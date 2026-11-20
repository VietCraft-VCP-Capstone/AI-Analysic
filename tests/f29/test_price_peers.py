import pytest
from bson import ObjectId

from app.core.f29 import material
from app.core.f29.price_peers import position, price_sub
from tests.f29.fake_mongo import make_calculator

CAT = "Váy Đầm"
SHOP_A, SHOP_B = ObjectId(f"{500:024x}"), ObjectId(f"{501:024x}")
SILK = "Váy lụa tơ tằm"


def _oid(i: int) -> ObjectId:
    return ObjectId(f"{i:024x}")


def _prod(i: int, shop=SHOP_B, title="Váy đầm xinh") -> dict:
    return {"_id": _oid(i), "shop_id": shop, "categories": [CAT], "title": title}


def _db(rows: list):
    products = [p for p, _ in rows]
    variants = [{"product_id": p["_id"], "retail_price": str(v)} for p, v in rows]
    return make_calculator(products=products, product_variants=variants).live_db


@pytest.mark.parametrize("price", [None, 0, float("nan")])
def test_missing_price_is_seller_missing(price):
    me = _prod(0, SHOP_A)
    assert position(_db([]), me, price)["state"] == "seller_missing"


def test_fewer_than_min_peers_is_not_applicable():
    me = _prod(0, SHOP_A)
    db = _db([(me, 100000)] + [(_prod(i), 200000) for i in range(1, 8)])
    result = position(db, me, 150000)
    assert result["state"] == "not_applicable" and result["n"] == 7 and result["pct"] is None


def test_same_shop_products_are_not_peers():
    me = _prod(0, SHOP_A)
    db = _db([(me, 100000)] + [(_prod(i, SHOP_A), 200000) for i in range(1, 10)])
    assert position(db, me, 150000)["state"] == "not_applicable"


def test_mid_price_scores_inside_band():
    me = _prod(0, SHOP_A)
    db = _db([(me, 100000)] + [(_prod(i), 100000 * i) for i in range(1, 9)])
    result = position(db, me, 450000)
    assert result["state"] == "scored" and result["factor"] == 1.0 and result["confidence"] == 1.0
    assert result["n"] == 8 and result["pct"] == 50 and result["p10"] < result["p90"]


def test_premium_material_is_compared_after_adjustment(monkeypatch):
    monkeypatch.setattr(material, "price_params", lambda: {**material.DEFAULT_PARAMS, "materials": {"lua": 2.0}})
    me = _prod(0, SHOP_A, SILK)
    db = _db([(me, 100000)] + [(_prod(i, title=f"Váy cotton {i}"), 100000 * i) for i in range(1, 9)])
    result = position(db, me, 900000)
    assert result["factor"] == 2.0 and result["pct"] == 50
    assert result["p90"] > 800000


def test_far_outlier_is_dropped():
    me = _prod(0, SHOP_A)
    db = _db([(me, 100000)] + [(_prod(i), 100000 + 1000 * i) for i in range(1, 9)] + [(_prod(20), 90000000)])
    assert position(db, me, 105000)["n"] == 8


def test_few_peers_lower_confidence(monkeypatch):
    monkeypatch.setattr(material, "price_params", lambda: {**material.DEFAULT_PARAMS, "full_n": 16})
    me = _prod(0, SHOP_A)
    db = _db([(me, 100000)] + [(_prod(i), 100000 * i) for i in range(1, 9)])
    assert position(db, me, 450000)["confidence"] == 0.5


@pytest.mark.parametrize("pct, reasons, confidence, sub", [
    (50, [], 1.0, 100), (0, [], 1.0, 100), (90, [], 1.0, 100), (95, [], 1.0, 75),
    (100, [], 1.0, 50), (100, ["process"], 1.0, 100), (100, [], 0.5, 75),
])
def test_price_sub_only_cuts_unexplained_high_price(pct, reasons, confidence, sub):
    assert price_sub(pct, reasons, confidence) == sub


def test_price_reason_reads_plainly():
    from app.core.f29.factors_v3 import price_reason
    assert price_reason(0, 33) == "Rẻ nhất trong 33 sản phẩm cùng loại"
    assert price_reason(20, 33) == "Rẻ hơn 80% trong 33 sản phẩm cùng loại"
    assert price_reason(79, 28) == "Đắt hơn 79% trong 28 sản phẩm cùng loại"
    assert price_reason(95, 28, 2.0) == "Đắt hơn 95% trong 28 sản phẩm cùng loại, đã quy đổi theo chất liệu, chưa nêu lý do giá cao"
