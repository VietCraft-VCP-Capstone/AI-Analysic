import pytest
from bson import ObjectId

from app.core.f29 import scoring
from app.core.f29.constants import EFFORT
from app.core.f29.todos import _impact, build_todos
from tests.f29.fake_mongo import make_calculator
from tests.f29.samples import PRODUCT_ID, base_product, with_id


class TestWarningsPriority0:

    def test_zero_images(self):
        calc = make_calculator()
        product = base_product(images=[])
        warnings = calc._get_warnings(product, [])
        fields = [w["field"] for w in warnings]
        assert "images" in fields
        assert all(w["impact"] == 0 for w in warnings)
        assert all(w["type"] == "warning" for w in warnings)

    def test_retail_price_below_base_cost(self):
        calc = make_calculator()
        product = base_product()
        variants = [{"retail_price": "50000", "base_cost": "80000"}]
        warnings = calc._get_warnings(product, variants)
        assert any(w["field"] == "variants.retail_price" for w in warnings)

    def test_moderation_rejected(self):
        calc = make_calculator()
        product = base_product(moderation_status="REJECTED", rejection_reason="Ảnh mờ")
        warnings = calc._get_warnings(product, [])
        msg = next(w for w in warnings if w["field"] == "moderation_status")
        assert "Ảnh mờ" in msg["message"]

    def test_default_weight_is_not_a_warning(self):
        calc = make_calculator()
        product = base_product(weight_g=500, dimensions_cm={"length": 10, "width": 10, "height": 10})
        assert not any(w["field"] == "weight_g" for w in calc._get_warnings(product, []))


class TestApprovedTags:
    def _ids(self, n):
        return [ObjectId() for _ in range(n)]

    def test_pending_tags_not_counted(self):
        a, b, c = self._ids(3)
        calc = make_calculator(tags=[{"_id": c, "status": "pending"}, {"_id": a, "status": "active"}])
        product = base_product(tag_ids=[a, b, c], tags=["x", "y", "z"])
        assert scoring.count_approved_tags(product, calc.pending_tag_ids()) == 2
        assert scoring.count_pending_tags(product, calc.pending_tag_ids()) == 1

    def test_legacy_product_without_tag_ids_counts_names(self):
        calc = make_calculator()
        assert scoring.count_approved_tags(base_product(tags=["a", "b"]), calc.pending_tag_ids()) == 2

    def test_todo_message_mentions_pending(self):
        (pending,) = self._ids(1)
        calc = make_calculator(tags=[{"_id": pending, "status": "pending"}])
        product = with_id(base_product(tag_ids=[pending], tags=["ly-tach"]))
        calc.live_db["products"].seed([product])
        result = calc.calculate(PRODUCT_ID)
        todo = next(t for t in result["todos"] if t.get("field") == "tags")
        assert todo["current_value"] == 0
        assert todo["message"] == "Chọn thêm 3 tag · 1 tag đang chờ duyệt"

    def test_no_warnings_for_healthy_product(self):
        calc = make_calculator()
        product = base_product()
        variants = [{"retail_price": "150000", "base_cost": "80000"}]
        warnings = calc._get_warnings(product, variants)
        assert warnings == []


class TestTodosFromBreakdown:

    def _calc(self, images):
        main = with_id(base_product(
            images=images,
            description="x" * 160,
            tags=["a", "b", "c"],
            category_ids=["cat_giay"],
            product_type="READY_TO_SHIP",
        ))
        variants = [{"product_id": main["_id"], "is_active": True, "stock_quantity": 10,
                     "retail_price": "150000", "base_cost": "80000"}]
        return make_calculator(products=[main], product_variants=variants)

    def test_image_todo_message_and_impact(self):
        result = self._calc(["i1.jpg", "i2.jpg"]).calculate(PRODUCT_ID)
        todo = next(t for t in result["todos"] if t["field"] == "image")
        assert todo["current_value"] == 2
        assert todo["target"] == 6
        assert todo["message"] == "Thêm 4 ảnh (đang có 2/6)"
        assert todo["impact"] == pytest.approx(18.0, abs=0.05)

    def test_todos_sorted_by_impact_then_effort(self):
        result = self._calc(["i1.jpg", "i2.jpg"]).calculate(PRODUCT_ID)
        keys = [(-t["impact"], EFFORT[t["code"]]) for t in result["todos"]]
        assert keys == sorted(keys)

    def test_image_target_is_fixed_policy(self):
        result = self._calc(["i1.jpg"]).calculate(PRODUCT_ID)
        todo = next(t for t in result["todos"] if t["code"] == "image")
        assert todo["target"] == 6


def test_review_impact_is_real_gain():
    row = {"key": "review", "value": 1000, "n_good": 900, "p0": 0.8, "m": 5.0,
           "weight": 5, "points": 4.5, "sub_score": 90.0}
    assert _impact(row) < 0.1
    assert all(t["code"] != "review" for t in build_todos([row]))
