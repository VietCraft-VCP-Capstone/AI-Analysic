"""Chấm từng trục và gộp điểm tổng."""

from datetime import timedelta

import pytest

from app.core.f29.constants import MIN_IMAGES
from app.core.f29.scoring import (
    bayes_shrunk_rating,
    content_axis_score,
    content_component_scores,
    rating_axis_score,
)
from tests.f29.fake_mongo import make_calculator
from tests.f29.samples import NOW, base_product


class TestStatus:
    def test_status_good(self):
        calc = make_calculator()
        assert calc._get_status_from_score(85) == "good"

    def test_status_needs_improvement(self):
        calc = make_calculator()
        assert calc._get_status_from_score(65) == "needs_improvement"

    def test_status_poor(self):
        calc = make_calculator()
        assert calc._get_status_from_score(40) == "poor"


class TestContentScore:
    def test_no_images_not_full_marks_but_not_zero(self):
        """0 ảnh kéo điểm xuống nhưng mô tả và tag vẫn đóng góp."""
        product = base_product(images=[])
        calc = make_calculator()
        score, warnings = calc._get_content_score(product)
        assert all("ảnh" not in h["message"].lower() for h in warnings)
        # ảnh=0, mô tả (>=150 ký tự)=100, tag (3 tag)=100 -> trung bình (0+100+100)/3
        assert score == pytest.approx(66.7, abs=0.1)
        assert score < 100.0

    def test_good_product_full_marks(self):
        product = base_product()  # 5 ảnh, mô tả >=150 ký tự, 3 tag
        calc = make_calculator()
        score, warnings = calc._get_content_score(product)
        assert score == 100.0
        assert warnings == []

    def test_short_title_hint_points_to_title(self):
        _, hints = make_calculator()._get_content_score(base_product(title="Vong tay"))
        assert [h["field"] for h in hints] == ["title"]

    def test_component_formula_matches_todo_recompute(self):
        """Điểm thành phần trong todos phải khớp công thức chấm thật."""
        calc = make_calculator()
        comps = calc._content_component_scores(n_images=2, desc_len=0, n_tags=0)
        assert comps["images"] == pytest.approx((2 / MIN_IMAGES) * 100.0)
        assert comps["description"] == 0.0
        assert comps["tags"] == 0.0


    def test_unavailable_component_is_skipped(self):
        """Nguồn không có tag (Olist) chấm trên 2 thành phần còn lại, không cho tag 0 điểm."""
        comps = content_component_scores(n_images=5, desc_len=75, n_tags=None)
        assert set(comps) == {"images", "description"}
        assert content_axis_score(comps) == pytest.approx(75.0)


class TestRatingScale:
    @pytest.mark.parametrize("stars, expected", [(1.0, 0.0), (3.0, 50.0), (5.0, 100.0)])
    def test_rating_axis_score_anchors(self, stars, expected):
        assert rating_axis_score(stars) == pytest.approx(expected)

    def test_bayes_shrinkage(self):
        assert bayes_shrunk_rating(0, 0, 4.0) is None
        # 10 review 1★, C=4, m=50 -> (10 + 200)/60 = 3.5 -> 62.5 điểm
        assert rating_axis_score(bayes_shrunk_rating(10, 10, 4.0)) == pytest.approx(62.5)


class TestFreshnessScore:
    def test_new_product_full_score(self):
        calc = make_calculator()
        product = {"updated_at": NOW, "content_changed_at": NOW}
        assert calc._get_freshness_score(product) == 100.0

    def test_old_product_zero_score(self):
        calc = make_calculator()
        old = NOW - timedelta(days=400)
        product = {"updated_at": old, "content_changed_at": old}
        assert calc._get_freshness_score(product) == 0.0

    def test_naive_datetime_from_mongo_does_not_crash(self):
        """Datetime naive từ Mongo không được làm lỗi phép trừ ngày."""
        calc = make_calculator()
        naive_recent = (NOW - timedelta(days=10)).replace(tzinfo=None)
        product = {"updated_at": naive_recent, "content_changed_at": naive_recent}
        score = calc._get_freshness_score(product)  # không được raise TypeError
        assert score == 100.0

    def test_linear_decay_between_90_and_365_days(self):
        calc = make_calculator()
        mid = NOW - timedelta(days=227)  # giữa 90 và 365
        product = {"content_changed_at": mid}
        score = calc._get_freshness_score(product)
        assert 0.0 < score < 100.0


class TestInventoryScore:
    def test_not_ready_to_ship_is_na(self):
        calc = make_calculator()
        product = {"product_type": "POD_TEMPLATE"}
        assert calc._get_inventory_score(product, []) is None

    def test_no_active_variants_is_na(self):
        calc = make_calculator()
        product = {"product_type": "READY_TO_SHIP"}
        variants = [{"is_active": False, "stock_quantity": 10}]
        assert calc._get_inventory_score(product, variants) is None

    def test_ratio_of_in_stock_variants(self):
        calc = make_calculator()
        product = {"product_type": "READY_TO_SHIP"}
        variants = [
            {"is_active": True, "stock_quantity": 5},
            {"is_active": True, "stock_quantity": 0},
            {"is_active": True, "stock_quantity": 3},
            {"is_active": True, "stock_quantity": 0},
        ]
        score = calc._get_inventory_score(product, variants)
        assert score == 50.0  # 2/4 còn hàng


class TestTotalScoreReweighting:
    """Trục n/a bị loại, trọng số còn lại chia lại về tổng 1."""

    def test_two_axes_missing_reweights_correctly(self):
        calc = make_calculator()
        axes = {"rating": None, "content": 80.0, "inventory": None,
                "freshness": 100.0, "conversion": None}
        total = calc._total_score(axes)
        # chỉ còn content(.20) + freshness(.10), tổng trọng số .30
        expected = round((80.0 * 0.20 + 100.0 * 0.10) / 0.30, 1)
        assert total == expected == 86.7

    def test_all_axes_missing_returns_none(self):
        calc = make_calculator()
        axes = {"rating": None, "content": None, "inventory": None,
                "freshness": None, "conversion": None}
        assert calc._total_score(axes) is None

    def test_no_axis_missing_equals_plain_weighted_average(self):
        calc = make_calculator()
        axes = {"rating": 80.0, "content": 80.0, "inventory": 80.0,
                "freshness": 80.0, "conversion": 80.0}
        assert calc._total_score(axes) == 80.0
