import pytest
from bson import ObjectId

from app.core.f29.factors import KEYS
from app.core.f29.preview import preview_health
from tests.f29.fake_mongo import make_calculator
from tests.f29.samples import PRODUCT_ID, base_product, with_id

NONE = {"n_images": None, "description_length": None, "n_tags": None, "price": None}
LONG = " ".join(f"chu{i}" for i in range(130))
JUNK_TITLE = "icon arrow left bold Share: Favorite (48) Áo thun cotton local brand unisex"


def _calc(**product):
    p = with_id(base_product(**product))
    variants = [{"product_id": p["_id"], "is_active": True, "stock_quantity": 10,
                 "retail_price": "150000", "base_cost": "80000"}]
    peers = [{"_id": ObjectId(f"{i:024x}"), "categories": ["Thời trang"], "description": LONG} for i in range(1, 9)]
    variants += [{"product_id": p["_id"], "is_active": True, "retail_price": "100000"} for p in peers]
    return make_calculator(products=[p, *peers], product_variants=variants)


def _others_unchanged(preview, current, key):
    return all(preview["axes"][k] == current["axes"][k] for k in KEYS if k != key)


def test_no_override_matches_current():
    calc = _calc()
    current = calc.calculate(PRODUCT_ID)
    preview = preview_health(calc, PRODUCT_ID, NONE)
    assert preview["score"] == current["score"] and preview["axes"] == current["axes"]
    assert preview["delta_vs_current"] == 0.0 and preview["ignored"] == []


@pytest.mark.parametrize("override,key,expected", [
    ({"n_tags": 0}, "tags", 0.0),
    ({"n_images": 0}, "image", 0.0),
    ({"description_length": 0}, "description", 75.0),
])
def test_override_changes_only_its_factor(override, key, expected):
    calc = _calc()
    current = calc.calculate(PRODUCT_ID)
    preview = preview_health(calc, PRODUCT_ID, {**NONE, **override})
    assert preview["axes"][key] == expected
    assert _others_unchanged(preview, current, key)


def test_price_override_recomputes_price_axis():
    calc = _calc()
    current = calc.calculate(PRODUCT_ID)
    preview = preview_health(calc, PRODUCT_ID, {**NONE, "price": 100000})
    assert preview["axes"]["price"] == 100.0 and preview["inputs"]["price"] == 100000
    assert _others_unchanged(preview, current, "price")


def test_preview_has_no_79_cap():
    product = with_id(base_product(title=JUNK_TITLE))
    variants = [{"product_id": product["_id"], "is_active": True, "stock_quantity": 10,
                 "retail_price": "150000", "base_cost": "80000"}]
    calc = make_calculator(products=[product], product_variants=variants)
    current = calc.calculate(PRODUCT_ID)
    assert any(b["field"] == "title" for b in current["blockers"]) and current["score"] == 100.0
    assert preview_health(calc, PRODUCT_ID, NONE)["score"] == 100.0


def test_description_override_on_empty_description_scores_words():
    calc = _calc(description="")
    assert calc.calculate(PRODUCT_ID)["axes"]["description"] == 0.0
    preview = preview_health(calc, PRODUCT_ID, {**NONE, "description_length": 130})
    assert preview["axes"]["description"] == 100.0
