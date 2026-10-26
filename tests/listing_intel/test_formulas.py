import math

import numpy as np
import pytest

from app.core.listing_intel import formulas, fusion
from tests.listing_intel import intel_support

GOOD_IMAGE = {"img_sharpness": 9.0, "img_brightness": 0.6, "img_contrast": 0.2, "img_border_uniform": 1.0,
              "img_text_ratio": 0.0, "img_w": 256.0, "img_h": 256.0, "sim_title": 0.2, "sim_category": 0.14}
TEXT = {"title_attr_material": 1.0, "title_attr_color": 2.0, "title_attr_size": 1.0, "title_attr_occasion": 0.0,
        "title_attr_use": 0.0, "title_missing": 0.0, "title_len": 60.0, "kw_lift_sum": 0.0, "title_repeat_ratio": 0.0,
        "title_banned": 0.0}


def test_weights_sum_to_one():
    for w in (formulas.IMAGE_WEIGHTS, formulas.TEXT_WEIGHTS, formulas.MARKET_WEIGHTS):
        assert sum(w.values()) == pytest.approx(1.0)


def test_image_formula_range_and_order():
    assert formulas.image(GOOD_IMAGE) == pytest.approx(1.0)
    worse = {**GOOD_IMAGE, "img_sharpness": 4.0, "img_brightness": 0.1, "img_text_ratio": 0.2}
    assert 0 <= formulas.image(worse) < formulas.image(GOOD_IMAGE)
    assert math.isnan(formulas.image({"img_sharpness": float("nan")}))


def test_image_formula_ignores_global_darkening():
    dark = {**GOOD_IMAGE, "img_sharpness": 4.0, "img_contrast": 0.2 * 0.9}
    base = {**GOOD_IMAGE, "img_sharpness": 4.0 - 2 * math.log(0.9)}
    a, b = formulas.image_parts(dark)["sharpness_rel"], formulas.image_parts(base)["sharpness_rel"]
    assert 0 < a < 1 and a == pytest.approx(b)


def test_exposure_flag_accepts_white_background():
    assert formulas.exposure_ok(0.95, 0.9, 0.2) == 1.0
    assert formulas.exposure_ok(0.95, 0.2, 0.2) == 0.0 and formulas.exposure_ok(0.1, 0.9, 0.2) == 0.0


def test_text_formula_penalises_stuffing_and_length():
    base = formulas.text(TEXT)
    assert base == pytest.approx(0.35 * 0.6 + 0.2 + 0.25 * 0.5 + 0.2)
    assert formulas.text({**TEXT, "title_repeat_ratio": 0.5}) == pytest.approx(base - 0.1)
    assert formulas.text({**TEXT, "title_len": 10.0}) == pytest.approx(base - 0.1)
    assert formulas.text({**TEXT, "kw_lift_sum": float("nan")}) > 0
    assert formulas.text({**TEXT, "title_missing": 2.0}) == pytest.approx(base - 0.3)


def test_title_keys_use_title_and_declared_materials_only():
    keys = formulas.title_keys("Áo khoác nam mùa đông", [], "fashion")
    assert keys["title_missing"] == 3.0
    assert formulas.title_keys("Áo khoác nam mùa đông", ["len"], "fashion")["title_missing"] == 2.0
    assert formulas.title_keys("Áo khoác nam mùa đông", [], "home")["title_missing"] == 0.0


def test_market_formula():
    assert formulas.market({"knn_price_pct": 50.0, "knn_dup_count": 0.0}) == pytest.approx(1.0)
    assert formulas.market({"knn_price_pct": 0.0, "knn_dup_count": 1.0}) == pytest.approx(0.2)
    assert math.isnan(formulas.market({}))


def test_axis_scores_use_formula_mode(monkeypatch):
    monkeypatch.setenv("LI_BUNDLE_DIR", str(intel_support.bundle_dir()))
    b = fusion.load_bundle()
    monkeypatch.setitem(b.meta, "axis_modes", {"image": {"mode": "model"}, "text": {"mode": "formula"},
                                               "market": {"mode": "model"}})
    feats = {**TEXT, "title_words": 8.0, "title_upper_ratio": 0.1, "desc_len": 0.0, "desc_words": 0.0,
             "kw_lift_max": 0.0, "kw_lift_terms": 0.0}
    dist = b.formula_dist.get(("text", "bags"), b.formula_dist[("text", "all")])
    got = fusion.axis_scores(feats, "bags")
    assert got["text"] == pytest.approx(float(np.interp(formulas.text(feats), dist, fusion.QS)))
    assert got["image"] is None
