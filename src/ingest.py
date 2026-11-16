
from getpass import getpass
from pathlib import Path
from urllib.parse import quote_plus

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.types import String, Text

DB_NAME = "zomato_bi"
RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"

TABLES = [
    "cities", "customers", "restaurants", "delivery_partners", "menu",
    "promotions", "orders", "order_items", "payments",
    "customer_feedback", "weather", "traffic",
]


def load_all(engine, raw_dir=RAW_DIR):

    results = {}
    for name in TABLES:
        path = Path(raw_dir) / f"{name}.csv"
        try:
            # dtype=str keeps everything as text; only truly empty cells become NULL
            df = pd.read_csv(path, dtype=str, keep_default_na=False, na_values=[""])
        except FileNotFoundError:
            print(f"[MISSING] {path.name} not found in {raw_dir}")
            continue
        except Exception as exc:
            print(f"[ERROR] could not read {path.name}: {exc}")
            continue

        col_types = {c: (Text() if c == "Review" else String(255)) for c in df.columns}
        df.to_sql(f"stg_{name}", engine, if_exists="replace", index=False,
                  dtype=col_types, chunksize=2000)

        with engine.connect() as conn:
            in_db = conn.execute(text(f"SELECT COUNT(*) FROM stg_{name}")).scalar()
        status = "OK" if in_db == len(df) else "MISMATCH"
        print(f"[{status}] stg_{name}: {len(df)} rows in CSV, {in_db} rows in MySQL")
        results[name] = in_db
    return results


def main():
    user = input("MySQL user [root]: ").strip() or "root"
    password = quote_plus(getpass("MySQL password: "))
    host = "localhost:3306"

    server = create_engine(f"mysql+pymysql://{user}:{password}@{host}/")
    with server.begin() as conn:
        conn.execute(text(f"CREATE DATABASE IF NOT EXISTS {DB_NAME}"))

    engine = create_engine(f"mysql+pymysql://{user}:{password}@{host}/{DB_NAME}")
    print(f"Reading CSVs from: {RAW_DIR}\n")
    results = load_all(engine)
    print(f"\nDone. {len(results)} of {len(TABLES)} tables loaded.")


if __name__ == "__main__":
    main()
