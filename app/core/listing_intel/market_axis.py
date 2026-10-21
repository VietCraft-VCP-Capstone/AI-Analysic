import numpy as np


class KnnIndex:
    def __init__(self, vecs, prices, top):
        self.vecs = np.asarray(vecs, dtype=np.float32)
        self.prices = np.asarray(prices, dtype=np.float64)
        self.top = np.asarray(top).astype(bool)


def knn_features(vec, price, index, k=20, dup_cos=0.92, exclude=None):
    nan = float("nan")
    drop = np.unique(np.atleast_1d(exclude if exclude is not None else []).astype(int))
    n = len(index.vecs) - len(drop)
    if n <= 0:
        return {"knn_price_pct": nan, "knn_dup_count": 0.0, "knn_median_price": nan}
    sims = index.vecs @ np.asarray(vec, dtype=np.float32)
    sims[drop] = -np.inf
    k = min(k, n)
    near = np.argpartition(-sims, k - 1)[:k]
    prices = index.prices[near]
    prices = prices[~np.isnan(prices)]
    known = prices.size > 0
    has_price = price is not None and not np.isnan(price)
    return {
        "knn_price_pct": 100.0 * float(np.mean(prices <= price)) if known and has_price else nan,
        "knn_dup_count": float((sims[near] > dup_cos).sum()),
        "knn_median_price": float(np.median(prices)) if known else nan,
    }


def _unit(a):
    n = np.linalg.norm(a, axis=-1, keepdims=True)
    return a / np.where(n == 0, 1.0, n)


def _margin(vecs, top_centroid, rest_centroid):
    return _unit(np.asarray(vecs, dtype=np.float64)) @ (_unit(top_centroid) - _unit(rest_centroid))


def centroids(vecs, top):
    vecs = np.asarray(vecs, dtype=np.float64)
    top = np.asarray(top).astype(bool)
    return _unit(vecs[top].mean(axis=0)), _unit(vecs[~top].mean(axis=0))


def centroid_margin(vec, top_centroid, rest_centroid):
    return float(_margin(vec, top_centroid, rest_centroid))


def oof_centroid_margin(vecs, top, folds):
    vecs = np.asarray(vecs, dtype=np.float64)
    top = np.asarray(top).astype(bool)
    folds = np.asarray(folds)
    out = np.full(len(vecs), np.nan)
    for fold in np.unique(folds):
        held = folds == fold
        fit = ~held
        if not (top & fit).any() or not (~top & fit).any():
            continue
        top_c, rest_c = centroids(vecs[fit], top[fit])
        out[held] = _margin(vecs[held], top_c, rest_c)
    return out
