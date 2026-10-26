import numpy as np
import pandas as pd

from scripts.f29_health.candidates import EQUAL, LEARNED, gate

MARKETS = ("olist_test", "tiki_test", "shopee_test")
Y = np.tile([0, 1], 100)


def _frame(y):
    n = len(y)
    return pd.DataFrame({"top25": y, "source": "tiki23", "group": "bags", "listing_id": np.arange(n),
                         "seller": [f"s{i}" for i in range(n)]})


def _good(seed):
    rng = np.random.default_rng(seed)
    return _frame(Y), {LEARNED: Y + rng.random(200) * 0.01, EQUAL: rng.random(200)}


def test_gate_passes_when_learned_is_not_worse():
    sets = {m: _good(i) for i, m in enumerate(MARKETS)}
    assert gate(sets)["passed"] is True


def test_gate_fails_when_learned_is_clearly_worse():
    noise = np.random.default_rng(1).random(200) * 0.01
    sets = {m: (_frame(Y), {LEARNED: 1 - Y + noise, EQUAL: Y + noise}) for m in MARKETS}
    result = gate(sets)
    assert result["passed"] is False and result["per_market"]["tiki_test"]["vs_equal_ci"][1] < 0


def test_gate_requires_both_markets():
    rng = np.random.default_rng(2)
    bad = (_frame(Y), {LEARNED: Y + rng.normal(0, 0.8, 200), EQUAL: Y + rng.random(200) * 0.01})
    sets = {"olist_test": _good(0), "tiki_test": _good(1), "shopee_test": bad}
    result = gate(sets)
    assert result["passed"] is False and result["per_market"]["tiki_test"]["vs_equal_ci"][1] >= 0
    assert result["per_market"]["shopee_test"]["vs_equal_ci"][1] < 0


def test_gate_requires_lift():
    y = np.zeros(200)
    y[0:40:2] = 1
    y[160:182] = 1
    sets = {"olist_test": (_frame(y), {LEARNED: np.arange(200.0), EQUAL: np.arange(200.0)}),
            "tiki_test": _good(1), "shopee_test": _good(2)}
    result = gate(sets)
    assert result["passed"] is False and abs(result["per_market"]["olist_test"]["lift"] - 1.1) < 1e-9
