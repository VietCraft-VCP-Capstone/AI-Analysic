from datetime import datetime, timedelta

import pytest
from bson import ObjectId

from app.core.f29 import query_relevance as qr
from tests.f29.fake_mongo import make_calculator

NOW = datetime(2026, 11, 18, 12, 0, 0)
REAL = ObjectId("000000000000000000000001")
OTHER = ObjectId("000000000000000000000002")
SEED = ObjectId("000000000000000000000003")


def _click(pid, pos=0):
    return {"product_id": pid, "position": pos, "clicked_at": NOW}


def _db():
    products = [
        {"_id": REAL, "categories": ["Áo thun"]},
        {"_id": OTHER, "categories": ["Váy"]},
        {"_id": SEED, "categories": ["Áo thun"], "seed_ref": ObjectId()},
    ]
    logs = [
        {"keyword": "Áo Thun", "created_at": NOW - timedelta(days=1), "clicks": [_click(REAL)]},
        {"keyword": "áo thun", "created_at": NOW - timedelta(days=2), "clicks": [_click(REAL, 1)]},
        {"keyword": "ao thun", "created_at": NOW - timedelta(days=2), "clicks": []},
        {"keyword": "váy", "created_at": NOW - timedelta(days=1), "clicks": [_click(OTHER)]},
        {"keyword": "váy", "created_at": NOW - timedelta(days=1), "clicks": []},
        {"keyword": "cốc", "created_at": NOW - timedelta(days=1), "clicks": [_click(REAL)]},
        {"keyword": "đen", "created_at": NOW - timedelta(days=60), "clicks": [_click(REAL)]},
        {"keyword": "đen", "created_at": NOW - timedelta(days=60), "clicks": [_click(REAL)]},
        {"keyword": "seed", "created_at": NOW - timedelta(days=1), "clicks": [_click(SEED)]},
        {"keyword": "seed", "created_at": NOW - timedelta(days=1), "clicks": [_click(SEED)]},
    ]
    return make_calculator(products=products, search_logs=logs).live_db


def test_covered_ignores_accent_and_case():
    assert qr.covered("ÁO THUN", "áo thun cotton")
    assert qr.covered("ao thun", "Áo Thun")
    assert qr.covered("đầm", "Đầm dự tiệc")
    assert not qr.covered("", "áo thun")


def test_covered_requires_every_token():
    assert not qr.covered("cốc sứ", "Ly sứ")
    assert not qr.covered("áo thun nam", "Áo thun nữ")


def test_category_queries_filters_by_category_and_searches():
    db = _db()
    since = NOW - timedelta(days=30)
    assert qr.category_queries(db, "Áo thun", since) == [{"query": "áo thun", "searches": 3}]
    assert qr.category_queries(db, "Váy", since) == [{"query": "váy", "searches": 2}]
    assert [r["query"] for r in qr.category_queries(db, None, since)] == ["áo thun", "váy"]


def test_relevant_falls_back_to_lexical_without_model(tmp_path):
    assert qr.relevant("ao thun", "Áo thun cotton", None)
    assert not qr.relevant("ao thun", "Áo khoác", {})
    assert qr.relevant("ao thun", "Áo thun", qr.load_model(tmp_path / "missing.json"))
    assert not qr.relevant("ao thun", "Váy", qr.load_model(tmp_path / "missing.json"))


def test_relevant_uses_association_when_enabled():
    model = {"enabled": True, "assoc": {"coc": {"ly": 0.5}}}
    assert qr.relevant("cốc", "Ly sứ", model)
    assert not qr.relevant("cốc", "Váy", model)
    assert not qr.relevant("cốc", "Ly sứ", {"enabled": False, "assoc": model["assoc"]})


def test_train_weights_clicks_by_inverse_position():
    assoc = qr.train([("cốc", "Ly sứ trắng", 0), ("cốc", "Ly sứ men", 1)])
    assert assoc["coc"]["ly"] == pytest.approx(1.0)
    assert assoc["coc"]["men"] == pytest.approx(1 / 3, abs=1e-3)


def test_load_model_missing_file_is_lexical(tmp_path):
    model = qr.load_model(tmp_path / "missing.json")
    assert model == {"version": "lexical-1", "enabled": False}
    disabled = tmp_path / "off.json"
    disabled.write_text('{"version": "weak-x", "enabled": false}', "utf-8")
    assert qr.load_model(disabled)["version"] == "lexical-1"


def test_zero_result_queries_keeps_repeated_relevant_misses():
    product = {"categories": ["Áo thun"], "title": "Áo thun cotton unisex"}
    miss = {"result_count": 0, "created_at": NOW - timedelta(days=1)}
    logs = [
        {"keyword": "Áo Thun Oversize", **miss},
        {"keyword": "áo thun oversize", **miss},
        {"keyword": "váy dạ hội", **miss},
        {"keyword": "váy dạ hội", **miss},
        {"keyword": "cotton", **miss},
        {"keyword": "ao thun", "result_count": 5, "created_at": NOW - timedelta(days=1)},
        {"keyword": "ao thun", "result_count": 5, "created_at": NOW - timedelta(days=1)},
        {"keyword": "áo thun nam", "result_count": 0, "created_at": NOW - timedelta(days=60)},
        {"keyword": "áo thun nam", "result_count": 0, "created_at": NOW - timedelta(days=60)},
    ]
    db = make_calculator(search_logs=logs).live_db
    assert qr.zero_result_queries(db, product, NOW - timedelta(days=30)) == [
        {"query": "áo thun oversize", "searches": 2}]


def test_zero_result_ignores_accent_collisions_and_single_shared_word():
    product = {"categories": ["Trang sức"], "title": "Đồng hồ thời trang nam nữ dây cao su"}
    miss = {"result_count": 0, "created_at": NOW - timedelta(days=1)}
    logs = [{"keyword": k, **miss} for k in ["váy trắng", "váy trắng", "áo đồng phục", "áo đồng phục", "đồng hồ dây da", "đồng hồ dây da"]]
    db = make_calculator(search_logs=logs).live_db
    assert qr.zero_result_queries(db, product, NOW - timedelta(days=30)) == [{"query": "đồng hồ dây da", "searches": 2}]


def test_about_rejects_queries_sharing_only_generic_words():
    watch = {"categories": ["Trang sức"], "title": "Đồng hồ thời trang nam nữ dây cao su"}
    assert not qr.about("dép nam", watch)
    assert not qr.about("vòng nam", watch)
    assert qr.about("đồng hồ nam", watch)
    assert qr.about("thun oversize", {"categories": ["Áo thun"], "title": "Áo thun nam nữ form rộng"})
