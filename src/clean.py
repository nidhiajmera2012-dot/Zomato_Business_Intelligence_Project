import pandas as pd
import numpy as np


def base_clean(df):
    df = df.copy()
    for col in df.select_dtypes(include="object").columns:
        df[col] = df[col].str.strip()
    df = df.drop_duplicates()
    df = df.reset_index(drop=True)
    return df


def clean_phone(series):
    s = series.astype("Int64").astype("string")
    s = s.str.zfill(10)
    return s


def clean_pincode(series):
    s = series.astype("Int64")
    s = s.mask(s.fillna(-1) == 0)
    s = s.astype("string")
    return s


def clean_date(series):
    return pd.to_datetime(series, format="%Y-%m-%d", errors="coerce")


def clean_outliers(series, upper_limit):
    return series.mask(series > upper_limit)


def clean_orders(df):
    df = base_clean(df)
    df["OrderDate"] = clean_date(df["OrderDate"])
    df["DeliveryTimeMinutes"] = clean_outliers(df["DeliveryTimeMinutes"], 200)
    return df


def clean_order_items(df):
    return base_clean(df)


def clean_customers(df):
    df = base_clean(df)
    df["Phone"] = clean_phone(df["Phone"])
    df["Pincode"] = clean_pincode(df["Pincode"])
    df["RegistrationDate"] = clean_date(df["RegistrationDate"])
    return df


def clean_restaurants(df):
    return base_clean(df)


def clean_menu(df):
    return base_clean(df)


def clean_delivery_partners(df):
    df = base_clean(df)
    df["JoiningDate"] = clean_date(df["JoiningDate"])
    return df


def clean_payments(df):
    df = base_clean(df)
    df["PaymentDate"] = clean_date(df["PaymentDate"])
    return df


def clean_customer_feedback(df):
    return base_clean(df)


def clean_promotions(df):
    df = base_clean(df)
    df["StartDate"] = clean_date(df["StartDate"])
    df["EndDate"] = clean_date(df["EndDate"])
    return df


def clean_cities(df):
    return base_clean(df)


def clean_traffic(df):
    df = base_clean(df)
    df["Date"] = clean_date(df["Date"])
    df["AverageSpeed"] = clean_outliers(df["AverageSpeed"], 80)
    return df


def clean_weather(df):
    df = base_clean(df)
    df["Date"] = clean_date(df["Date"])
    df["Temperature"] = clean_outliers(df["Temperature"], 50)
    return df

def build_abt(t):
    abt = t["orders"].copy()
    n = len(abt)

    # customers
    cust = t["customers"][["CustomerID", "Age", "Gender", "City", "State",
                           "RegistrationDate", "Membership", "TotalOrders", "PreferredCuisine"]]
    cust = cust.rename(columns={"Age": "CustomerAge", "Gender": "CustomerGender", "City": "CustomerCity"})
    abt = abt.merge(cust, on="CustomerID", how="left")
    assert len(abt) == n, "customers join changed the row count"

    # restaurants
    rest = t["restaurants"][["RestaurantID", "Cuisine", "City", "Area", "Rating",
                             "AverageCost", "RestaurantType", "Latitude", "Longitude"]]
    rest = rest.rename(columns={"City": "RestaurantCity", "Rating": "RestaurantRating"})
    abt = abt.merge(rest, on="RestaurantID", how="left")
    assert len(abt) == n, "restaurants join changed the row count"

    # delivery partners
    dp = t["delivery_partners"][["DeliveryPartnerID", "Age", "VehicleType", "JoiningDate",
                                 "City", "Rating", "CompletedDeliveries", "AverageDeliveryTime"]]
    dp = dp.rename(columns={"Age": "PartnerAge", "JoiningDate": "PartnerJoiningDate",
                            "City": "PartnerCity", "Rating": "PartnerRating",
                            "AverageDeliveryTime": "PartnerAvgDeliveryTime"})
    abt = abt.merge(dp, on="DeliveryPartnerID", how="left")
    assert len(abt) == n, "delivery partners join changed the row count"

    # order items: one summary row per order
    items = t["order_items"].groupby("OrderID", as_index=False).agg(
        ItemCount=("OrderItemID", "count"),
        TotalQuantity=("Quantity", "sum"),
        ItemsTotalPrice=("TotalPrice", "sum"))
    abt = abt.merge(items, on="OrderID", how="left")
    assert len(abt) == n, "order items join changed the row count"

    # payments: one row per order, best status first
    status_rank = {"Success": 0, "Refunded": 1, "Pending": 2, "Failed": 3}
    pay = t["payments"].copy()
    pay["rank"] = pay["PaymentStatus"].map(status_rank)
    pay = pay.sort_values(["OrderID", "rank"]).drop_duplicates(subset="OrderID", keep="first")
    pay = pay[["OrderID", "PaymentStatus"]]
    abt = abt.merge(pay, on="OrderID", how="left")
    assert len(abt) == n, "payments join changed the row count"

    # feedback: keep the latest feedback per order
    fb = t["customer_feedback"].sort_values("FeedbackID").drop_duplicates(subset="OrderID", keep="last")
    fb = fb[["OrderID", "CustomerRating", "DeliveryRating", "FoodRating", "Sentiment"]]
    abt = abt.merge(fb, on="OrderID", how="left")
    assert len(abt) == n, "feedback join changed the row count"

    # weather: one row per restaurant city and date
    weather = t["weather"].groupby(["City", "Date"], as_index=False).agg(
        Temperature=("Temperature", "mean"),
        Rainfall=("Rainfall", "mean"),
        Humidity=("Humidity", "mean"))
    weather = weather.rename(columns={"City": "RestaurantCity", "Date": "OrderDate"})
    abt = abt.merge(weather, on=["RestaurantCity", "OrderDate"], how="left")
    assert len(abt) == n, "weather join changed the row count"

    # traffic: one row per restaurant city and date
    traffic = t["traffic"].groupby(["City", "Date"], as_index=False).agg(
        AverageSpeed=("AverageSpeed", "mean"))
    traffic = traffic.rename(columns={"City": "RestaurantCity", "Date": "OrderDate"})
    abt = abt.merge(traffic, on=["RestaurantCity", "OrderDate"], how="left")
    assert len(abt) == n, "traffic join changed the row count"

    # cities
    city = t["cities"][["City", "Region", "Population", "AverageIncome"]]
    city = city.rename(columns={"City": "RestaurantCity", "Population": "CityPopulation",
                                "AverageIncome": "CityAverageIncome"})
    abt = abt.merge(city, on="RestaurantCity", how="left")
    assert len(abt) == n, "cities join changed the row count"

    # promotions
    promo = t["promotions"][["CouponCode", "DiscountPercentage", "CampaignName", "StartDate", "EndDate"]]
    promo = promo.rename(columns={"StartDate": "PromoStartDate", "EndDate": "PromoEndDate"})
    abt = abt.merge(promo, on="CouponCode", how="left")
    assert len(abt) == n, "promotions join changed the row count"
    return abt