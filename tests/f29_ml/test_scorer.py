from app.core.f29.ml.features import ACTIONABLE, snapshot
from app.core.f29.ml.scorer import MIN_GAIN, NO_SALES, score_frame
from tests.f29_ml.samples import T, sale, tables


def _market():
    sales = []
    for i in range(6):
        sales += [sale(f"o{i}-{k}", f"p{i}", seller=f"s{i % 2}", at=-5 - k * (i + 1), price=100 + 20 * i)
                  for k in range(1 + i * 2)]
    return snapshot(*tables(sales), T)


def test_score_is_a_percentile_within_peers():
    result = score_frame(_market(), "p5")
    assert 0 <= result["score"] <= 100
    assert 0 < result["probability"] < 1
    assert result["peer_group"] == {"type": "category", "name": "cat", "size": 6}


def test_advice_only_lists_actionable_changes_with_real_gain():
    for p in [f"p{i}" for i in range(6)]:
        for a in score_frame(_market(), p)["advice"]:
            assert a["feature"] in ACTIONABLE
            assert a["gain"] >= MIN_GAIN


def test_unknown_listing_returns_reason():
    assert score_frame(_market(), "missing") == NO_SALES


def test_too_few_peers_returns_reason():
    df = _market()
    assert isinstance(score_frame(df[df["product_id"].isin(["p0", "p1"])], "p0"), str)


def test_no_advice_for_groups_without_measured_lift(monkeypatch):
    from app.core.f29.ml import scorer

    clf, meta = scorer.load_model()
    weak = {**meta, "group_lift": {g: 0.0 for g in meta["group_lift"]}}
    monkeypatch.setattr(scorer, "load_model", lambda: (clf, weak))
    assert all(not score_frame(_market(), f"p{i}")["advice"] for i in range(6))
