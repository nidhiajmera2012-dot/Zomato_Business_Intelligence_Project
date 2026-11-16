"""clean_and_load.py - Clean the 12 raw CSVs and load them into the final MySQL tables.

Stage 1: clean every table (duplicates, messy city names, mixed date formats,
         negative values, orphan keys, missing amounts) and save the result
         to data/cleaned/ as CSV files.
Stage 2: load the cleaned data into the final tables in zomato_bi
         (the ones with primary keys and foreign keys).

Run from the project root:   python src/clean_and_load.py
"""
import re
from datetime import datetime, date
from getpass import getpass
from pathlib import Path
from urllib.parse import quote_plus

import pandas as pd

DB_NAME = "zomato_bi"
ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RAW = ROOT / "data" / "raw"
DEFAULT_CLEAN = ROOT / "data" / "cleaned"

LOAD_ORDER = [
    "cities", "customers", "restaurants", "delivery_partners", "promotions",
    "menu", "orders", "order_items", "payments", "customer_feedback",
    "weather", "traffic",
]
START, END = date(2023, 1, 1), date(2024, 12, 31)


# ----------------------------------------------------------------- helpers
def clean_stem(filename):
    s = filename.lower()
    s = re.sub(r"(\.csv)+$", "", s)
    s = re.sub(r"_csv$", "", s)
    s = re.sub(r"\s*\(\d+\)$", "", s)
    return s.strip()


def read_raw(folder, name):
    files = [p for p in Path(folder).iterdir()
             if p.is_file() and p.name.lower().endswith(".csv") and clean_stem(p.name) == name]
    if not files:
        raise FileNotFoundError(f"No CSV for '{name}' in {folder}")
    exact = [p for p in files if p.name.lower() == f"{name}.csv"]
    path = (exact or sorted(files))[0]
    return pd.read_csv(path, dtype=str, keep_default_na=False, na_values=[""])


def log(table, msg):
    print(f"   [{table}] {msg}")


def num(s):
    return pd.to_numeric(s, errors="coerce")


def to_int(s):
    return num(s).round().astype("Int64")


def dedupe(df, key, table):
    n0 = len(df)
    df = df.drop_duplicates().drop_duplicates(subset=[key], keep="first")
    if n0 != len(df):
        log(table, f"removed {n0 - len(df)} duplicate rows")
    return df.reset_index(drop=True)


ALIASES = {  # old / alternative names -> the name used in the cities table
    "bombay": "Mumbai", "calcutta": "Kolkata", "madras": "Chennai",
    "bangalore": "Bengaluru", "baroda": "Vadodara", "new delhi": "Delhi",
}


def fill_city_by_neighbors(df, id_col, table):
    """Rows are stored in blocks per city, so a blank city can be filled when the
    nearest known rows before and after it agree."""
    d = df.sort_values(id_col)
    c = d["City"].astype("string").str.strip()
    before, after = c.ffill(), c.bfill()
    fill = c.isna() & before.notna() & (before.str.lower() == after.str.lower())
    d.loc[fill, "City"] = before[fill]
    if fill.sum():
        log(table, f"filled {int(fill.sum())} blank city values from neighbouring rows")
    return d.sort_index()


def norm_city(df, cities, table):
    canon = {c.lower().strip(): c for c in cities}
    canon.update({k: v for k, v in ALIASES.items() if v in cities})
    key = df["City"].astype("string").str.strip().str.replace(r"\s+", " ", regex=True).str.lower()
    fixed = key.map(canon)
    changed = int((fixed.notna() & (df["City"] != fixed)).sum())
    bad = int(fixed.isna().sum())
    df["City"] = fixed
    if changed:
        log(table, f"fixed {changed} messy city names")
    if bad:
        log(table, f"dropped {bad} rows with unknown city")
        df = df[df["City"].notna()]
    return df.reset_index(drop=True)


# ------------------------------------------------------------------- dates
_UNAMBIGUOUS = [
    (r"^\d{4}-\d{2}-\d{2}$", "%Y-%m-%d"),
    (r"^\d{4}\.\d{2}\.\d{2}$", "%Y.%m.%d"),
    (r"^\d{2}-\d{2}-\d{4}$", "%d-%m-%Y"),
    (r"^\d{1,2} [A-Za-z]{3} \d{4}$", "%d %b %Y"),
]


def date_candidates(value):
    """Possible dates for a raw text value. Slash dates can be dd/mm or mm/dd."""
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return []
    s = str(value).strip()
    for pat, fmt in _UNAMBIGUOUS:
        if re.match(pat, s):
            try:
                return [datetime.strptime(s, fmt).date()]
            except ValueError:
                return []
    if re.match(r"^\d{1,2}/\d{1,2}/\d{4}$", s):
        out = []
        for fmt in ("%d/%m/%Y", "%m/%d/%Y"):     # dd/mm first = our default
            try:
                d = datetime.strptime(s, fmt).date()
                if d not in out:
                    out.append(d)
            except ValueError:
                pass
        return out
    return []


def resolve_with(cands, other=None, upper=None):
    """Choose one date from candidates, using extra information when we have it."""
    c = list(cands)
    if other:
        both = [d for d in c if d in other]
        if len(both) >= 1:
            c = both
    if upper is not None:
        ok = [d for d in c if d <= upper]
        if ok:
            c = ok
    return c[0] if c else None


# ------------------------------------------------------------- the cleaning
def clean_all(raw_dir):
    raw = {n: read_raw(raw_dir, n) for n in LOAD_ORDER}
    out = {}

    # cities --------------------------------------------------------------
    t = "cities"
    d = raw[t].copy()
    d["CityID"] = to_int(d["CityID"])
    d["Population"] = num(d["Population"]).round().astype("Int64")
    d["AverageIncome"] = num(d["AverageIncome"])
    d["City"] = d["City"].str.strip()
    out[t] = dedupe(d, "CityID", t)
    city_names = out[t]["City"].tolist()

    # promotions ----------------------------------------------------------
    t = "promotions"
    d = raw[t].copy()
    d["PromotionID"] = to_int(d["PromotionID"])
    d["CouponCode"] = d["CouponCode"].str.strip().str.upper()
    d["DiscountPercentage"] = to_int(d["DiscountPercentage"])
    starts, ends, swapped = [], [], 0
    for s, e in zip(d["StartDate"], d["EndDate"]):
        cs, ce = date_candidates(s), date_candidates(e)
        pick = next(((a, b) for a in cs for b in ce if b >= a), None)
        if pick is None:
            a, b = (cs[0] if cs else None), (ce[0] if ce else None)
            if a is not None and b is not None and b < a:
                a, b = b, a            # end before start: the two dates were swapped
                swapped += 1
            pick = (a, b)
        starts.append(pick[0]); ends.append(pick[1])
    d["StartDate"], d["EndDate"] = starts, ends
    if swapped:
        log(t, f"swapped start/end dates on {swapped} promotions where end was before start")
    d = d.dropna(subset=["StartDate", "EndDate"])
    out[t] = dedupe(d, "PromotionID", t)
    promo_codes = set(out[t]["CouponCode"])

    # restaurants ---------------------------------------------------------
    t = "restaurants"
    d = raw[t].copy()
    d["RestaurantID"] = to_int(d["RestaurantID"])
    d = norm_city(d, city_names, t)
    r = num(d["Rating"])
    bad = int(((r < 1) | (r > 5)).sum())
    d["Rating"] = r.where((r >= 1) & (r <= 5))
    if bad:
        log(t, f"set {bad} impossible ratings (outside 1-5) to blank")
    d["AverageCost"] = num(d["AverageCost"]).abs()
    d["OpeningTime"] = d["OpeningTime"].str.strip().str.slice(0, 5) + ":00"
    d["ClosingTime"] = d["ClosingTime"].str.strip().str.slice(0, 5) + ":00"
    d["Latitude"] = num(d["Latitude"]).round(6)
    d["Longitude"] = num(d["Longitude"]).round(6)
    out[t] = dedupe(d, "RestaurantID", t)
    rest_ids = set(out[t]["RestaurantID"])

    # menu ----------------------------------------------------------------
    t = "menu"
    d = raw[t].copy()
    d["FoodItemID"] = to_int(d["FoodItemID"])
    d["RestaurantID"] = to_int(d["RestaurantID"])
    d["Price"] = num(d["Price"]).abs()
    d["PreparationTime"] = to_int(d["PreparationTime"])
    d["Calories"] = to_int(d["Calories"])
    n0 = len(d)
    d = d[d["RestaurantID"].isin(rest_ids)]
    if n0 != len(d):
        log(t, f"dropped {n0 - len(d)} rows with unknown restaurant")
    out[t] = dedupe(d, "FoodItemID", t)
    menu_ids = set(out[t]["FoodItemID"])

    # delivery_partners ---------------------------------------------------
    t = "delivery_partners"
    d = raw[t].copy()
    d["DeliveryPartnerID"] = to_int(d["DeliveryPartnerID"])
    d = norm_city(d, city_names, t)
    d["Age"] = to_int(d["Age"])
    r = num(d["Rating"])
    d["Rating"] = r.where((r >= 1) & (r <= 5))
    d["CompletedDeliveries"] = to_int(d["CompletedDeliveries"]).abs()
    d["AverageDeliveryTime"] = num(d["AverageDeliveryTime"]).abs()
    log(t, f"{int((d['JoiningDate'].map(date_candidates).map(len) > 1).sum())} joining dates could be dd/mm or mm/dd; used dd/mm")
    d["JoiningDate"] = [resolve_with(date_candidates(x)) for x in d["JoiningDate"]]
    out[t] = dedupe(d, "DeliveryPartnerID", t)
    dp_ids = set(out[t]["DeliveryPartnerID"])

    # orders + payments dates (payment date always equals order date) ------
    pay_raw = raw["payments"].copy()
    pay_raw["OrderID"] = to_int(pay_raw["OrderID"])
    pay_cands = {oid: set(date_candidates(x))
                 for oid, x in zip(pay_raw["OrderID"], pay_raw["PaymentDate"])}

    t = "orders"
    d = raw[t].copy()
    for c in ["OrderID", "CustomerID", "RestaurantID", "DeliveryPartnerID"]:
        d[c] = to_int(d[c])
    d = dedupe(d, "OrderID", t)
    od, via_pay = [], 0
    for oid, x in zip(d["OrderID"], d["OrderDate"]):
        c = date_candidates(x)
        pick = resolve_with(c, pay_cands.get(oid))
        if len(c) > 1 and pick is not None and oid in pay_cands and pick in pay_cands[oid]:
            via_pay += 1
        od.append(pick)
    d["OrderDate"] = od
    log(t, f"{via_pay} ambiguous dd/mm vs mm/dd dates were settled using the payment date")
    for c in ["DeliveryTimeMinutes", "FoodCost", "DeliveryFee", "Discount", "GST", "FinalAmount"]:
        d[c] = num(d[c])
    for c in ["DeliveryTimeMinutes", "FoodCost", "DeliveryFee", "Discount", "GST"]:
        d[c] = d[c].abs()
    d["DeliveryTimeMinutes"] = d["DeliveryTimeMinutes"].round().astype("Int64")
    missing = d["FinalAmount"].isna()
    d.loc[missing, "FinalAmount"] = (d["FoodCost"] + d["DeliveryFee"] - d["Discount"] + d["GST"]).round(2)
    if missing.sum():
        log(t, f"calculated {int(missing.sum())} missing FinalAmount values")
    d["CouponCode"] = d["CouponCode"].str.strip().str.upper()
    d.loc[~d["CouponCode"].isin(promo_codes), "CouponCode"] = None
    d = d.dropna(subset=["OrderDate"])
    # customers are cleaned below; keep orders for now, filter after customers
    orders = d

    # customers -----------------------------------------------------------
    t = "customers"
    c = raw[t].copy()
    c["CustomerID"] = to_int(c["CustomerID"])
    c = dedupe(c, "CustomerID", t)
    c = norm_city(c, city_names, t)
    age = num(c["Age"]).abs()
    c["Age"] = age.where((age >= 10) & (age <= 100)).round().astype("Int64")
    c["Name"] = c["Name"].str.strip()
    c["Email"] = c["Email"].str.strip().str.lower()

    def phone(x):
        if pd.isna(x):
            return None
        digits = re.sub(r"\D", "", str(x))
        if len(digits) == 12 and digits.startswith("91"):
            digits = digits[2:]
        return digits if len(digits) == 10 else None

    def pincode(x):
        if pd.isna(x):
            return None
        digits = re.sub(r"\D", "", str(x))
        return digits if len(digits) == 6 else None

    bad_ph = int(c["Phone"].notna().sum() - c["Phone"].map(phone).notna().sum())
    c["Phone"] = c["Phone"].map(phone)
    bad_pc = int(c["Pincode"].notna().sum() - c["Pincode"].map(pincode).notna().sum())
    c["Pincode"] = c["Pincode"].map(pincode)
    if bad_ph:
        log(t, f"blanked {bad_ph} invalid phone numbers")
    if bad_pc:
        log(t, f"blanked {bad_pc} invalid pincodes")
    c["TotalOrders"] = to_int(c["TotalOrders"]).abs()
    first_order = orders.groupby("CustomerID")["OrderDate"].min().to_dict()
    c["RegistrationDate"] = [
        resolve_with(date_candidates(x), upper=first_order.get(cid))
        for cid, x in zip(c["CustomerID"], c["RegistrationDate"])
    ]
    c = c.dropna(subset=["RegistrationDate"])
    out[t] = c.reset_index(drop=True)
    cust_ids = set(out[t]["CustomerID"])

    # orders: remove orphans ----------------------------------------------
    t = "orders"
    n0 = len(orders)
    orders = orders[orders["CustomerID"].isin(cust_ids)
                    & orders["RestaurantID"].isin(rest_ids)
                    & orders["DeliveryPartnerID"].isin(dp_ids)]
    if n0 != len(orders):
        log(t, f"dropped {n0 - len(orders)} orders pointing to a missing customer/restaurant/partner")
    out[t] = orders.reset_index(drop=True)
    order_ids = set(out[t]["OrderID"])
    order_date = dict(zip(out[t]["OrderID"], out[t]["OrderDate"]))

    # order_items ---------------------------------------------------------
    t = "order_items"
    d = raw[t].copy()
    for col in ["OrderItemID", "OrderID", "FoodItemID"]:
        d[col] = to_int(d[col])
    d["Quantity"] = to_int(d["Quantity"]).abs()
    d["UnitPrice"] = num(d["UnitPrice"]).abs()
    d["TotalPrice"] = num(d["TotalPrice"])
    miss = d["TotalPrice"].isna()
    d.loc[miss, "TotalPrice"] = (d["Quantity"] * d["UnitPrice"]).round(2)
    if miss.sum():
        log(t, f"calculated {int(miss.sum())} missing TotalPrice values")
    n0 = len(d)
    d = d[d["OrderID"].isin(order_ids) & d["FoodItemID"].isin(menu_ids)]
    if n0 != len(d):
        log(t, f"dropped {n0 - len(d)} rows linked to removed orders or unknown menu items")
    out[t] = dedupe(d, "OrderItemID", t)

    # payments ------------------------------------------------------------
    t = "payments"
    d = raw[t].copy()
    for col in ["PaymentID", "OrderID"]:
        d[col] = to_int(d[col])
    n0 = len(d)
    d = d[d["OrderID"].isin(order_ids)]
    if n0 != len(d):
        log(t, f"dropped {n0 - len(d)} rows linked to removed orders")
    d["PaymentDate"] = d["OrderID"].map(order_date)
    out[t] = dedupe(d, "PaymentID", t)

    # customer_feedback ---------------------------------------------------
    t = "customer_feedback"
    d = raw[t].copy()
    for col in ["FeedbackID", "OrderID"]:
        d[col] = to_int(d[col])
    for col in ["CustomerRating", "DeliveryRating", "FoodRating"]:
        v = num(d[col])
        bad = int(((v < 1) | (v > 5)).sum())
        if bad:
            log(t, f"blanked {bad} impossible {col} values (outside 1-5)")
        d[col] = v.where((v >= 1) & (v <= 5)).round().astype("Int64")
    n0 = len(d)
    d = d[d["OrderID"].isin(order_ids)]
    if n0 != len(d):
        log(t, f"dropped {n0 - len(d)} rows linked to removed orders")
    out[t] = dedupe(d, "FeedbackID", t)

    # weather -------------------------------------------------------------
    t = "weather"
    d = raw[t].copy()
    d["WeatherID"] = to_int(d["WeatherID"])
    d = dedupe(d, "WeatherID", t)
    d = fill_city_by_neighbors(d, "WeatherID", t)
    d = norm_city(d, city_names, t)
    cands = d["Date"].map(date_candidates)
    guess = int((cands.map(len) > 1).sum())
    d["Date"] = cands.map(lambda c: c[0] if c else None)
    d = d.dropna(subset=["Date"])
    log(t, f"{guess} dates could be dd/mm or mm/dd; used dd/mm (India style)")
    d["Temperature"] = num(d["Temperature"])
    d["Rainfall"] = num(d["Rainfall"]).abs()
    h = num(d["Humidity"]).abs()
    bad = int((h > 100).sum())
    d["Humidity"] = h.where(h <= 100).round().astype("Int64")
    if bad:
        log(t, f"blanked {bad} impossible humidity values (over 100)")
    out[t] = d.reset_index(drop=True)

    # traffic -------------------------------------------------------------
    t = "traffic"
    d = raw[t].copy()
    d["TrafficID"] = to_int(d["TrafficID"])
    d = dedupe(d, "TrafficID", t)
    d = norm_city(d, city_names, t)
    cands = d["Date"].map(date_candidates)
    guess = int((cands.map(len) > 1).sum())
    d["Date"] = cands.map(lambda c: c[0] if c else None)
    d = d.dropna(subset=["Date"])
    log(t, f"{guess} dates could be dd/mm or mm/dd; used dd/mm (India style)")
    d["Time"] = d["Time"].str.strip().str.slice(0, 5) + ":00"
    d["AverageSpeed"] = num(d["AverageSpeed"]).abs()
    out[t] = d.reset_index(drop=True)

    return {k: out[k] for k in LOAD_ORDER}


# ------------------------------------------------------------------ saving
def save_cleaned(tables, folder):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    for name, df in tables.items():
        df.to_csv(folder / f"{name}.csv", index=False)


def to_db_frame(df):
    df = df.astype(object)
    return df.where(pd.notna(df), None)


def load_to_mysql(tables, engine):
    from sqlalchemy import text
    with engine.begin() as conn:
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
        for name in reversed(LOAD_ORDER):
            conn.execute(text(f"DELETE FROM {name}"))
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
    for name in LOAD_ORDER:
        df = to_db_frame(tables[name])
        df.to_sql(name, engine, if_exists="append", index=False, chunksize=2000)
        with engine.connect() as conn:
            n = conn.execute(text(f"SELECT COUNT(*) FROM {name}")).scalar()
        status = "OK" if n == len(df) else "MISMATCH"
        print(f"[{status}] {name}: {len(df)} cleaned rows, {n} in MySQL")


def main():
    from sqlalchemy import create_engine

    answer = input(f"Folder with the RAW csv files [{DEFAULT_RAW}]: ").strip().strip('"')
    raw_dir = Path(answer) if answer else DEFAULT_RAW
    if not raw_dir.is_dir():
        print(f"That folder does not exist: {raw_dir}")
        return
    clean_dir = DEFAULT_CLEAN

    print("\nSTAGE 1: cleaning")
    tables = clean_all(raw_dir)
    save_cleaned(tables, clean_dir)
    print(f"\nCleaned files saved in: {clean_dir}")

    user = input("\nMySQL user [root]: ").strip() or "root"
    password = quote_plus(getpass("MySQL password: "))
    engine = create_engine(f"mysql+pymysql://{user}:{password}@localhost:3306/{DB_NAME}")
    print("\nSTAGE 2: loading into MySQL")
    load_to_mysql(tables, engine)
    print("\nDone.")


if __name__ == "__main__":
    main()
