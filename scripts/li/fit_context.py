import json
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.decomposition import PCA
from sklearn.model_selection import GroupKFold

from app.core.listing_intel.context import FeatureContext, prompt_texts
from app.core.listing_intel.embedder import embed_texts
from app.core.listing_intel.features import PCA_DIM, market_vec
from app.core.listing_intel.lift import lift_table
from app.core.listing_intel.market_axis import KnnIndex, centroids
from app.core.listing_intel.trend_store import weekly_series
from scripts.li import paths

KEYWORDS = Path(__file__).resolve().parents[2] / "app/core/listing_intel/data/trend_keywords.json"
N_FOLDS = 5
TREND_MATCH_COS = None
WEEK0_THURSDAY = date(2023, 1, 5)


def group_season(monthly: pd.DataFrame) -> dict[str, np.ndarray]:
    if monthly.empty:
        return {}
    months = [(WEEK0_THURSDAY + timedelta(weeks=w)).month for w in range(52)]
    table = monthly.pivot(index="group", columns="month", values="index")
    return {g: table.loc[g, months].to_numpy(float) for g in table.index}


def seller_keys(df: pd.DataFrame) -> np.ndarray:
    return np.array([f"row:{i}" if s is None else f"{src}:{s}" for i, src, s in zip(df.index, df["source"], df["seller"])])


def seller_folds(df: pd.DataFrame, train: np.ndarray) -> np.ndarray:
    keys = seller_keys(df)
    folds = np.full(len(df), -1)
    idx = np.flatnonzero(train)
    for k, (_, held) in enumerate(GroupKFold(N_FOLDS).split(idx, groups=keys[idx])):
        folds[idx[held]] = k
    return folds


def _embed(texts: dict[str, str]) -> dict[str, np.ndarray]:
    return dict(zip(texts, embed_texts(list(texts.values()))))


def _centroids(vecs, top, groups, mask) -> dict:
    out = {}
    for g in np.unique(groups[mask]):
        m = mask & (groups == g)
        if top[m].any() and (~top[m]).any():
            out[str(g)] = centroids(vecs[m], top[m])
    return out


def _knn(vecs, price, top, groups, mask, keys) -> tuple[dict, dict]:
    index, pos = {}, {}
    for g in np.unique(groups[mask]):
        rows = np.flatnonzero(mask & (groups == g))
        index[str(g)] = KnnIndex(vecs[rows].astype(np.float16), price[rows], top[rows])
        same = pd.Series(np.arange(len(rows))).groupby(keys[rows]).indices
        pos.update({int(r): same[keys[r]] for r in rows})
    return index, pos


def fit_context(df: pd.DataFrame, txt: np.ndarray, img: np.ndarray):
    train = (df["split"] == "train").to_numpy()
    groups, top = df["group"].to_numpy(str), df["top25"].to_numpy(bool)
    price, titles = df["price"].to_numpy(float), df["title"].to_numpy(str)
    has = ~np.isnan(img[:, 0])
    mvec = np.full_like(img, np.nan)
    mvec[has] = market_vec(img[has], txt[has])
    knn, pos = _knn(mvec, price, top, groups, train & has, seller_keys(df))
    median = df[train].groupby("group")["price"].median().astype(float).to_dict()
    keywords = json.loads(KEYWORDS.read_text("utf-8"))
    series = weekly_series()
    ctx = FeatureContext(
        lift=lift_table(titles[train], groups[train], top[train]),
        group_median_price={**median, "all": float(np.median(price[train]))},
        pca=PCA(PCA_DIM, random_state=42).fit(img[train & has].astype(np.float64)),
        prompt_vecs=_embed(prompt_texts()),
        knn=knn,
        trend_series=series,
        trend_kw_vecs=_embed({k: k for k in keywords}),
        group_season=group_season(pd.read_parquet(paths.clean("tikireviews_monthly.parquet"))),
        centroids=_centroids(mvec, top, groups, train & has),
        trend_match_cos=TREND_MATCH_COS,
        trend_keywords=[k for k in keywords if k in series],
    )
    folds = seller_folds(df, train)
    fold_ctx = {}
    for k in range(N_FOLDS):
        fit = train & (folds != k)
        fold_ctx[k] = replace(ctx, lift=lift_table(titles[fit], groups[fit], top[fit]),
                              centroids=_centroids(mvec, top, groups, fit & has))
    return ctx, fold_ctx, folds, pos
