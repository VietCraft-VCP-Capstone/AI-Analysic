import time

from bson import ObjectId

from app.core.f29 import price_ref, price_suggest
from app.core.f29.price_ref import PriceRef, clear_index_cache, product_price
from tests.f29.fake_mongo import make_calculator
from tests.f29.fake_price import FakePriceModel

PARAMS = {"full_at": 1.0, "zero_at": 2.0, "min_peers": 8}
TARGET_CAT = "Váy Đầm"
TIKI_REF = {"price": 189000.0, "source": "tiki", "n": 0, "kind": "std", "comparable": False,
            "low": None, "high": None, "materials": [], "same_n": 0, "prices": []}


def _oid(i: int) -> ObjectId:
    return ObjectId(f"{i:024x}")


def _db(*items):
    products = [{"_id": _oid(i), "categories": [cat]} for i, cat, _ in items]
    variants = [{"product_id": _oid(i), "retail_price": str(price)} for i, _, price in items]
    return make_calculator(products=products, product_variants=variants).live_db


def _target(i: int = 0) -> dict:
    return {"_id": _oid(i), "categories": [TARGET_CAT]}


def test_product_price_ignores_inactive_and_zero():
    variants = [{"retail_price": "100000"}, {"retail_price": "0"},
                {"retail_price": "300000", "is_active": False}, {"retail_price": "200000"}]
    assert product_price(variants) == 200000.0


def test_product_price_none():
    assert product_price([]) is None


def test_reference_category_needs_8_peers():
    items = [(0, TARGET_CAT, 100000)] + [(i, TARGET_CAT, 200000) for i in range(1, 9)]
    ref = PriceRef(_db(*items), PARAMS).reference(_target())
    assert ref["source"] == "category" and ref["n"] == 8
    clear_index_cache()
    ref = PriceRef(_db(*items[:-1]), PARAMS).reference(_target())
    assert ref["source"] != "category"


def test_reference_falls_back_group_then_model(fake_price_model):
    items = [(0, TARGET_CAT, 100000)] + [(i, "Áo thun", 200000) for i in range(1, 9)]
    ref = PriceRef(_db(*items), PARAMS).reference(_target())
    assert ref["source"] == "group"
    clear_index_cache()
    ref = PriceRef(_db(*items[:-1]), PARAMS).reference(_target())
    assert ref["source"] == "model" and ref["n"] == 0


def test_reference_uses_model_when_few_peers(fake_price_model):
    ref = PriceRef(_db((0, TARGET_CAT, 100000)), PARAMS).reference(_target())
    assert ref["source"] == "model" and ref["n"] == 0


def test_reference_falls_back_to_tiki_without_model():
    ref = PriceRef(_db((0, TARGET_CAT, 100000)), PARAMS).reference(_target())
    assert ref == TIKI_REF


def test_reference_falls_back_to_tiki_when_predict_fails(monkeypatch):
    model = FakePriceModel(error=RuntimeError("boom"))
    monkeypatch.setattr(price_suggest, "_load", lambda path: (model, -0.2, 0.2))
    ref = PriceRef(_db((0, TARGET_CAT, 100000)), PARAMS).reference(_target())
    assert ref == TIKI_REF


def test_pod_product_does_not_use_std_peers():
    clear_index_cache()
    items = [(0, TARGET_CAT, 100000)] + [(i, TARGET_CAT, 200000) for i in range(1, 9)]
    db = _db(*items)
    pod_product = {"_id": _oid(0), "categories": [TARGET_CAT], "product_type": "POD_TEMPLATE"}
    ref = PriceRef(db, PARAMS).reference(pod_product)
    assert ref["kind"] == "pod"
    assert ref["source"] != "category"


def test_reference_excludes_self():
    items = [(0, TARGET_CAT, 1000000)] + [(i, TARGET_CAT, 200000) for i in range(1, 9)]
    ref = PriceRef(_db(*items), PARAMS).reference(_target())
    assert ref["price"] == 200000.0 and ref["n"] == 8


def test_index_cached_for_fifteen_minutes(monkeypatch):
    items = [(0, TARGET_CAT, 100000)] + [(i, TARGET_CAT, 200000) for i in range(1, 9)]
    db = _db(*items)
    assert PriceRef(db, PARAMS).reference(_target())["n"] == 8
    db["products"].docs.append({"_id": _oid(20), "categories": [TARGET_CAT]})
    db["product_variants"].docs.append({"product_id": _oid(20), "retail_price": "200000"})
    assert PriceRef(db, PARAMS).reference(_target())["n"] == 8
    later = time.monotonic() + price_ref.INDEX_TTL_SECONDS + 1
    monkeypatch.setattr(price_ref.time, "monotonic", lambda: later)
    assert PriceRef(db, PARAMS).reference(_target())["n"] == 9


def test_index_build_sends_no_in_filter():
    db = _db((0, TARGET_CAT, 100000), (1, TARGET_CAT, 200000))
    seen = []
    for name in ("products", "product_variants"):
        original = db[name].find

        def spy(query=None, projection=None, _find=original):
            seen.append(query or {})
            return _find(query, projection)

        db[name].find = spy
    PriceRef(db, PARAMS).reference(_target())
    assert len(seen) == 2 and all("$in" not in repr(q) for q in seen)


def test_dirty_data_handled():
    clear_index_cache()
    items = [(0, TARGET_CAT, 100000)] + [(i, TARGET_CAT, 200000) for i in range(1, 9)]
    db = _db(*items)
    db["products"].docs.append({"_id": _oid(99), "categories": [12345]})
    db["products"].docs.append({"_id": _oid(100), "categories": None})
    db["product_variants"].docs.append({"retail_price": "200000"})
    db["product_variants"].docs.append({"product_id": None, "retail_price": "200000"})
    db["product_variants"].docs.append({"product_id": _oid(0), "retail_price": "Infinity"})
    db["product_variants"].docs.append({"product_id": _oid(0), "retail_price": "NaN"})
    ref = PriceRef(db, PARAMS).reference(_target())
    assert ref["source"] == "category" and ref["n"] == 8


def test_reference_excludes_same_shop():
    clear_index_cache()
    shop_a = _oid(500)
    shop_b = _oid(501)
    products = [{"_id": _oid(0), "shop_id": shop_a, "categories": [TARGET_CAT]}]
    for i in range(1, 9):
        products.append({"_id": _oid(i), "shop_id": shop_a, "categories": [TARGET_CAT]})
    variants = [{"product_id": _oid(i), "retail_price": "200000"} for i in range(9)]
    db = make_calculator(products=products, product_variants=variants).live_db
    ref = PriceRef(db, PARAMS).reference(products[0])
    assert ref["source"] != "category"



def _material_db(peer_title, n=8):
    products = [{"_id": _oid(0), "shop_id": _oid(500), "categories": [TARGET_CAT], "title": "Váy lụa tơ tằm"}]
    products += [{"_id": _oid(i), "shop_id": _oid(501), "categories": [TARGET_CAT], "title": f"{peer_title} {i}"}
                 for i in range(1, n + 1)]
    variants = [{"product_id": p["_id"], "retail_price": str(100000 * (i + 1))} for i, p in enumerate(products)]
    return make_calculator(products=products, product_variants=variants).live_db, products[0]


def test_reference_same_material_is_comparable_with_band():
    db, target = _material_db("Váy lụa")
    ref = PriceRef(db, PARAMS).reference(target)
    assert ref["source"] == "material" and ref["comparable"] is True and ref["materials"] == ["lụa"]
    assert ref["n"] == 8 and ref["low"] <= ref["price"] <= ref["high"]


def test_reference_other_material_is_not_comparable():
    db, target = _material_db("Váy cotton")
    ref = PriceRef(db, PARAMS).reference(target)
    assert ref["source"] == "category" and ref["comparable"] is False


def test_reference_too_few_same_material_falls_back():
    db, target = _material_db("Váy lụa", n=7)
    assert PriceRef(db, PARAMS).reference(target)["comparable"] is False


def test_sample_keeps_ends_and_caps_length():
    from app.core.f29.price_ref import _sample
    out = _sample([float(x) for x in range(1000, 0, -1)], cap=5)
    assert len(out) == 5 and out[0] == 1.0 and out[-1] == 1000.0 and out == sorted(out)
    assert _sample([3.0, 1.0]) == [1.0, 3.0]
