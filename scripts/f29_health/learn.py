import math

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

from app.core.f29 import factors
from app.core.f29.price_peers import price_sub

TAG_WEIGHT = 20
FLOOR = 10
TAG_TARGET = 3


def targets(olist_train, tiki_train):
    top_tiki = tiki_train[tiki_train["top25"] == 1]
    top_olist = olist_train[olist_train["top25"] == 1]
    return {
        "image": int(top_tiki["n_images"].median()),
        "description": int(round(top_olist["description_length"].median(), -1)),
        "tags": TAG_TARGET,
    }


def _values(col):
    return col if isinstance(col, tuple) else (col,)


def _apply(fn, cols):
    return np.array([fn(*(None if pd.isna(v) else float(v) for v in row)) for row in zip(*cols)], dtype=float)


def subscores(df, cols, targets, review):
    fns = {
        "image": lambda v: factors.ratio_score(v, targets["image"]),
        "description": lambda v: factors.ratio_score(v, targets["description"]),
        "review": lambda good, n: factors.review_score(good, n, review["p0"], review["m"]),
        "price": lambda pct: price_sub(pct, (), 1.0),
    }
    return pd.DataFrame(
        {k: _apply(fns[k], [df[c] for c in _values(col)]) for k, col in cols.items() if k in fns},
        index=df.index,
    )


def fit_coefs(X, y, controls=None):
    Z = X / 100
    if controls is not None:
        Z = pd.concat([Z, ((controls - controls.mean()) / controls.std().replace(0, 1)).fillna(0)], axis=1)
    model = LogisticRegression(max_iter=1000).fit(Z, y)
    return dict(zip(X.columns, model.coef_[0][:X.shape[1]].tolist()))


def shares(coefs):
    pos = {k: max(c, 0.0) for k, c in coefs.items()}
    total = sum(pos.values())
    return {k: v / total if total else 1 / len(pos) for k, v in pos.items()}


def pooled(market_coefs, keys):
    vecs = [shares({k: c[k] for k in keys}) for c in market_coefs]
    return {k: sum(v[k] for v in vecs) / len(vecs) for k in keys}


def agreement(market_coefs, keys):
    vecs = [shares({k: c[k] for k in keys}) for c in market_coefs]
    gaps = [0.5 * sum(abs(a[k] - b[k]) for k in keys) for i, a in enumerate(vecs) for b in vecs[i + 1:]]
    return round(1 - float(np.mean(gaps)), 3)


def _shares(coefs, budget, floor):
    free = dict(coefs)
    while True:
        left = budget - floor * (len(coefs) - len(free))
        total = sum(free.values())
        exact = ({k: left * c / total for k, c in free.items()} if total > 0
                 else {k: left / len(free) for k in free})
        low = [k for k, v in exact.items() if v < floor]
        if not low:
            return exact | {k: floor for k in coefs if k not in free}
        for k in low:
            del free[k]


def _round(exact, budget):
    out = {k: math.floor(v) for k, v in exact.items()}
    extra = budget - sum(out.values())
    for k in sorted(exact, key=lambda k: (exact[k] - out[k], exact[k]), reverse=True)[:extra]:
        out[k] += 1
    return out


def to_weights(coefs, lam=1.0, tag=TAG_WEIGHT, floor=FLOOR):
    budget, learned = 100 - tag, shares(coefs)
    blended = {k: lam * learned[k] + (1 - lam) / len(coefs) for k in coefs}
    merged = _round(_shares(blended, budget, floor), budget) | {"tags": tag}
    return {k: merged[k] for k in factors.KEYS}
