from tests.f29.fake_mongo import make_calculator
from tests.f29.samples import PRODUCT_ID, base_product, with_id

PRICED = [{"is_active": True, "stock_quantity": 10, "retail_price": "150000", "base_cost": "80000"}]
LOSS = [{"is_active": True, "stock_quantity": 10, "retail_price": "50000", "base_cost": "80000"}]
NO_STOCK = [{"is_active": True, "stock_quantity": 0, "retail_price": "150000", "base_cost": "80000"}]
RICH = {"images": [f"i{i}.jpg" for i in range(6)],
        "description": " ".join(f"chu{chr(97 + i % 26)}{i}" for i in range(130))}


def _calc(variants=PRICED, **overrides):
    product = with_id(base_product(**overrides))
    priced = [{**v, "product_id": product["_id"]} for v in variants]
    return make_calculator(products=[product], product_variants=priced)


def _fields(result):
    return [b["field"] for b in result["blockers"]]


def test_selling_below_cost_is_blocker():
    assert _fields(_calc(LOSS).calculate(PRODUCT_ID)) == ["variants.retail_price"]


def test_no_stock_is_blocker():
    assert _fields(_calc(NO_STOCK).calculate(PRODUCT_ID)) == ["variants.stock"]


def test_clean_listing_has_no_blockers():
    assert _calc(**RICH).calculate(PRODUCT_ID)["blockers"] == []
