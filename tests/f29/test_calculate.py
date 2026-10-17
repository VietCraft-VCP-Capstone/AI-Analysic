from tests.f29.fake_mongo import make_calculator
from tests.f29.samples import NOW, PRODUCT_ID, base_product, with_id


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

    def test_happy_path_shape_and_axes_missing(self):
        product = with_id(base_product())
        variants = [
            {"product_id": product["_id"], "is_active": True, "stock_quantity": 10,
             "retail_price": "150000", "base_cost": "80000"},
        ]
        calc = make_calculator(products=[product], product_variants=variants)
        result = calc.calculate(PRODUCT_ID)

        assert result["product_id"] == PRODUCT_ID
        assert result["score"] is not None
        assert result["status"] in ("good", "needs_improvement", "poor")
        assert set(result["axes"].keys()) == {"conversion", "rating", "content", "inventory", "freshness"}
        assert "conversion" in result["axes_missing"]
        assert "rating" in result["axes_missing"]
        assert result["axes"]["conversion"] is None
        assert result["axes"]["rating"] is None
        assert result["axes"]["inventory"] == 100.0
        assert result["content_hash"]
        assert result["inputs_hash"]
        assert result["content_changed_at"] is not None

    def test_axis_reweighting_end_to_end(self):
        product = with_id(base_product(product_type="POD_TEMPLATE"))
        calc = make_calculator(products=[product])
        result = calc.calculate(PRODUCT_ID)

        assert sorted(result["axes_missing"]) == ["conversion", "inventory", "rating"]
        content = result["axes"]["content"]
        freshness = result["axes"]["freshness"]
        expected = round((content * 0.20 + freshness * 0.10) / 0.30, 1)
        assert result["score"] == expected

    def test_warnings_appear_first_in_todos(self):
        product = with_id(base_product(images=[], moderation_status="REJECTED"))
        variants = [
            {"product_id": product["_id"], "is_active": True, "stock_quantity": 10,
             "retail_price": "50000", "base_cost": "80000"},
        ]
        calc = make_calculator(products=[product], product_variants=variants)
        result = calc.calculate(PRODUCT_ID)

        todos = result["todos"]
        warning_fields = {t["field"] for t in todos if t["type"] == "warning"}
        assert {"images", "variants.retail_price", "moderation_status"} == warning_fields
        first_n = len(warning_fields)
        assert all(t["type"] == "warning" for t in todos[:first_n])
        assert all(t["impact"] == 0 for t in todos if t["type"] == "warning")


class TestSaveIdempotency:
    def _sample_result(self, score=72.5):
        return {
            "product_id": PRODUCT_ID,
            "date": NOW.date().isoformat(),
            "score": score,
            "status": "needs_improvement",
            "axes": {"conversion": None, "rating": None, "content": 80.0,
                     "inventory": 100.0, "freshness": 100.0},
            "axes_missing": ["conversion", "rating"],
            "todos": [],
            "computed_at": NOW.isoformat().replace("+00:00", "Z"),
            "model_version": "health-1.0",
            "content_hash": "abc123",
            "content_changed_at": NOW,
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
        calc = make_calculator(products=[product])

        result1 = calc.calculate(PRODUCT_ID)
        calc.save(result1)
        result2 = calc.calculate(PRODUCT_ID)
        calc.save(result2)

        docs = calc.live_db["listing_health_scores"].docs
        assert len(docs) == 1
        assert docs[0]["score"] == result1["score"] == result2["score"]
        assert docs[0]["content_hash"] == result1["content_hash"]

    def test_save_returns_none_for_invalid_result(self):
        calc = make_calculator()
        assert calc.save(None) is None
        assert calc.save({"product_id": "khong-phai-objectid", "date": "2026-10-15"}) is None
