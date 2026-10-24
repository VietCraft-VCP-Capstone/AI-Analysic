import numpy as np
import pandas as pd

from app.core.f29.scoring import (
    bayes_shrunk_rating,
    content_axis_score,
    content_component_scores,
    rating_axis_score,
    total_score,
)


def _value(v):
    return None if pd.isna(v) else float(v)


def _health(row):
    content = content_axis_score(content_component_scores(_value(row.photos), _value(row.description_length), None))
    shrunk = bayes_shrunk_rating(row.review_sum, int(row.review_count), row.review_prior)
    rating = rating_axis_score(shrunk) if shrunk is not None else None
    return total_score({"content": content, "rating": rating})


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
