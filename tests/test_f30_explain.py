import numpy as np

from app.services.f30.explain import top_listings
from app.services.f30.rules import WINDOW


def _series(level: float, today: float) -> np.ndarray:
    arr = np.full(WINDOW + 1, level, dtype=float)
    arr[-1] = today
    return arr


def test_drop_puts_strongest_first_and_skips_spikes():
    t = WINDOW
    per = {
        "a": _series(100, 50),   # drop 50
        "b": _series(100, 90),   # drop 10
        "c": _series(100, 200),  # spike, must be excluded
    }
    titles = {"a": "Váy A", "b": "Váy B", "c": "Váy C"}

    rows = top_listings(per, titles, t, "drop", listing_prefix="live_")

    assert [r["listing_id"] for r in rows] == ["live_a", "live_b"]
    assert rows[0] == {
        "listing_id": "live_a", "title": "Váy A",
        "expected": 100, "actual": 50, "change_pct": -50.0,
    }


def test_spike_keeps_only_increases():
    t = WINDOW
    per = {"a": _series(100, 50), "c": _series(100, 200)}

    rows = top_listings(per, {}, t, "spike")

    assert [r["listing_id"] for r in rows] == ["c"]
    assert rows[0]["change_pct"] == 100.0
    assert rows[0]["title"] == ""


def test_zero_expected_gives_none_change_pct():
    t = WINDOW
    per = {"a": _series(0, 5)}

    rows = top_listings(per, {}, t, "spike")

    assert rows[0]["change_pct"] is None
