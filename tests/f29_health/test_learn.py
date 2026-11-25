import pandas as pd

from app.core.f29 import factors
from scripts.f29_health.learn import agreement, pooled, subscores, to_weights


def test_subscores_uses_factor_functions():
    df = pd.DataFrame({
        "photos": [3, None], "desc": [300, 900], "good": [2, 0], "n": [4, 0],
        "pct": [50.0, 95.0],
    })
    targets = {"image": 6, "description": 570, "tags": 3}
    cols = {"image": "photos", "description": "desc", "review": ("good", "n"), "price": "pct"}
    out = subscores(df, cols, targets, {"p0": 0.8, "m": 5})
    assert list(out.columns) == ["image", "description", "review", "price"]
    assert out.loc[0, "image"] == factors.ratio_score(3, 6)
    assert out.loc[1, "image"] == 0
    assert out.loc[0, "description"] == factors.ratio_score(300, 570)
    assert out.loc[0, "review"] == factors.review_score(2, 4, 0.8, 5)
    assert out.loc[1, "review"] == 0
    assert out.loc[0, "price"] == 100.0 and out.loc[1, "price"] == 75.0


def test_blend_moves_from_equal_to_learned_with_floor():
    coefs = {"image": 0.3, "description": 0.1, "review": -0.1, "price": 0.6}
    assert to_weights(coefs, lam=0.0) == {"image": 20, "description": 20, "tags": 20, "review": 20, "price": 20}
    full = to_weights(coefs, lam=1.0)
    assert full["price"] > full["image"] > full["description"] and full["review"] == 10 and sum(full.values()) == 100


def test_agreement_is_one_for_identical_markets():
    a = {"image": 0.2, "price": 0.6}
    assert agreement([a, a], ["image", "price"]) == 1.0
    assert agreement([a, {"image": 0.6, "price": 0.2}], ["image", "price"]) == 0.5


def test_pooled_averages_market_shares():
    out = pooled([{"image": 1.0, "price": 3.0}, {"image": -1.0, "price": 2.0}], ["image", "price"])
    assert out == {"image": 0.125, "price": 0.875}
