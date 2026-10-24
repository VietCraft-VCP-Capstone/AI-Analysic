import numpy as np
import pytest

from app.core.listing_intel.lift import lift_table
from app.core.listing_intel.market_axis import (
    KnnIndex,
    centroid_margin,
    centroids,
    knn_features,
    oof_centroid_margin,
)
from app.core.listing_intel.tags_axis import tag_report


def unit(m):
    return m / np.linalg.norm(m, axis=-1, keepdims=True)


def test_lift_positive_for_top_terms():
    titles = ["túi da bò nữ"] * 20 + ["túi vải nữ"] * 20
    top = [1] * 20 + [0] * 20
    lift = lift_table(titles, ["bags"] * 40, top, min_count=5)
    assert lift["bags"]["da bò"] > 0
    assert lift["bags"]["vải"] < 0


def test_lift_respects_min_count():
    titles = ["túi da bò nữ"] * 37 + ["túi hiếm lạ"] * 3
    lift = lift_table(titles, ["bags"] * 40, [1, 0] * 20)
    assert "túi" in lift["bags"]
    assert "hiếm" not in lift["bags"]


def test_lift_neutral_term_not_biased_by_singleton_tail():
    titles = [f"{'áo' if i % 2 == 0 else 'quần'} w{i}" for i in range(200)]
    top = [1 if (i // 2) % 2 == 0 else 0 for i in range(200)]
    lift = lift_table(titles, ["fashion"] * 200, top, min_count=20)
    assert set(lift["fashion"]) == {"áo", "quần"}
    assert abs(lift["fashion"]["áo"]) < 0.15
    assert abs(lift["fashion"]["quần"]) < 0.15


def make_index():
    rng = np.random.default_rng(0)
    dup = unit(rng.normal(size=(1, 64)))
    vecs = np.vstack([np.repeat(dup, 5, axis=0), unit(rng.normal(size=(15, 64)))])
    prices = np.arange(1, 21, dtype=float) * 1000
    return dup[0], KnnIndex(vecs.astype(np.float16), prices, np.zeros(20))


def test_knn_dup_count():
    dup, index = make_index()
    assert index.vecs.dtype == np.float32
    assert knn_features(dup, 5000.0, index)["knn_dup_count"] == 5


def test_knn_exclude_skips_own_row():
    dup, index = make_index()
    feats = knn_features(dup, 1000.0, index, exclude=0)
    assert feats["knn_dup_count"] == 4
    single = KnnIndex(index.vecs[:1], index.prices[:1], index.top[:1])
    assert knn_features(dup, 1000.0, single, exclude=0)["knn_dup_count"] == 0


def test_knn_exclude_drops_whole_seller():
    dup, index = make_index()
    assert knn_features(dup, 1000.0, index, exclude=[0, 1, 1])["knn_dup_count"] == 3
    assert knn_features(dup, 1000.0, index, exclude=range(len(index.vecs)))["knn_dup_count"] == 0


def test_knn_price_pct():
    dup, index = make_index()
    feats = knn_features(dup, 20000.0, index)
    assert feats["knn_price_pct"] == 100
    assert feats["knn_median_price"] == 10500.0
    assert knn_features(dup, 500.0, index)["knn_price_pct"] == 0


def test_oof_margin_excludes_own_fold():
    rng = np.random.default_rng(1)
    vecs = unit(rng.normal(size=(60, 16)))
    top = rng.integers(0, 2, size=60)
    folds = np.arange(60) % 3
    extreme = unit(np.ones((1, 16)))
    all_vecs = np.vstack([vecs, extreme])
    all_top = np.append(top, 1)
    all_folds = np.append(folds, 0)
    with_extreme = oof_centroid_margin(all_vecs, all_top, all_folds)
    without = oof_centroid_margin(vecs, top, folds)
    fit = folds != 0
    expected = centroid_margin(extreme[0], *centroids(vecs[fit], top[fit]))
    assert with_extreme[-1] == pytest.approx(expected)
    assert np.allclose(with_extreme[:60][folds == 0], without[folds == 0])
    assert not np.allclose(with_extreme[:60][folds == 1], without[folds == 1])


def test_tag_duplicate_and_pending():
    lift = {"fashion": {"len": 0.5}}
    _, verdicts, _ = tag_report(
        ["Len", "len", "vintage"], "áo len nữ", "fashion", lift, set(), {"vintage"}, None, None
    )
    assert [v["verdict"] for v in verdicts] == ["keep", "duplicate", "pending"]
    assert all(v["reason"] for v in verdicts)


def test_tag_weak_unless_trending_and_suggestions():
    lift = {"fashion": {"xấu": -0.5, "da bò": 1.0, "len": 0.5, "áo len": 0.8, "thun": 0.6}}
    _, verdicts, sugg = tag_report(
        ["xấu", "len"], "áo len nữ", "fashion", lift, set(), set(), None, None
    )
    assert [v["verdict"] for v in verdicts] == ["weak", "keep"]
    assert [s["tag"] for s in sugg] == ["da bò", "thun"]
    _, verdicts, _ = tag_report(["xấu"], "áo", "fashion", lift, {"xấu"}, set(), None, None)
    assert verdicts[0]["verdict"] == "keep"


def test_tag_score_formula():
    vec = unit(np.ones(4))
    lift = {"bags": {"da bò": 2.0}}
    score, _, _ = tag_report(["da bò"], "túi", "bags", lift, {"da bò"}, set(), [vec], vec)
    assert score == pytest.approx(0.35 + 0.25 + 0.20 + 0.20 / 3)


def test_tag_penalties_subtract():
    vec = unit(np.ones(4))
    lift = {"bags": {"da bò": 2.0}}
    base = 0.35 + 0.25 + 0.20 + 0.20 / 3
    dup, _, _ = tag_report(
        ["da bò", "Da bò"], "túi", "bags", lift, {"da bò"}, set(), [vec, vec], vec
    )
    assert dup == pytest.approx(base - 0.1)
    pend, verdicts, _ = tag_report(
        ["da bò", "len"], "túi", "bags", lift, {"da bò"}, {"len"}, [vec, vec], vec
    )
    assert verdicts[1]["verdict"] == "pending"
    assert pend == pytest.approx(0.35 * 0.5 + 0.25 * 0.5 + 0.20 + 0.20 / 3 - 0.05)


def test_tag_score_clipped_at_zero():
    low, _, _ = tag_report(["a", "A"], "túi", "bags", None, set(), {"a"}, None, None)
    assert low == 0.0


def test_tag_score_renormalizes_without_lift_table():
    vec = unit(np.ones(4))
    expected = (0.25 + 0.20 + 0.20 / 3) / 0.65
    for lift in (None, {}, {"shoes": {"da bò": 2.0}}):
        score, _, _ = tag_report(["da bò"], "túi", "bags", lift, {"da bò"}, set(), [vec], vec)
        assert score == pytest.approx(expected)
