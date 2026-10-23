import pytest
from bson import ObjectId

from app.core.f29 import weights
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
        assert result["model_version"] == "health-2.1"
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
        msg = "Chưa có giá bán cho biến thể nào · Tham khảo giá sản phẩm tương tự: 82.000đ–122.000đ"
        assert any(t["field"] == "price" and t["message"] == msg for t in result["todos"])

    def test_price_row_has_suggestion(self, fake_price_model):
        product = with_id(base_product())
        calc = make_calculator(products=[product], product_variants=_priced(product))
        price = next(r for r in calc.calculate(PRODUCT_ID)["breakdown"] if r["key"] == "price")
        assert price["suggestion"] == {"low": 82000.0, "mid": 100000.0, "high": 122000.0}

    def test_high_price_todo_mentions_reference(self, fake_price_model):
        product = with_id(base_product())
        variants = _priced(product, [{"is_active": True, "retail_price": "400000", "base_cost": "80000"}])
        result = make_calculator(products=[product], product_variants=variants).calculate(PRODUCT_ID)
        msg = next(t["message"] for t in result["todos"] if t["field"] == "price")
        assert msg == ("Giá cao hơn 300% so với mức giữa cho sản phẩm tương tự (100.000đ) "
                       "· Tham khảo giá sản phẩm tương tự: 82.000đ–122.000đ")

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
    def _sample_result(self, score=72.5):
        return {
            "product_id": PRODUCT_ID,
            "date": NOW.date().isoformat(),
            "score": score,
            "status": "needs_improvement",
            "axes": {"image": 100.0, "description": 100.0, "tags": 100.0, "review": 0.0, "price": 0.0},
            "axes_missing": ["review", "price"],
            "todos": [],
            "computed_at": NOW.isoformat().replace("+00:00", "Z"),
            "model_version": "health-2.1",
            "content_hash": "abc123",
            "inputs_hash": "def456",
        }

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
