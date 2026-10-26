import pandas as pd

from app.core.f29.factors import KEYS
from app.core.f29.material import has_material
from scripts.f29_health import run
from scripts.f29_health.learn import to_weights
from tests.f29.fake_mongo import make_calculator
from tests.f29.samples import PRODUCT_ID, base_product, with_id


def test_has_material_from_field():
    assert has_material({"materials": ["Len"]}) is True


def test_has_material_from_title():
    assert has_material({"materials": [], "title": "Khăn len đan tay"}) is True


def test_has_material_negation():
    assert has_material({"description": "không phải cotton"}) is False
    assert has_material({"description": "áo 100% cotton"}) is True
    assert has_material({"materials": ["len"]}) is True


def test_no_material():
    assert has_material({"title": "Mũ bucket thêu logo", "materials": None}) is False


def _no_material_product():
    return with_id(base_product(title="Mũ bucket thêu logo unisex",
                                description="Mũ bucket thêu logo, form đẹp, phù hợp đi chơi và đi làm hằng ngày."))


def _calc(product):
    variants = [{"product_id": product["_id"], "is_active": True, "stock_quantity": 10,
                 "retail_price": "150000", "base_cost": "80000"}]
    return make_calculator(products=[product], product_variants=variants)


def test_breakdown_has_six_rows_and_sums():
    result = _calc(with_id(base_product())).calculate(PRODUCT_ID)
    assert [r["key"] for r in result["breakdown"]] == list(KEYS)
    assert len(result["breakdown"]) == 6
    assert round(sum(r["points"] for r in result["breakdown"]), 1) == result["score"]


def test_material_todo_impact_equals_weight():
    result = _calc(_no_material_product()).calculate(PRODUCT_ID)
    todo = next(t for t in result["todos"] if t["code"] == "material")
    assert todo["impact"] == 10.0
    assert todo["message"] == "Ghi rõ chất liệu (ví dụ: cotton, len, gốm…) vào ô Chất liệu"


def test_to_weights_fixed_material():
    w = to_weights({"image": .267, "description": .12, "review": -.076, "price": .433})
    assert w["material"] == 10 and w["tags"] == 10 and w["review"] == 5
    assert sum(w.values()) == 100


def test_material_rate_splits_top25():
    df = pd.DataFrame({"title": ["Khăn len", "Mũ bucket", "Áo cotton"],
                       "description": [None, "thêu logo", None], "top25": [1, 1, 0]})
    assert run._material_rate(df) == {"share": 66.7, "top25_with": 50.0, "top25_without": 100.0}
