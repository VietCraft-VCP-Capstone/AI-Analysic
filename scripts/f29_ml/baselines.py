import numpy as np
import pandas as pd

WEIGHTS_V1 = {"content": 0.20, "rating": 0.25}


def _value(v):
    return None if pd.isna(v) else float(v)


def _health(row):
    photos = _value(row.photos)
    desc = _value(row.description_length)
    comps = {}
    if photos is not None:
        comps["images"] = min(100.0, max(0.0, photos / 5.0 * 100.0))
    if desc is not None:
        comps["description"] = min(100.0, max(0.0, desc / 150.0 * 100.0))
    content = (sum(comps.values()) / len(comps)) if comps else None

    n = int(row.review_count)
    if n > 0:
        shrunk = (row.review_sum + 50 * row.review_prior) / (n + 50)
        rating = min(100.0, max(0.0, (shrunk - 1.0) / 4.0 * 100.0))
    else:
        rating = None

    valid = {k: v for k, v in [("content", content), ("rating", rating)] if v is not None}
    if not valid:
        return 0.0
    tot_w = sum(WEIGHTS_V1[k] for k in valid)
    return round(sum(valid[k] * WEIGHTS_V1[k] / tot_w for k in valid), 1)


def health_v1(df):
    return df.apply(_health, axis=1).fillna(0.0).to_numpy()


def popularity(df):
    return df["log_sales_90d"].to_numpy()


def random_score(df, seed=42):
    return np.random.default_rng(seed).random(len(df))


def recency(df):
    return -df["days_since_last"].to_numpy()


BASELINES = {
    "Ngẫu nhiên": random_score,
    "health-1.0 (luật hiện tại)": health_v1,
    "Bán nhiều 90 ngày qua": popularity,
    "Đơn gần nhất": recency,
}
