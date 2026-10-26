import numpy as np
import pandas as pd

from app.core.f29.ml import features
from scripts.li.labels import top25
from scripts.li.paths import clean

KEY = ["product_id", "seller_id"]
GOOD_STARS = 4
TIKI_FILE = "tiki23.parquet"
MIN_PEERS = 8


def _leave_self_out(prices):
    s = np.sort(prices)
    if len(s) <= MIN_PEERS:
        return np.full(len(prices), np.nan)
    return np.array([np.median(np.delete(s, np.searchsorted(s, p))) for p in prices])


def _loo(prices):
    return pd.Series(_leave_self_out(prices.to_numpy()), index=prices.index)


def _price_ref(df):
    by_category = df.groupby("category")["price"].transform(_loo)
    return by_category.fillna(_loo(df["price"]))


def _reviews_before(tables, t):
    sales, _, rated = tables
    past = sales[sales["ts"] < t]
    return rated[(rated["ts"] < t) & rated["order_id"].isin(past["order_id"])]


def _snapshot(tables, t):
    df = features.snapshot(*tables, t)
    good = _reviews_before(tables, t)
    good = good[good["stars"] >= GOOD_STARS].groupby(KEY).size().rename("review_good").reset_index()
    df = df.merge(good, on=KEY, how="left")
    df["review_good"] = df["review_good"].fillna(0).astype(int)
    df["review_n"] = df["review_count"]
    df["price_ref"] = _price_ref(df)
    return df


def olist(tables, cutoffs):
    df = pd.concat([_snapshot(tables, pd.Timestamp(t)) for t in cutoffs], ignore_index=True)
    df["top25"] = top25(df.assign(fs=df["future_sales"].fillna(0)), "fs", ["cutoff", "category"])
    return df


def olist_p0(tables, cutoffs):
    reviews = _reviews_before(tables, pd.Timestamp(max(cutoffs)))
    return float((reviews["stars"] >= GOOD_STARS).mean())


def tiki(split):
    raw = pd.read_parquet(clean(TIKI_FILE))
    df = raw[raw["split"] == split].copy()
    df["desc_len"] = df["description"].fillna("").str.len()
    if split == "train":
        df["price_ref"] = df.groupby("group")["price"].transform(_loo)
    else:
        df["price_ref"] = df["group"].map(raw[raw["split"] == "train"].groupby("group")["price"].median())
    return df
