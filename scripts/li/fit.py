import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier

from app.core.calendar_vn import ALL_GROUPS
from app.core.listing_intel import features as F

AXES = {"image": F.IMAGE_COLS, "text": F.TEXT_COLS, "market": F.MARKET_COLS, "trend": F.TREND_COLS}
AXIS_MODELS = ("image", "text", "market")
FULL = F.FEATURE_COLS + ["group"]
AXIS_PARAMS = {"image": {"max_depth": 4, "min_samples_leaf": 40, "l2_regularization": 1.0, "max_iter": 10,
                         "early_stopping": False}}


def hgb(**params):
    return HistGradientBoostingClassifier(**({"learning_rate": 0.05, "max_iter": 400, "random_state": 42} | params))


def axis_cols(axis):
    return AXES[axis] + ["group"]


def without(axis):
    return [c for c in FULL if c not in AXES[axis]]


def frame(df, cols):
    X = df[cols].copy()
    if "group" in cols:
        g = df["group"].astype(object)
        X["group"] = pd.Categorical(g.where(g.isin(ALL_GROUPS)), categories=ALL_GROUPS)
    return X


def fit(df, cols, y=None, **params):
    return hgb(**params).fit(frame(df, cols), df["top25"] if y is None else y)


def predict(model, df, cols):
    return model.predict_proba(frame(df, cols))[:, 1]


def defined(df, axis):
    return df[df[AXES[axis]].notna().any(axis=1)]
