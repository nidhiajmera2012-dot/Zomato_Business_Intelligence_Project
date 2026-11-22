
import os

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (accuracy_score, f1_score, precision_score,
                             recall_score, roc_auc_score)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

import clean
import features

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_FOLDER = os.path.join(ROOT, "data", "cleaned")
MODEL_PATH = os.path.join(ROOT, "models", "churn_best_model.pkl")
POWERBI_FOLDER = os.path.join(ROOT, "powerbi", "data")

TABLE_NAMES = ["orders", "order_items", "customers", "restaurants", "menu",
               "delivery_partners", "payments", "customer_feedback",
               "promotions", "cities", "traffic", "weather"]

NUM_FEATURES = ["NumOrders", "TotalSpent", "AvgOrderValue", "CancelRate", "LateRate",
                "AvgDeliveryTime", "AvgRating", "CustomerAge",
                "DaysSinceLastOrder", "DaysSinceFirstOrder"]
CAT_FEATURES = ["CustomerGender", "Membership", "CustomerCity", "PreferredCuisine"]


def load_abt():
    """Read the cleaned tables, clean them again and return the order-level table."""
    clean_tables = {}
    for name in TABLE_NAMES:
        path = os.path.join(DATA_FOLDER, name + ".csv")
        try:
            table = pd.read_csv(path)
        except FileNotFoundError:
            raise SystemExit("Missing file: " + path)
        clean_tables[name] = getattr(clean, "clean_" + name)(table)

    abt = clean.build_abt(clean_tables)
    return features.build_features(abt)


def build_customer_table(abt, churn_days=270):
    """One row per customer, using orders up to the cutoff date.

    Churned = 1 when the customer has no order after the cutoff.
    """
    abt = abt.copy()
    abt["OrderDate"] = pd.to_datetime(abt["OrderDate"])
    abt["IsCancelled"] = (abt["OrderStatus"] == "Cancelled").astype(int)
    abt["IsLate"] = (abt["OrderStatus"] == "Delivered Late").astype(int)

    cutoff = abt["OrderDate"].max() - pd.Timedelta(days=churn_days)
    past = abt[abt["OrderDate"] <= cutoff]
    future = abt[abt["OrderDate"] > cutoff]

    cust = past.groupby("CustomerID").agg(
        NumOrders=("OrderID", "count"),
        TotalSpent=("FinalAmount", "sum"),
        AvgOrderValue=("FinalAmount", "mean"),
        CancelRate=("IsCancelled", "mean"),
        LateRate=("IsLate", "mean"),
        AvgDeliveryTime=("DeliveryTimeMinutes", "mean"),
        AvgRating=("CustomerRating", "mean"),
        FirstOrder=("OrderDate", "min"),
        LastOrder=("OrderDate", "max"),
        CustomerAge=("CustomerAge", "first"),
        CustomerGender=("CustomerGender", "first"),
        Membership=("Membership", "first"),
        CustomerCity=("CustomerCity", "first"),
        PreferredCuisine=("PreferredCuisine", "first"),
    ).reset_index()

    cust["DaysSinceLastOrder"] = (cutoff - cust["LastOrder"]).dt.days
    cust["DaysSinceFirstOrder"] = (cutoff - cust["FirstOrder"]).dt.days
    cust["Churned"] = (~cust["CustomerID"].isin(future["CustomerID"])).astype(int)
    return cust.drop(columns=["FirstOrder", "LastOrder"])


def make_model():
    """Preprocessing plus logistic regression (C = 0.1), the final churn model."""
    preprocessor = ColumnTransformer([
        ("num", Pipeline([("fill", SimpleImputer(strategy="median")),
                          ("scale", StandardScaler())]), NUM_FEATURES),
        ("cat", Pipeline([("fill", SimpleImputer(strategy="most_frequent")),
                          ("onehot", OneHotEncoder(handle_unknown="ignore"))]), CAT_FEATURES),
    ])
    return Pipeline([("prep", preprocessor),
                     ("model", LogisticRegression(C=0.1, max_iter=1000))])


def train_and_save(cust):
    """Train on 80% of customers, test on 20%, and save the model and dashboard files."""
    X = cust[NUM_FEATURES + CAT_FEATURES]
    y = cust["Churned"]
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y)

    model = make_model()
    model.fit(X_train, y_train)

    prob = model.predict_proba(X_test)[:, 1]
    pred = (prob >= 0.5).astype(int)
    metrics = pd.DataFrame({
        "Metric": ["Accuracy", "Precision", "Recall", "F1", "ROC-AUC"],
        "Value": [accuracy_score(y_test, pred),
                  precision_score(y_test, pred, zero_division=0),
                  recall_score(y_test, pred, zero_division=0),
                  f1_score(y_test, pred, zero_division=0),
                  roc_auc_score(y_test, prob)],
    })

    # Permutation importance: how much the AUC drops when one column is shuffled.
    perm = permutation_importance(model, X_test, y_test, n_repeats=5,
                                  random_state=42, scoring="roc_auc")
    drivers = pd.Series(perm.importances_mean, index=X_test.columns)
    drivers = drivers.sort_values(ascending=False).reset_index()
    drivers.columns = ["Feature", "Importance"]

    # Risk segments are relative: top, middle and bottom third of the probabilities.
    scores = pd.DataFrame({
        "CustomerID": cust.loc[X_test.index, "CustomerID"].values,
        "ChurnProbability": prob,
        "ActualChurn": np.array(y_test),
    })
    scores["RiskSegment"] = pd.qcut(scores["ChurnProbability"].rank(method="first"),
                                    3, labels=["Low", "Medium", "High"])

    os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
    os.makedirs(POWERBI_FOLDER, exist_ok=True)
    joblib.dump(model, MODEL_PATH)
    scores.to_csv(os.path.join(POWERBI_FOLDER, "churn_scores.csv"), index=False)
    drivers.to_csv(os.path.join(POWERBI_FOLDER, "churn_drivers.csv"), index=False)
    metrics.to_csv(os.path.join(POWERBI_FOLDER, "churn_metrics.csv"), index=False)
    return metrics, scores


if __name__ == "__main__":
    abt = load_abt()
    cust = build_customer_table(abt)
    print("Customers:", cust.shape[0], " Churn rate:", round(cust["Churned"].mean() * 100, 1), "%")

    metrics, scores = train_and_save(cust)
    print(metrics.round(3))
    print(scores["RiskSegment"].value_counts())
    print("Saved model to", MODEL_PATH)
