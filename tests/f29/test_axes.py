import pytest

from app.core.f29.scoring import (
    bayes_shrunk_rating,
    content_axis_score,
    content_component_scores,
    rating_axis_score,
)
from tests.f29.fake_mongo import make_calculator
from tests.f29.samples import base_product


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
        product = base_product(images=[])
        calc = make_calculator()
        score, warnings = calc._get_content_score(product)
        assert all("ảnh" not in h["message"].lower() for h in warnings)
        assert score == pytest.approx(66.7, abs=0.1)
        assert score < 100.0

    def test_good_product_full_marks(self):
        product = base_product()
        calc = make_calculator()
        score, warnings = calc._get_content_score(product)
        assert score == 100.0
        assert warnings == []

    def test_short_title_hint_points_to_title(self):
        _, hints = make_calculator()._get_content_score(base_product(title="Vong tay"))
        assert [h["field"] for h in hints] == ["title"]

    def test_unavailable_component_is_skipped(self):
        comps = content_component_scores(n_images=5, desc_len=75, n_tags=None)
        assert set(comps) == {"images", "description"}
        assert content_axis_score(comps) == pytest.approx(75.0)


class TestRatingScale:
    @pytest.mark.parametrize("stars, expected", [(1.0, 0.0), (3.0, 50.0), (5.0, 100.0)])
    def test_rating_axis_score_anchors(self, stars, expected):
        assert rating_axis_score(stars) == pytest.approx(expected)

    def test_bayes_shrinkage(self):
        assert bayes_shrunk_rating(0, 0, 4.0) is None
        assert rating_axis_score(bayes_shrunk_rating(10, 10, 4.0)) == pytest.approx(62.5)
