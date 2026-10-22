import pandas as pd

from app.core.f29 import factors
from scripts.f29_health.learn import subscores, to_weights


def test_to_weights_proportional_with_floor():
    w = to_weights({"image": 0.27, "description": 0.12, "review": -0.03, "price": 0.44})
    assert list(w) == ["image", "description", "tags", "review", "price"]
    assert sum(w.values()) == 100 and w["tags"] == 10 and w["review"] == 5
    assert w["price"] > w["image"] > w["description"] >= 5


def test_to_weights_all_zero_is_equal():
    w = to_weights({"image": 0, "description": -1, "review": 0, "price": 0})
    assert sum(w.values()) == 100 and w["tags"] == 10
    assert max(w[k] for k in ("image", "description", "review", "price")) - min(w[k] for k in ("image", "description", "review", "price")) <= 1


def test_subscores_uses_factor_functions():
    df = pd.DataFrame({
        "photos": [3, None], "desc": [300, 900], "good": [2, 0], "n": [4, 0],
        "price": [100.0, 150.0], "ref": [100.0, 100.0],
    })
    targets = {"image": 6, "description": 570, "tags": 3}
    cols = {"image": "photos", "description": "desc", "review": ("good", "n"), "price": ("price", "ref")}
    out = subscores(df, cols, targets, {"p0": 0.8, "m": 5}, {"full_at": 1.0, "zero_at": 2.0})
    assert list(out.columns) == ["image", "description", "review", "price"]
    assert out.loc[0, "image"] == factors.ratio_score(3, 6)
    assert out.loc[1, "image"] == 0
    assert out.loc[0, "description"] == factors.ratio_score(300, 570)
    assert out.loc[0, "review"] == factors.review_score(2, 4, 0.8, 5)
    assert out.loc[1, "review"] == 0
    assert out.loc[1, "price"] == factors.price_score(150.0, 100.0, 1.0, 2.0)
