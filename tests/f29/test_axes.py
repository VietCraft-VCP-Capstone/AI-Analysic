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


class TestContentHints:
    def test_short_title_hint_points_to_title(self):
        hints = make_calculator()._get_content_hints(base_product(title="Vong tay"))
        assert [h["field"] for h in hints] == ["title"]
