import numpy as np
import pandas as pd

from app.core.f29 import factors
from scripts.f29_health import learn
from scripts.f29_ml.evaluate import _resamples


def lift(y, s, q: float = 0.2) -> float:
    y, s = np.asarray(y, dtype=float), np.asarray(s, dtype=float)
    low = y[s <= np.quantile(s, q)].mean()
    high = y[s >= np.quantile(s, 1 - q)].mean()
    return float(high / low) if low > 0 else float("inf")


def weight_ranges(sub: pd.DataFrame, y: pd.Series, groups: np.ndarray,
                  n: int = 200, seed: int = 42) -> dict[str, list[int]]:
    draws = [learn.to_weights(learn.fit_coefs(sub.iloc[i], y.iloc[i])) for i in _resamples(groups, n, seed)]
    return {k: np.percentile([w[k] for w in draws], [2.5, 97.5], method="nearest").astype(int).tolist()
            for k in factors.KEYS}


def pair_share(coefs: dict, a: str, b: str) -> tuple[int, int]:
    ca, cb = max(coefs[a], 0.0), max(coefs[b], 0.0)
    share = round(100 * ca / (ca + cb))
    return share, 100 - share
