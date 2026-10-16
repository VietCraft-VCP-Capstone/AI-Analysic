import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.f29.scoring import (  # noqa: E402
    bayes_shrunk_rating,
    content_axis_score,
    content_component_scores,
    rating_axis_score,
    total_score,
)

BASE = "/home/rio/Documents/CODE/nodejs/vietcraft/preparied-olist-data"
T = pd.Timestamp("2018-01-01")
CUTOFF = pd.Timestamp("2018-08-31")
MONTHS_WINDOW = (CUTOFF - T).days / 30.44  # ~7,95 tháng, cố định cho mọi sản phẩm


def load():
    prod = pd.read_csv(f"{BASE}/olist_products_dataset.csv")
    rev = pd.read_csv(f"{BASE}/olist_order_reviews_dataset.csv")
    items = pd.read_csv(f"{BASE}/olist_order_items_dataset.csv")
    orders = pd.read_csv(f"{BASE}/olist_orders_dataset.csv")
    orders["order_purchase_timestamp"] = pd.to_datetime(orders["order_purchase_timestamp"])
    rev["review_creation_date"] = pd.to_datetime(rev["review_creation_date"])
    return prod, rev, items, orders


class OlistAxes:
    """Chuẩn bị order_items trước/sau T và các hàm chấm trục theo product_id."""

    def __init__(self):
        prod, rev, items, orders = load()
        self.prod = prod.set_index("product_id")
        self.category_of = prod.set_index("product_id")["product_category_name"].to_dict()

        orders_d = orders[orders["order_status"] == "delivered"]
        oi = items.merge(orders_d[["order_id", "order_purchase_timestamp"]], on="order_id")
        self.pre = oi[oi["order_purchase_timestamp"] < T]
        self.post = oi[(oi["order_purchase_timestamp"] >= T) & (oi["order_purchase_timestamp"] <= CUTOFF)]
        self.sales_after_t = self.post.groupby("product_id")["price"].sum() / MONTHS_WINDOW

        # Chỉ review của đơn một sản phẩm mới gán chắc chắn được cho product_id.
        items_d = items[items["order_id"].isin(orders_d["order_id"])]
        n_products = items_d.groupby("order_id")["product_id"].nunique()
        single = items_d[items_d["order_id"].isin(n_products[n_products == 1].index)]
        prod_of_order = single.drop_duplicates("order_id")[["order_id", "product_id"]]
        rev = rev.merge(prod_of_order, on="order_id").dropna(subset=["review_score"])
        rev_pre = rev[rev["review_creation_date"] < T]

        self.platform_mean = float(rev_pre["review_score"].mean())
        self.rating_agg = rev_pre.groupby("product_id")["review_score"].agg(["sum", "count"])

    def rating(self, pid):
        if pid not in self.rating_agg.index:
            return None
        row = self.rating_agg.loc[pid]
        shrunk = bayes_shrunk_rating(float(row["sum"]), int(row["count"]), self.platform_mean)
        return None if shrunk is None else round(rating_axis_score(shrunk), 1)

    def content(self, pid):
        if pid not in self.prod.index:
            return None
        row = self.prod.loc[pid]
        photos, desc_len = row["product_photos_qty"], row["product_description_lenght"]
        comps = content_component_scores(
            None if pd.isna(photos) else float(photos),
            None if pd.isna(desc_len) else float(desc_len),
            None,
        )
        score = content_axis_score(comps)
        return None if score is None else round(score, 1)

    def health(self, rating, content):
        """Ba trục còn lại n/a trên Olist -> engine tự chia lại trọng số."""
        return total_score({"conversion": None, "rating": rating, "content": content,
                            "inventory": None, "freshness": None})
