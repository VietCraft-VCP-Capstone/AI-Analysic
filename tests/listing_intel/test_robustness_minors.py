import threading
import time
import warnings

import numpy as np
import pandas as pd
import pytest

from app.api.v1 import f29_intel
from app.api.v1._template import STATUS_INSUFFICIENT
from app.core.listing_intel import fusion
from app.core.listing_intel import trend_store as ts
from app.core.listing_intel.lift import lift_table
from app.core.listing_intel.market_axis import centroids


def test_run_returns_no_model_when_bundle_is_corrupt(monkeypatch):
    def corrupt():
        raise EOFError("truncated bundle")

    monkeypatch.setattr(fusion, "load_bundle", corrupt)
    out = f29_intel._run(lambda: {"x": 1}, "shop", "s1")
    assert out["data"] is None
    assert out["meta"]["status"] == STATUS_INSUFFICIENT
    assert out["meta"]["reason"] == f29_intel.NO_MODEL


def test_weekly_series_loads_once_under_concurrent_calls(monkeypatch):
    calls = []

    def slow_load():
        calls.append(1)
        time.sleep(0.05)
        return {"k": pd.Series([1.0])}

    monkeypatch.setattr(ts, "_load", slow_load)
    monkeypatch.setitem(ts._cache, "data", None)
    barrier = threading.Barrier(8)

    def call():
        barrier.wait()
        ts.weekly_series()

    threads = [threading.Thread(target=call) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(calls) == 1


def test_lift_table_rejects_mismatched_lengths():
    with pytest.raises(ValueError):
        lift_table(["túi da bò"] * 3, ["bags"] * 3, [1, 0])


def test_centroids_all_top_has_nan_rest_without_warning():
    vecs = np.array([[1.0, 0.0], [0.0, 1.0], [1.0, 1.0]])
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        top_c, rest_c = centroids(vecs, [1, 1, 1])
    mean = vecs.mean(axis=0)
    assert np.allclose(top_c, mean / np.linalg.norm(mean))
    assert rest_c.shape == (2,) and np.isnan(rest_c).all()
