

import os

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

import clean
import features

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_FOLDER = os.path.join(ROOT, "data", "cleaned")
MODEL_PATH = os.path.join(ROOT, "models", "delivery_time_best_model.pkl")
POWERBI_FOLDER = os.path.join(ROOT, "powerbi", "data")

TABLE_NAMES = ["orders", "order_items", "customers", "restaurants", "menu",
               "delivery_partners", "payments", "customer_feedback",
               "promotions", "cities", "traffic", "weather"]

TARGET = "DeliveryTimeMinutes"

NUM_FEATURES = ["FoodCost", "DeliveryFee", "DiscountPercentage", "CustomerAge", "TotalOrders",
                "RestaurantRating", "AverageCost", "Latitude", "Longitude", "PartnerAge",
                "PartnerRating", "CompletedDeliveries", "PartnerAvgDeliveryTime", "ItemCount",
                "Temperature", "Rainfall", "Humidity", "AverageSpeed", "CityPopulation",
                "CityAverageIncome", "OrderHour", "PeakHour", "WeekendOrder", "HasCoupon",
                "CustomerTenure", "PartnerExperienceDays"]

CAT_FEATURES = ["PaymentMethod", "CustomerGender", "Membership", "Cuisine", "RestaurantType",
                "VehicleType", "Region", "MealTime", "DayOfWeek", "RestaurantCity", "Area"]


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


def make_model():
    """Fill missing values, one-hot encode the text columns, then linear regression."""
    preprocessor = ColumnTransformer([
        ("num", SimpleImputer(strategy="median"), NUM_FEATURES),
        ("cat", Pipeline([("fill", SimpleImputer(strategy="most_frequent")),
                          ("onehot", OneHotEncoder(handle_unknown="ignore"))]), CAT_FEATURES),
    ])
    return Pipeline([("prep", preprocessor), ("model", LinearRegression())])


def train_and_save(abt):
    """Train on 80% of the orders, test on 20%, and save the model and dashboard files."""
    df = abt.dropna(subset=[TARGET])
    df = df[df[TARGET] <= 100]
    print("Rows kept:", df.shape[0], "of", abt.shape[0])

    train_df, test_df = train_test_split(df, test_size=0.2, random_state=42)
    X_train = train_df[NUM_FEATURES + CAT_FEATURES]
    y_train = train_df[TARGET]
    X_test = test_df[NUM_FEATURES + CAT_FEATURES]
    y_test = test_df[TARGET]

    model = make_model()
    model.fit(X_train, y_train)
    pred = model.predict(X_test)

    mse = mean_squared_error(y_test, pred)
    metrics = pd.DataFrame({
        "Metric": ["MAE", "RMSE", "R2"],
        "Value": [mean_absolute_error(y_test, pred), np.sqrt(mse), r2_score(y_test, pred)],
    })

    # Predicted vs actual, with the error of each order
    results = pd.DataFrame({"Actual": np.array(y_test), "Predicted": np.array(pred)})
    results["Residual"] = results["Actual"] - results["Predicted"]
    results["RowID"] = range(1, len(results) + 1)

    # Permutation importance: how much the MAE grows when one column is shuffled.
    perm = permutation_importance(model, X_test, y_test, n_repeats=5, random_state=42,
                                  scoring="neg_mean_absolute_error")
    importance = pd.Series(perm.importances_mean, index=X_test.columns)
    importance = importance.sort_values(ascending=False).reset_index()
    importance.columns = ["Feature", "Importance"]

    os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
    os.makedirs(POWERBI_FOLDER, exist_ok=True)
    joblib.dump(model, MODEL_PATH)
    results.to_csv(os.path.join(POWERBI_FOLDER, "delivery_predictions.csv"), index=False)
    importance.to_csv(os.path.join(POWERBI_FOLDER, "delivery_feature_importance.csv"), index=False)
    metrics.to_csv(os.path.join(POWERBI_FOLDER, "delivery_metrics.csv"), index=False)
    return metrics, importance


if __name__ == "__main__":
    abt = load_abt()
    print("ABT shape:", abt.shape)

    metrics, importance = train_and_save(abt)
    print(metrics.round(4))
    print(importance.head(5))
    print("Saved model to", MODEL_PATH)
