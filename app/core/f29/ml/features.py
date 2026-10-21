import numpy as np
import pandas as pd

KEY = ["product_id", "seller_id"]
LOOKBACK, ACTIVE, HORIZON, PRIOR_M = 90, 180, 90, 5
GROUPS = {
    "history": ["log_sales_90d", "log_sales_180d", "days_since_last"],
    "price": ["log_price", "log_price_rel", "freight_ratio"],
    "content": ["photos", "description_length", "name_length"],
    "reviews": ["log_reviews", "rating", "low_star_share"],
    "seller": ["log_seller_sales", "log_seller_listings", "seller_rating", "seller_late_rate", "seller_ship_days"],
    "physical": ["log_weight", "log_volume"],
}
NUMERIC = [f for cols in GROUPS.values() for f in cols]
PORTABLE = [f for f in NUMERIC if f not in ("log_price", "seller_late_rate")]
ACTIONABLE = {
    "photos": 1, "description_length": 1, "name_length": 1,
    "log_price_rel": -1, "seller_ship_days": -1,
}
LOGS = {
    "log_sales_90d": "sales_90d",
    "log_sales_180d": "sales_180d",
    "log_reviews": "review_count",
    "log_seller_sales": "seller_sales",
    "log_seller_listings": "seller_listings",
    "log_weight": "weight_g",
}


def _before(t, days):
    return t - pd.Timedelta(days=days)


def _listings(past, t):
    recent = past[past["ts"] >= _before(t, ACTIVE)]
    df = recent.groupby(KEY).agg(sales_180d=("ts", "size"), price=("price", "median"), freight=("freight_value", "median"))
    df["sales_90d"] = recent[recent["ts"] >= _before(t, LOOKBACK)].groupby(KEY).size().reindex(df.index, fill_value=0)
    df["days_since_last"] = (t - past.groupby(KEY)["ts"].max().reindex(df.index)).dt.days
    return df.reset_index(), recent


def _reviews(reviews):
    marked = reviews.assign(low=reviews["stars"] <= 2)
    return marked.groupby(KEY).agg(
        review_count=("stars", "count"), review_sum=("stars", "sum"), low_star_share=("low", "mean")
    ).reset_index()


def _sellers(past, recent, reviews, prior, t):
    s = recent.groupby("seller_id").agg(seller_sales=("ts", "size"), seller_listings=("product_id", "nunique"))
    done = past[past["delivered"] < t].drop_duplicates(["order_id", "seller_id"])
    s["seller_late_rate"] = (done["delivered"].dt.normalize() > done["estimated"]).groupby(done["seller_id"]).mean()
    s["seller_ship_days"] = ((done["delivered"] - done["ts"]).dt.total_seconds() / 86400).groupby(done["seller_id"]).median()
    g = reviews.drop_duplicates(["order_id", "seller_id"]).groupby("seller_id")["stars"]
    s["seller_rating"] = (g.sum() + PRIOR_M * prior) / (g.count() + PRIOR_M)
    s["seller_rating"] = s["seller_rating"].fillna(prior)
    return s.reset_index()


def _derive(df, prior):
    df["review_count"] = df["review_count"].fillna(0)
    df["review_sum"] = df["review_sum"].fillna(0)
    df["review_prior"] = prior
    df["rating"] = (df["review_sum"] + PRIOR_M * prior) / (df["review_count"] + PRIOR_M)
    for new, col in LOGS.items():
        df[new] = np.log1p(df[col])
    df["log_volume"] = np.log1p(df["length_cm"] * df["height_cm"] * df["width_cm"])
    df["log_price"] = np.log(df["price"])
    df["log_price_rel"] = np.log(df["price"] / df.groupby("category")["price"].transform("median"))
    df["freight_ratio"] = df["freight"] / df["price"]
    return df


def snapshot(sales, products, rated, t):
    t = pd.Timestamp(t)
    past = sales[sales["ts"] < t]
    reviews = rated[(rated["ts"] < t) & rated["order_id"].isin(past["order_id"])]
    prior = float(reviews["stars"].mean())
    df, recent = _listings(past, t)
    df = df.merge(_reviews(reviews), on=KEY, how="left")
    df = df.merge(_sellers(past, recent, reviews, prior, t), on="seller_id", how="left")
    df = _derive(df.merge(products, on="product_id", how="left"), prior)
    future = sales[(sales["ts"] >= t) & (sales["ts"] < t + pd.Timedelta(days=HORIZON))]
    sold = future.groupby(KEY).size().rename("future_sales").reset_index()
    df = df.merge(sold, on=KEY, how="left")
    df["label"] = df["future_sales"].fillna(0).gt(0).astype(int)
    df["cutoff"] = t
    return df
