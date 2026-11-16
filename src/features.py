import pandas as pd
import numpy as np


def add_time_features(df):
    df = df.copy()

    # hour of the order (0 to 23), taken from the first two characters of OrderTime
    df["OrderHour"] = df["OrderTime"].str[:2].astype(int)

    # 1 if the order was placed in the lunch rush (11-13) or dinner rush (18-20)
    df["PeakHour"] = df["OrderHour"].isin([11, 12, 13, 18, 19, 20]).astype(int)

    # day name and weekend flag (Saturday = 5, Sunday = 6)
    df["DayOfWeek"] = df["OrderDate"].dt.day_name()
    df["WeekendOrder"] = (df["OrderDate"].dt.dayofweek >= 5).astype(int)

    # month number (1 to 12)
    df["OrderMonth"] = df["OrderDate"].dt.month

    # meal of the day, based on the hour
    hour = df["OrderHour"]
    conditions = [
        hour.between(6, 10),
        hour.between(11, 14),
        hour.between(15, 17),
        hour.between(18, 21),
    ]
    choices = ["Breakfast", "Lunch", "Snack", "Dinner"]
    df["MealTime"] = np.select(conditions, choices, default="Late Night")

    return df

def add_tenure_features(df):
    df = df.copy()

    # days between registration and the order (negative means the order came first, so it is not valid)
    tenure = (df["OrderDate"] - df["RegistrationDate"]).dt.days
    df["CustomerTenure"] = tenure.mask(tenure < 0)

    # days between the partner joining and the order
    experience = (df["OrderDate"] - df["PartnerJoiningDate"]).dt.days
    df["PartnerExperienceDays"] = experience.mask(experience < 0)

    return df

def add_order_features(df):
    df = df.copy()

    # 1 if a coupon was used, otherwise 0
    df["HasCoupon"] = df["CouponCode"].notnull().astype(int)

    # discount as a percentage of the food cost
    df["DiscountPercent"] = (df["Discount"] / df["FoodCost"] * 100).round(1)

    # partner's usual delivery time divided by this delivery's time
    # above 1 = faster than usual, below 1 = slower than usual
    # WARNING: uses DeliveryTimeMinutes (the Week 3 target), so use it for dashboards only, never as a model input
    df["DeliveryEfficiency"] = (df["PartnerAvgDeliveryTime"] / df["DeliveryTimeMinutes"]).round(2)

    return df

def build_features(df):
    df = add_time_features(df)
    df = add_tenure_features(df)
    df = add_order_features(df)
    return df