import pytest

from app.core.f29.breakdown import score


def _f(state, points=0.0):
    return {"key": "x", "state": state, "points": points, "weight": 20}


def test_score_counts_scored_and_seller_missing_only():
    rows = [_f("scored", 20), _f("seller_missing"), _f("not_applicable"), _f("technical_failure"), _f("scored", 10)]
    assert score(rows) == (50.0, {"evaluated": 3, "total": 5})


def test_all_excluded_scores_zero():
    assert score([_f("not_applicable"), _f("technical_failure")]) == (0.0, {"evaluated": 0, "total": 2})


@pytest.mark.parametrize("points,expected", [((20, 20, 20, 20, 20), 100.0), ((20, 20, 20, 0, 0), 60.0)])
def test_equal_weights(points, expected):
    value, _ = score([_f("scored", p) for p in points])
    assert value == expected
