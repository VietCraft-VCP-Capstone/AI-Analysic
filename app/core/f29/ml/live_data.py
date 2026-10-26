import re
import unicodedata
from datetime import datetime, timedelta

import pandas as pd
from bson import ObjectId

from app.api.v1._live import LOC_SP_THAT, _so, db_live
from app.api.v1._live_data import DON_HOP_LE

HISTORY_DAYS = 730
MAX_QTY = 50
SALES_COLS = ["order_id", "product_id", "seller_id", "price", "freight_value", "ts", "delivered", "estimated"]
PRODUCT_COLS = ["product_id", "category", "photos", "description_length", "name_length",
                "weight_g", "length_cm", "height_cm", "width_cm"]
RATED_COLS = ["order_id", "product_id", "seller_id", "stars", "ts"]
MARKUP = re.compile(r"<[^>]+>|[#*_>`]")
PRODUCT_FIELDS = {"categories": 1, "images": 1, "description": 1, "title": 1, "weight_g": 1, "dimensions_cm": 1}


def _delivered_at(order):
    return next((h.get("changed_at") for h in order.get("status_history") or [] if h.get("status") == "DELIVERED"), None)


def _order_rows(order):
    items = order.get("items") or []
    subtotal = sum((_so(i.get("retail_price")) or 0) * int(i.get("quantity") or 1) for i in items)
    ship = _so((order.get("financial_breakdown") or {}).get("shipping_fee")) or 0
    for it in items:
        price = _so(it.get("retail_price")) or 0
        if price <= 0:
            continue
        row = [str(order["_id"]), str(it.get("product_id")), str(order.get("shop_id")), price,
               ship * price / subtotal if subtotal else 0, order.get("created_at"), _delivered_at(order), None]
        yield from [row] * min(int(it.get("quantity") or 1), MAX_QTY)


def _text_len(s):
    return len(MARKUP.sub("", unicodedata.normalize("NFC", s or "")).strip())


def _product_row(p):
    dim = p.get("dimensions_cm") if isinstance(p.get("dimensions_cm"), dict) else {}
    return [str(p["_id"]), (p.get("categories") or ["unknown"])[0] or "unknown", len(p.get("images") or []),
            _text_len(p.get("description")), _text_len(p.get("title")),
            p.get("weight_g"), dim.get("length"), dim.get("height"), dim.get("width")]


def _dates(df, cols):
    for c in cols:
        df[c] = pd.to_datetime(df[c])
    return df


def load_tables(now: datetime):
    db = db_live()
    products = pd.DataFrame([_product_row(p) for p in db["products"].find(LOC_SP_THAT, PRODUCT_FIELDS)], columns=PRODUCT_COLS)
    products[PRODUCT_COLS[2:]] = products[PRODUCT_COLS[2:]].apply(lambda c: pd.to_numeric(c.astype(str), errors="coerce"))
    orders = db["orders"].find({**DON_HOP_LE, "created_at": {"$gte": now - timedelta(days=HISTORY_DAYS), "$lt": now}},
                               {"shop_id": 1, "items": 1, "created_at": 1, "status_history": 1, "financial_breakdown": 1})
    sales = pd.DataFrame([r for o in orders for r in _order_rows(o)], columns=SALES_COLS)
    sales = _dates(sales[sales["product_id"].isin(products["product_id"])], ["ts", "delivered", "estimated"])
    order_ids = [ObjectId(i) for i in sales["order_id"].unique()]
    reviews = pd.DataFrame([[str(r["order_id"]), str(r["product_id"]), r.get("rating"), r.get("created_at")]
                            for r in db["reviews"].find({"order_id": {"$in": order_ids}},
                                                      {"order_id": 1, "product_id": 1, "rating": 1, "created_at": 1})],
                           columns=["order_id", "product_id", "stars", "ts"])
    keys = sales[["order_id", "product_id", "seller_id"]].drop_duplicates()
    rated = _dates(keys.merge(reviews.dropna(subset=["stars"]), on=["order_id", "product_id"]), ["ts"])
    return sales, products, rated[RATED_COLS]
