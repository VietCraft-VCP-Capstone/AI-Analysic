import pytest
from bson import ObjectId

from app.core.f29 import weights
from app.core.f29.constants import MODEL_VERSION
from app.core.f29.factors import KEYS
from tests.f29.fake_mongo import make_calculator
from tests.f29.samples import NOW, PRODUCT_ID, base_product, with_id

ORDER = ObjectId()
OTHER = ObjectId("507f1f77bcf86cd799439012")
PRICED = [{"is_active": True, "stock_quantity": 10, "retail_price": "150000", "base_cost": "80000"}]


def _priced(product, variants=PRICED):
    return [{**v, "product_id": product["_id"]} for v in variants]


def _review(product_id, rating, order_id=ORDER):
    return {"product_id": product_id, "order_id": order_id, "rating": rating}


def _with_peers(peer_title, price):
    product = with_id(base_product())
    peers = [{"_id": ObjectId(f"{i:024x}"), "shop_id": OTHER, "categories": ["Thời trang"],
              "title": f"{peer_title} {i}"} for i in range(1, 9)]
    variants = _priced(product, [{"is_active": True, "retail_price": price, "base_cost": "30000"}])
    variants += [{"product_id": p["_id"], "is_active": True, "retail_price": "100000"} for p in peers]
    return make_calculator(products=[product, *peers], product_variants=variants).calculate(PRODUCT_ID)


class TestCalculateIntegration:
    def test_invalid_product_id_returns_none(self):
        calc = make_calculator()
        assert calc.calculate("not-an-object-id") is None

    def test_seed_product_excluded(self):
        product = with_id(base_product(seed_ref="seed_123"))
        calc = make_calculator(products=[product])
        assert calc.calculate(PRODUCT_ID) is None

    def test_missing_product_returns_none(self):
        calc = make_calculator(products=[])
        assert calc.calculate(PRODUCT_ID) is None

    def test_weights_missing_returns_error(self, monkeypatch, tmp_path):
        monkeypatch.setattr(weights, "WEIGHTS_PATH", tmp_path / "none.json")
        weights.clear_cache()
        calc = make_calculator(products=[with_id(base_product())])
        assert calc.calculate(PRODUCT_ID) == {"error": "no_weights"}

    def test_happy_path_shape_and_axes_missing(self):
        product = with_id(base_product())
        calc = make_calculator(products=[product], product_variants=_priced(product))
        result = calc.calculate(PRODUCT_ID)

        assert result["product_id"] == PRODUCT_ID
        assert isinstance(result["score"], float)
        assert result["status"] in ("good", "needs_improvement", "poor")
        assert set(result["axes"]) == set(KEYS)
        assert result["axes_missing"] == ["review"]
        assert [r["key"] for r in result["breakdown"]] == list(KEYS)
        assert result["basis"]["weights"] == weights.load()["weights"]
        assert result["model_version"] == MODEL_VERSION
        assert result["content_hash"] and result["inputs_hash"]

    def test_missing_review_scores_zero(self):
        product = with_id(base_product())
        calc = make_calculator(products=[product], product_variants=_priced(product))
        result = calc.calculate(PRODUCT_ID)
        assert result["axes"]["review"] == 0.0
        assert "review" in result["axes_missing"]

    def test_simulated_order_reviews_ignored(self):
        sim_order = ObjectId()
        product = with_id(base_product())
        calc = make_calculator(
            products=[product], product_variants=_priced(product),
            orders=[{"_id": sim_order, "is_simulated": True}],
            reviews=[_review(product["_id"], 5, order_id=sim_order)],
        )
        result = calc.calculate(PRODUCT_ID)
        assert result["axes"]["review"] == 0.0
        assert "review" in result["axes_missing"]

    def test_review_uses_platform_p0(self):
        product = with_id(base_product())
        reviews = [_review(product["_id"], 5), _review(product["_id"], 5),
                   _review(OTHER, 1), _review(OTHER, 1)]
        calc = make_calculator(products=[product], product_variants=_priced(product),
                               orders=[{"_id": ORDER}], reviews=reviews)
        assert calc.calculate(PRODUCT_ID)["axes"]["review"] == pytest.approx(64.3, abs=0.05)

    def test_no_active_variant_price_is_missing(self, fake_price_model):
        product = with_id(base_product())
        variants = _priced(product, [{"is_active": False, "retail_price": "150000", "base_cost": "80000"}])
        calc = make_calculator(products=[product], product_variants=variants)
        result = calc.calculate(PRODUCT_ID)
        assert result["axes"]["price"] == 0.0
        assert "price" in result["axes_missing"]
        msg = "Chưa có giá bán cho biến thể nào · Tham khảo: 82.000đ–122.000đ"
        assert any(t["field"] == "price" and t["message"] == msg for t in result["todos"])

    def test_price_row_has_suggestion(self, fake_price_model):
        product = with_id(base_product())
        calc = make_calculator(products=[product], product_variants=_priced(product))
        price = next(r for r in calc.calculate(PRODUCT_ID)["breakdown"] if r["key"] == "price")
        assert price["suggestion"] == {"low": 82000.0, "high": 122000.0}
        assert price["reference"]["source"] == "model" and price["reference"]["comparable"] is False

    def test_price_not_penalized_without_same_material_peers(self, fake_price_model):
        product = with_id(base_product())
        variants = _priced(product, [{"is_active": True, "retail_price": "400000", "base_cost": "80000"}])
        result = make_calculator(products=[product], product_variants=variants).calculate(PRODUCT_ID)
        price = next(r for r in result["breakdown"] if r["key"] == "price")
        assert result["axes"]["price"] is None and price["scored"] is False and price["points"] == 0.0
        assert not any(t["field"] == "price" for t in result["todos"] + result["warnings"])
        scored = [r for r in result["breakdown"] if r["scored"]]
        assert result["score"] == round(sum(r["points"] for r in scored) * 100 / sum(r["weight"] for r in scored), 1)

    def test_no_typo_check_against_rough_reference(self, fake_price_model):
        product = with_id(base_product())
        variants = _priced(product, [{"is_active": True, "retail_price": "15000", "base_cost": "8000"}])
        result = make_calculator(products=[product], product_variants=variants).calculate(PRODUCT_ID)
        assert not any(w["field"] == "price" for w in result["warnings"])
        assert result["axes"]["price"] is None

    def test_cheap_price_vs_same_material_peers(self):
        result = _with_peers("Áo cotton mẫu", "50000")
        price = next(r for r in result["breakdown"] if r["key"] == "price")
        assert price["reference"]["comparable"] is True and price["reference"]["materials"] == ["cotton"]
        assert result["axes"]["price"] < 100.0
        msg = next(t["message"] for t in result["todos"] if t["field"] == "price")
        assert msg == ("Giá thấp hơn 50% so với 8 sản phẩm cùng loại, cùng chất liệu cotton, "
                       "kiểm tra lại chi phí để không bán lỗ · Tham khảo: 100.000đ–100.000đ")

    def test_full_band_matches_price_score(self):
        price = next(r for r in _with_peers("Áo cotton mẫu", "50000")["breakdown"] if r["key"] == "price")
        assert price["full"] == {"low": 70000, "high": 130000}
        for value, full in ((70000, True), (130000, True), (69000, False), (131000, False)):
            result = _with_peers("Áo cotton mẫu", str(value))
            assert (result["axes"]["price"] == 100.0) is full

    def test_price_typo_vs_same_material_is_urgent(self):
        result = _with_peers("Áo cotton mẫu", "15000")
        warning = next(w for w in result["warnings"] if w["field"] == "price")
        assert warning["type"] == "warning" and warning["impact"] == 0
        assert "thấp hơn khoảng 7 lần" in warning["message"]

    def test_other_material_peers_do_not_penalize(self):
        result = _with_peers("Áo len mẫu", "50000")
        price = next(r for r in result["breakdown"] if r["key"] == "price")
        assert price["reference"]["source"] == "category" and price["reference"]["comparable"] is False
        assert result["axes"]["price"] is None and price["scored"] is False

    def test_junk_title_warns_with_cleaned_suggestion(self):
        product = with_id(base_product(title="icon arrow left bold Share: Favorite (48) Thắt lưng vải canvas nam"))
        result = make_calculator(products=[product], product_variants=_priced(product)).calculate(PRODUCT_ID)
        warning = next(w for w in result["warnings"] if w["field"] == "title")
        assert warning["type"] == "warning" and warning["target"] == "Thắt lưng vải canvas nam"

    def test_description_junk_scores_zero(self):
        product = with_id(base_product(description="a " * 570))
        result = make_calculator(products=[product], product_variants=_priced(product)).calculate(PRODUCT_ID)
        assert result["axes"]["description"] == 0.0

    def test_deterministic(self):
        product = with_id(base_product())
        calc = make_calculator(products=[product], product_variants=_priced(product))
        first, second = calc.calculate(PRODUCT_ID), calc.calculate(PRODUCT_ID)
        assert (first["score"], first["axes"], first["todos"]) == (second["score"], second["axes"], second["todos"])

    def test_warnings_are_separate_from_todos(self):
        product = with_id(base_product(images=[], moderation_status="REJECTED"))
        variants = _priced(product, [{"is_active": True, "retail_price": "50000", "base_cost": "80000"}])
        result = make_calculator(products=[product], product_variants=variants).calculate(PRODUCT_ID)

        assert {w["field"] for w in result["warnings"]} == {"images", "variants.retail_price", "moderation_status"}
        assert all(w["impact"] == 0 for w in result["warnings"])
        assert all(t["type"] == "todo" for t in result["todos"])


class TestSaveIdempotency:
    def _sample_result(self, score=72.5, date=None):
        return {
            "product_id": PRODUCT_ID,
            "date": date or NOW.date().isoformat(),
            "score": score,
            "status": "needs_improvement",
            "axes": {"image": 100.0, "description": 100.0, "tags": 100.0, "review": 0.0, "price": 0.0},
            "axes_missing": ["review", "price"],
            "todos": [],
            "computed_at": NOW.isoformat().replace("+00:00", "Z"),
            "model_version": "health-2.2",
            "content_hash": "abc123",
            "inputs_hash": "def456",
        }

    def test_save_different_dates_creates_history_documents(self):
        calc = make_calculator()
        calc.save(self._sample_result(date="2026-10-15", score=50.0))
        calc.save(self._sample_result(date="2026-10-16", score=75.0))
        docs = calc.live_db["listing_health_scores"].docs
        assert len(docs) == 2
        scores = {d["score"] for d in docs}
        assert scores == {50.0, 75.0}

    def test_save_when_db_allows_one_document_per_product(self):
        from pymongo.errors import DuplicateKeyError
        calc = make_calculator()
        calc.save(self._sample_result(date="2026-10-15", score=50.0))
        coll = calc.live_db["listing_health_scores"]
        plain_update = coll.update_one

        def unique_product(filt, update, upsert=False):
            if upsert and not coll.find_one(filt) and coll.find_one({"product_id": filt["product_id"]}):
                raise DuplicateKeyError("E11000 duplicate key error index: product_id_1")
            return plain_update(filt, update, upsert)

        coll.update_one = unique_product
        calc.save(self._sample_result(date="2026-10-16", score=75.0))
        assert [(d["score"], d["date"].day) for d in coll.docs] == [(75.0, 16)]

    def test_save_twice_same_result_creates_one_document(self):
        calc = make_calculator()
        calc.save(self._sample_result())
        calc.save(self._sample_result())
        docs = calc.live_db["listing_health_scores"].docs
        assert len(docs) == 1
        assert docs[0]["score"] == 72.5

    def test_save_upserts_on_score_change_same_day(self):
        calc = make_calculator()
        calc.save(self._sample_result(score=50.0))
        calc.save(self._sample_result(score=90.0))
        docs = calc.live_db["listing_health_scores"].docs
        assert len(docs) == 1
        assert docs[0]["score"] == 90.0

    def test_calculate_then_save_twice_is_idempotent(self):
        product = with_id(base_product())
        calc = make_calculator(products=[product], product_variants=_priced(product))

        result1 = calc.calculate(PRODUCT_ID)
        calc.save(result1)
        result2 = calc.calculate(PRODUCT_ID)
        calc.save(result2)

        docs = calc.live_db["listing_health_scores"].docs
        assert len(docs) == 1
        assert docs[0]["score"] == result1["score"] == result2["score"]
        assert docs[0]["content_hash"] == result1["content_hash"]

    def test_save_drops_breakdown_and_basis(self):
        product = with_id(base_product())
        calc = make_calculator(products=[product], product_variants=_priced(product))
        result = calc.calculate(PRODUCT_ID)
        calc.save(result)
        doc = calc.live_db["listing_health_scores"].docs[0]
        assert "breakdown" not in doc and "basis" not in doc
        assert doc["todos"] == result["warnings"] + result["todos"]

    def test_save_returns_none_for_invalid_result(self):
        calc = make_calculator()
        assert calc.save(None) is None
        assert calc.save({"product_id": "khong-phai-objectid", "date": "2026-10-15"}) is None


def test_tag_under_review_counts_as_pending():
    tags = [{"_id": ObjectId(f"{i:024x}"), "name": n, "status": s, "review_status": r}
            for i, (n, s, r) in enumerate([("a", "active", "approved"), ("b", "pending", "pending"),
                                           ("c", "active", "pending")], start=1)]
    product = with_id(base_product(tag_ids=[t["_id"] for t in tags]))
    calc = make_calculator(products=[product], product_variants=_priced(product), tags=tags)
    row = next(r for r in calc.calculate(PRODUCT_ID)["breakdown"] if r["key"] == "tags")
    assert row["value"] == 1 and row["pending"] == 2


RICH = {"images": [f"i{i}.jpg" for i in range(6)],
        "description": " ".join(f"chu{chr(97 + i % 26)}{i}" for i in range(130))}


def test_missing_price_is_scored_zero_not_skipped():
    product = with_id(base_product())
    result = make_calculator(products=[product]).calculate(PRODUCT_ID)
    price = next(r for r in result["breakdown"] if r["key"] == "price")
    assert price["scored"] is True and price["points"] == 0.0


def test_todo_impact_equals_real_gain_when_price_unscored():
    before = with_id(base_product(**RICH, tags=["áo thun"]))
    after = with_id(base_product(**RICH))
    r1 = make_calculator(products=[before], product_variants=_priced(before)).calculate(PRODUCT_ID)
    r2 = make_calculator(products=[after], product_variants=_priced(after)).calculate(PRODUCT_ID)
    todo = next(t for t in r1["todos"] if t["code"] == "tags")
    assert abs(round(r2["score"] - r1["score"], 1) - todo["impact"]) <= 0.2


def test_blocking_warning_caps_score_below_good():
    product = with_id(base_product(**RICH, title="icon arrow left bold Share: Favorite (48) Áo thun cotton local brand unisex"))
    clean = with_id(base_product(**RICH))
    raw = make_calculator(products=[clean], product_variants=_priced(clean)).calculate(PRODUCT_ID)
    result = make_calculator(products=[product], product_variants=_priced(product)).calculate(PRODUCT_ID)
    assert raw["score"] > 79 and raw["cap"] is None
    assert result["score"] == 79.0 and result["status"] == "needs_improvement"
    assert result["cap"] == {"score": 79.0, "raw": raw["score"], "fields": ["title"]}


def test_more_specific_category_is_suggested():
    product = with_id(base_product(title="Giày Sneaker Nam Êm Chân Đi Học", categories=["Giày dép"]))
    cats = [{"name": n} for n in ("Giày dép", "Sneaker", "Áo thun", "quần")]
    result = make_calculator(products=[product], product_variants=_priced(product), categories=cats).calculate(PRODUCT_ID)
    hint = next(w for w in result["warnings"] if w["field"] == "categories")
    assert hint["type"] == "info" and hint["target"] == "Sneaker"
    assert result["cap"] is None
