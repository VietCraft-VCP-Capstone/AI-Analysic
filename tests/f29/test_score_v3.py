import pytest
from bson import ObjectId

from app.core.f29 import breakdown, factors_v3, image_check, review_stats, scoring
from app.core.f29.constants import MODEL_VERSION
from tests.f29.fake_mongo import make_calculator
from tests.f29.samples import PRODUCT_ID, base_product, with_id

ORDER = ObjectId()
PRICED = [{"is_active": True, "stock_quantity": 10, "retail_price": "150000", "base_cost": "80000"}]
RICH = {"images": [f"i{i}.jpg" for i in range(6)],
        "description": " ".join(f"chu{chr(97 + i % 26)}{i}" for i in range(130))}


@pytest.fixture(autouse=True)
def platform_p0_is_full(monkeypatch):
    monkeypatch.setattr(review_stats, "platform_p0", lambda live_db: 1.0)


def _priced(product):
    return [{**v, "product_id": product["_id"]} for v in PRICED]


def _peer(i):
    return {"_id": ObjectId(f"{i:024x}"), "categories": ["Thời trang"], "title": f"Áo thun cotton mẫu {i}"}


def _full_world(**overrides):
    product = with_id(base_product(**{**RICH, **overrides}))
    peers = [_peer(i) for i in range(1, 9)]
    variants = _priced(product) + [{"product_id": p["_id"], "is_active": True, "retail_price": "150000"} for p in peers]
    reviews = [{"product_id": product["_id"], "order_id": ORDER, "rating": 5}]
    return make_calculator(products=[product, *peers], product_variants=variants,
                           orders=[{"_id": ORDER}], reviews=reviews)


def _factor(result, key):
    return next(f for f in result["factors"] if f["key"] == key)


def test_seller_missing_description_counts_as_zero():
    product = with_id(base_product(description=""))
    result = make_calculator(products=[product], product_variants=_priced(product)).calculate(PRODUCT_ID)
    row = _factor(result, "description")
    assert row["state"] == "seller_missing" and row["points"] == 0.0
    assert result["coverage"] == {"evaluated": 3, "total": 5}


def test_no_reviews_and_no_peers_scores_three_factors():
    product = with_id(base_product())
    result = make_calculator(products=[product], product_variants=_priced(product)).calculate(PRODUCT_ID)
    assert result["coverage"] == {"evaluated": 3, "total": 5}
    assert set(result["axes_missing"]) == {"review", "price"}
    assert result["score"] == 100.0 and result["status"] == "good"


def test_review_without_data_is_excluded_coverage_four():
    product = with_id(base_product())
    result = make_calculator(products=[product]).calculate(PRODUCT_ID)
    assert _factor(result, "review")["state"] == "not_applicable"
    assert result["coverage"] == {"evaluated": 4, "total": 5}
    assert result["score"] == 75.0


def test_all_five_full_scores_hundred_good():
    result = _full_world().calculate(PRODUCT_ID)
    assert result["score"] == 100.0 and result["status"] == "good"
    assert result["coverage"] == {"evaluated": 5, "total": 5}
    assert all(f["weight"] == 20 for f in result["factors"])
    assert result["versions"]["score"] == MODEL_VERSION == "health-3.0"


def test_image_technical_failure_never_scores_zero(monkeypatch):
    failed = {"state": "technical_failure", "useful": 6, "images": [], "method": "heuristic"}
    monkeypatch.setattr(image_check, "analyze", lambda *a, **k: failed)
    result = _full_world().calculate(PRODUCT_ID)
    image = _factor(result, "image")
    assert image["state"] == "technical_failure" and image["sub_score"] is None and image["points"] == 0.0
    assert result["coverage"] == {"evaluated": 4, "total": 5}
    assert result["score"] == 100.0


def test_identical_input_gives_identical_output():
    calc = _full_world()
    first, second = calc.calculate(PRODUCT_ID), calc.calculate(PRODUCT_ID)
    for result in (first, second):
        result.pop("computed_at")
    assert first == second


@pytest.mark.parametrize("points,status", [
    ((20, 20, 20, 20, 0), "good"),
    ((20, 20, 20, 19.9, 0), "needs_improvement"),
    ((20, 20, 9.9, 0, 0), "poor"),
])
def test_status_bands(points, status):
    value, _ = breakdown.score([{"state": "scored", "points": p} for p in points])
    assert scoring.status_from_score(value) == status


def test_image_row_scales_useful_by_median():
    row = factors_v3.image_row({"state": "scored", "useful": 2, "method": "heuristic"}, 4)
    assert row["sub_score"] == 50.0 and row["points"] == 10.0


def test_tags_coverage_is_search_volume_weighted():
    queries = [{"query": "a", "searches": 3, "covered": True}, {"query": "b", "searches": 1, "covered": False}]
    assert factors_v3.tags_row(1, 0, queries, "rule")["sub_score"] == 87.5


def test_tags_without_queries_use_first_half_only():
    assert factors_v3.tags_row(1, 0, [], "rule")["sub_score"] == 100.0
    assert factors_v3.tags_row(0, 0, [], "rule")["sub_score"] == 0.0


def test_price_row_uses_price_points():
    row = factors_v3.price_row({"state": "scored", "pct": 5, "n": 8, "level": "category", "p10": 1, "p90": 2})
    assert row["points"] == 10.0


def test_default_size_is_not_a_real_size():
    default = {"dimensions_cm": {"length": 10, "width": 10, "height": 10}, "weight_g": 500}
    assert factors_v3.has_size(default, "Áo đẹp") is False
    assert factors_v3.has_size(default, "Áo dài 70cm") is True
