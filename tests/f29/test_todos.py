"""Cảnh báo ưu tiên 0 và việc cần sửa (§4.3)."""

from bson import ObjectId
import pytest

from app.core.f29 import scoring
from app.core.f29.constants import EFFORT, MIN_IMAGES
from tests.f29.fake_mongo import make_calculator
from tests.f29.samples import PRODUCT_ID, base_product, with_id


class TestWarningsPriority0:
    """§4.3: cảnh báo ưu tiên 0 — không ảnh hưởng điểm."""

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
        # Phí vận chuyển không dùng cân nặng sản phẩm và form không có ô này.
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
        assert "đang chờ admin duyệt" in todo["message"]

    def test_no_warnings_for_healthy_product(self):
        calc = make_calculator()
        product = base_product()
        variants = [{"retail_price": "150000", "base_cost": "80000"}]
        warnings = calc._get_warnings(product, variants)
        assert warnings == []


class TestTodosWithCategoryMedian:
    """§4.3: mốc = max(trung vị danh mục, mức sàn); expected_gain = chấm lại
    điểm THẬT khi kéo chỉ số đó lên mốc — không phải số cố định."""

    def _build_scene(self):
        main = with_id(base_product(
            images=["i1.jpg", "i2.jpg"],  # 2 ảnh — dưới cả mốc sàn (5) lẫn mốc danh mục
            description="x" * 160,         # >= 150 -> đã tối đa, không sinh todo mô tả
            tags=["a", "b", "c"],          # 3 tag đã duyệt -> đã đạt mốc sàn (3)
            category_ids=["cat_giay"],
            product_type="READY_TO_SHIP",
        ))
        peers = []
        # Trung vị ảnh của 10 listing cùng danh mục (không tính sản phẩm đang
        # chấm) = 6 — CAO HƠN mức sàn 5, nên mốc phải lấy trung vị danh mục.
        for i, n_anh in enumerate([8, 8, 8, 6, 6, 6, 5, 5, 5, 4]):
            peers.append({
                "_id": ObjectId(), "category_ids": ["cat_giay"],
                "images": [f"p{i}_{j}.jpg" for j in range(n_anh)],
                "description": "", "tags": [],
            })
        variants = [
            {"product_id": main["_id"], "is_active": True, "stock_quantity": 10,
             "retail_price": "150000", "base_cost": "80000"},
            {"product_id": main["_id"], "is_active": True, "stock_quantity": 5,
             "retail_price": "150000", "base_cost": "80000"},
            {"product_id": main["_id"], "is_active": True, "stock_quantity": 3,
             "retail_price": "150000", "base_cost": "80000"},
            {"product_id": main["_id"], "is_active": True, "stock_quantity": 1,
             "retail_price": "150000", "base_cost": "80000"},
        ]  # 4/4 còn hàng -> tồn kho 100%, không sinh todo tồn kho
        return make_calculator(products=[main] + peers, product_variants=variants)

    def test_moc_anh_uses_category_median_not_floor(self):
        calc = self._build_scene()
        result = calc.calculate(PRODUCT_ID)
        todos = [t for t in result["todos"] if t["type"] == "todo"]
        assert len(todos) == 1  # chỉ ảnh: mô tả/tag đã đạt mốc, tồn kho 100%
        todo = todos[0]
        assert todo["field"] == "images"
        assert todo["current_value"] == 2
        assert todo["target"] == 6  # trung vị danh mục (6) > mức sàn (5)
        assert "danh mục" in todo["message"]

    def test_expected_gain_is_real_recomputed_score_delta(self):
        """Chấm tay: content hiện tại = (2/5*100 + 100 + 100)/3 = 80.0. Chỉ có
        content(.20) + inventory(.15) + freshness(.10) hợp lệ (rating n/a,
        conversion n/a) -> tổng trọng số .45.
        Điểm hiện tại = (80*.2 + 100*.15 + 100*.10)/.45 = 91.1
        Điểm nếu ảnh đạt mốc (6 >= MIN_IMAGES -> content=100) =
          (100*.2 + 100*.15 + 100*.10)/.45 = 100.0
        -> expected_gain = 100.0 - 91.1 = 8.9
        """
        calc = self._build_scene()
        result = calc.calculate(PRODUCT_ID)
        assert result["axes"]["content"] == 80.0
        assert result["axes"]["inventory"] == 100.0
        assert result["score"] == 91.1

        todo = next(t for t in result["todos"] if t["type"] == "todo" and t["field"] == "images")
        assert todo["impact"] == pytest.approx(8.9, abs=0.05)

    def test_todos_sorted_by_gain_over_effort(self):
        calc = self._build_scene()
        result = calc.calculate(PRODUCT_ID)
        todos = [t for t in result["todos"] if t["type"] == "todo"]
        ratios = [t["impact"] / EFFORT.get(
            {"images": "images", "description": "description",
             "tags": "tags", "stock_quantity": "stock"}[t["field"]], 1)
            for t in todos]
        assert ratios == sorted(ratios, reverse=True)

    def test_small_category_falls_back_to_market_median(self):
        """Danh mục có ít hơn MIN_CATEGORY_SAMPLE listing -> dùng trung vị toàn
        sàn (ở đây chỉ có đúng sản phẩm đang chấm, nên trung vị toàn sàn chính
        là ảnh của nó -> mốc tụt về mức sàn MIN_IMAGES)."""
        main = with_id(base_product(images=["i1.jpg"], category_ids=["cat_hiem"]))
        calc = make_calculator(products=[main])
        result = calc.calculate(PRODUCT_ID)
        todo = next(t for t in result["todos"] if t["type"] == "todo" and t["field"] == "images")
        assert todo["target"] == MIN_IMAGES  # không đủ 8 listing cùng danh mục -> mốc sàn
