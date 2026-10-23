import os
from pathlib import Path

import pandas as pd

DEFAULT_DIR = Path(os.environ.get("F29_OLIST_DIR") or Path(__file__).resolve().parents[3] / "ai-data-train-prod" / "olist")
START, END = pd.Timestamp("2017-01-01"), pd.Timestamp("2018-09-01")
DROP_STATUS = ["canceled", "unavailable"]
PRODUCT_COLS = {
    "product_photos_qty": "photos",
    "product_description_lenght": "description_length",
    "product_name_lenght": "name_length",
    "product_weight_g": "weight_g",
    "product_length_cm": "length_cm",
    "product_height_cm": "height_cm",
    "product_width_cm": "width_cm",
}
ORDER_DATES = ["order_purchase_timestamp", "order_delivered_customer_date", "order_estimated_delivery_date"]


def _csv(folder, name, dates=()):
    return pd.read_csv(Path(folder) / f"olist_{name}_dataset.csv", parse_dates=list(dates))


def _sales(folder, report):
    orders = _csv(folder, "orders", ORDER_DATES)
    items = _csv(folder, "order_items")
    report["order_items_raw"] = len(items)
    kept = orders[~orders["order_status"].isin(DROP_STATUS)]
    report["orders_dropped_status"] = len(orders) - len(kept)
    in_range = kept[kept["order_purchase_timestamp"].between(START, END, inclusive="left")]
    report["orders_dropped_date"] = len(kept) - len(in_range)
    sales = items.merge(in_range[["order_id", *ORDER_DATES]], on="order_id")
    report["sales_rows"] = len(sales)
    return sales.rename(columns={
        "order_purchase_timestamp": "ts",
        "order_delivered_customer_date": "delivered",
        "order_estimated_delivery_date": "estimated",
    })


def _products(folder, report):
    products = _csv(folder, "products")
    names = pd.read_csv(Path(folder) / "product_category_name_translation.csv", encoding="utf-8-sig")
    english = dict(zip(names.iloc[:, 0], names.iloc[:, 1]))
    raw = products["product_category_name"]
    products["category"] = raw.map(english).fillna(raw).fillna("unknown")
    report["products_missing_content"] = int(products["product_photos_qty"].isna().sum())
    return products.rename(columns=PRODUCT_COLS)[["product_id", "category", *PRODUCT_COLS.values()]]


def _rated(folder, sales, report):
    reviews = _csv(folder, "order_reviews", ["review_creation_date", "review_answer_timestamp"])
    report["reviews_raw"] = len(reviews)
    reviews = reviews.dropna(subset=["review_score"]).sort_values("review_answer_timestamp")
    reviews = reviews.drop_duplicates("order_id", keep="last")
    report["reviews_kept"] = len(reviews)
    listings = sales[["order_id", "product_id", "seller_id"]].drop_duplicates()
    rated = listings.merge(reviews[["order_id", "review_score", "review_answer_timestamp"]], on="order_id")
    return rated.rename(columns={"review_score": "stars", "review_answer_timestamp": "ts"})


def load(folder=DEFAULT_DIR):
    report = {}
    sales = _sales(folder, report)
    return sales, _products(folder, report), _rated(folder, sales, report), report
