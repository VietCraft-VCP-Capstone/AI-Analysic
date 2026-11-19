import pytest
from bson import ObjectId

from app.core.f29.price_peers import position, price_points
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


def test_fewer_than_eight_peers_is_not_applicable():
    me = _prod(0, SHOP_A)
    db = _db([(me, 100000)] + [(_prod(i), 200000) for i in range(1, 8)])
    result = position(db, me, 150000)
    assert result["state"] == "not_applicable" and result["n"] == 7
    assert result["pct"] is None and result["level"] is None


def test_same_shop_products_are_not_peers():
    me = _prod(0, SHOP_A)
    db = _db([(me, 100000)] + [(_prod(i, SHOP_A), 200000) for i in range(1, 10)])
    assert position(db, me, 150000)["state"] == "not_applicable"


def test_mid_price_scores_inside_band():
    me = _prod(0, SHOP_A)
    db = _db([(me, 100000)] + [(_prod(i), 100000 * i) for i in range(1, 9)])
    result = position(db, me, 450000)
    assert result["state"] == "scored" and result["level"] == "category"
    assert result["n"] == 8 and result["pct"] == 50
    assert result["p10"] < result["p90"]
    assert price_points(result["pct"]) == 20


def test_same_material_peers_give_material_level():
    me = _prod(0, SHOP_A, SILK)
    db = _db([(me, 100000)] + [(_prod(i, title=f"Váy lụa {i}"), 100000 * i) for i in range(1, 9)]
             + [(_prod(i + 10, title=f"Váy cotton {i}"), 100000 * i) for i in range(1, 9)])
    result = position(db, me, 450000)
    assert result["state"] == "scored" and result["level"] == "category_material" and result["n"] == 8


def test_too_few_same_material_falls_back_to_category():
    me = _prod(0, SHOP_A, SILK)
    db = _db([(me, 100000)] + [(_prod(i, title=f"Váy lụa {i}"), 100000 * i) for i in range(1, 8)]
             + [(_prod(i + 10, title=f"Váy cotton {i}"), 100000 * i) for i in range(1, 9)])
    result = position(db, me, 450000)
    assert result["level"] == "category" and result["n"] == 15


@pytest.mark.parametrize("pct, points", [(50, 20), (10, 20), (90, 20), (5, 10), (95, 10), (0, 0), (100, 0)])
def test_price_points(pct, points):
    assert price_points(pct) == points


def test_price_reason_reads_plainly():
    from app.core.f29.factors_v3 import price_reason
    assert price_reason(0, 33) == "Rẻ nhất trong 33 sản phẩm cùng loại"
    assert price_reason(20, 33) == "Rẻ hơn 80% trong 33 sản phẩm cùng loại"
    assert price_reason(79, 28) == "Đắt hơn 79% trong 28 sản phẩm cùng loại"
