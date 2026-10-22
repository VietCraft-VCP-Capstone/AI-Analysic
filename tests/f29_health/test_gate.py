import numpy as np
import pandas as pd

from scripts.f29_health.candidates import EQUAL, LEARNED, V1, gate


def _frame(y):
    n = len(y)
    return pd.DataFrame({"top25": y, "source": "tiki23", "group": "bags", "listing_id": np.arange(n),
                         "seller": [f"s{i}" for i in range(n)]})


def test_gate_passes_when_learned_is_not_worse():
    y = np.tile([0, 1], 100)
    noise = np.random.default_rng(1).random(200) * 0.01
    scores = {LEARNED: y + noise, EQUAL: np.random.default_rng(2).random(200), V1: np.random.default_rng(3).random(200)}
    assert gate(_frame(y), scores)["passed"] is True


def test_gate_fails_when_learned_is_clearly_worse():
    y = np.tile([0, 1], 100)
    noise = np.random.default_rng(1).random(200) * 0.01
    scores = {LEARNED: 1 - y + noise, EQUAL: y + noise, V1: y + noise}
    result = gate(_frame(y), scores)
    assert result["passed"] is False and result["vs_equal_ci"][1] < 0
