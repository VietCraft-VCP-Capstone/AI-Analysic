import math

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

from app.core.f29 import factors

FIXED = {"tags": 10, "material": 10}
FLOOR = 5
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


def subscores(df, cols, targets, review, price):
    fns = {
        "image": lambda v: factors.ratio_score(v, targets["image"]),
        "description": lambda v: factors.ratio_score(v, targets["description"]),
        "review": lambda good, n: factors.review_score(good, n, review["p0"], review["m"]),
        "price": lambda p, ref: factors.price_score(p, ref, price["full_at"], price["zero_at"]),
    }
    return pd.DataFrame(
        {k: _apply(fns[k], [df[c] for c in _values(col)]) for k, col in cols.items() if k in fns},
        index=df.index,
    )


def fit_coefs(X, y):
    model = LogisticRegression(max_iter=1000).fit(X / 100, y)
    return dict(zip(X.columns, model.coef_[0].tolist()))


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


def to_weights(coefs, fixed=FIXED, floor=FLOOR):
    budget = 100 - sum(fixed.values())
    learned = _round(_shares({k: max(c, 0.0) for k, c in coefs.items()}, budget, floor), budget)
    merged = fixed | learned
    return {k: merged[k] for k in factors.KEYS}
