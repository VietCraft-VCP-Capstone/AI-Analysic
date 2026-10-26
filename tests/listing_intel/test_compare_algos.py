import numpy as np
import pandas as pd

from scripts.li.compare_algos import FULL, candidates, dev_rows
from scripts.li.fit import frame


def synthetic(n=60):
    rng = np.random.default_rng(0)
    df = pd.DataFrame(rng.normal(size=(n, len(FULL) - 1)), columns=[c for c in FULL if c != "group"])
    df["group"] = ["fashion", "bags", "unknown", None, "home", "sport"] * (n // 6)
    df["split"] = ["train", "val", "test"] * (n // 3)
    df["top25"] = rng.integers(0, 2, n)
    df.iloc[::4, 0] = np.nan
    return df


def test_dev_rows_drops_test():
    assert set(dev_rows(synthetic())["split"]) == {"train", "val"}


def test_candidates_handle_nan_and_unknown_group():
    df = dev_rows(synthetic())
    X = frame(df, FULL)
    for make in candidates().values():
        proba = make().fit(X, df["top25"]).predict_proba(X)[:, 1]
        assert len(proba) == len(df) and not np.isnan(proba).any()
