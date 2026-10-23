import numpy as np
import pandas as pd

from scripts.f29_health import evidence, learn


def test_lift_ratio():
    y = np.zeros(20)
    y[[0, 16, 17]] = 1
    assert evidence.lift(y, np.arange(20)) == 2.0


def test_lift_zero_low_group():
    y = np.zeros(20)
    y[19] = 1
    assert evidence.lift(y, np.arange(20)) == float("inf")


def test_weight_ranges_contain_point_estimate():
    rng = np.random.default_rng(1)
    n = 2000
    sub = pd.DataFrame(rng.uniform(0, 100, (n, 4)), columns=["image", "description", "review", "price"])
    y = pd.Series((rng.random(n) < 1 / (1 + np.exp(2 - sub.sum(axis=1) / 50))).astype(int))
    ranges = evidence.weight_ranges(sub, y, np.arange(n) % 200)
    point = learn.to_weights(learn.fit_coefs(sub, y))
    assert all(lo <= point[k] <= hi for k, (lo, hi) in ranges.items())
    assert ranges["tags"] == [10, 10]


def test_pair_share():
    assert evidence.pair_share({"image": 0.19, "price": 0.421}, "image", "price") == (31, 69)
