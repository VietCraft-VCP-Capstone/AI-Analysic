import math

import numpy as np

from scripts.f29_ml.evaluate import delta_ci, score_all, within_category_auc


def test_within_category_auc_is_nan_when_no_category_qualifies():
    assert math.isnan(within_category_auc(np.array([0, 1]), np.array([0.1, 0.9]), np.array(["a", "a"])))


def test_perfect_scores_beat_random_with_positive_delta():
    rng = np.random.default_rng(0)
    y = rng.integers(0, 2, 400)
    groups = np.arange(400) % 40
    good, noise = y + rng.random(400) * 0.1, rng.random(400)
    assert score_all(y, good, np.array(["c"] * 400), groups)["roc_auc"] == 1.0
    low, high = delta_ci(y, good, noise, groups)
    assert 0 < low <= high
