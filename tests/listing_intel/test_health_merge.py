from datetime import datetime, timedelta, timezone

from app.core.listing_intel import advice
from app.core.listing_intel.service import _stale
from app.core.listing_intel.types import AxisResult, ListingInput

NOW = datetime(2026, 10, 21, 10)


def test_stale_when_edited_after_last_score():
    assert _stale(ListingInput("a"), None)
    assert _stale(ListingInput("a", updated_at=NOW), {"computed_at": NOW - timedelta(hours=1), "todos": []})
    assert not _stale(ListingInput("a", updated_at=NOW), {"computed_at": NOW + timedelta(hours=1), "todos": []})
    assert not _stale(ListingInput("a", updated_at=NOW), {"computed_at": datetime(2026, 10, 21, 11, tzinfo=timezone.utc), "todos": []})


def test_review_issue():
    assert advice.review_issue(ListingInput("a")) is None
    assert advice.review_issue(ListingInput("a", rating_count=0))["code"] == "no_reviews"
    assert advice.review_issue(ListingInput("a", rating_count=3, average_rating=3.5))["code"] == "low_rating"
    assert advice.review_issue(ListingInput("a", rating_count=3, average_rating=4.6)) is None


def test_review_advice_is_kept_in_checklist():
    issues = [{"code": f"c{i}", "message": "x"} for i in range(8)]
    out = advice.build({"image": AxisResult(issues=issues)}, {}, {}, {}, {"code": "no_reviews", "message": "r"})
    assert len(out) == advice.MAX_ITEMS
    assert out[-1]["code"] == "no_reviews" and out[-1]["axis"] == "market" and out[-1]["evidence"] == "practice"


def test_common_issues_counts_products_per_todo():
    from app.core.listing_intel.service import common_issues
    docs = [{"todos": [{"code": "no_images", "message": "Chưa có ảnh"}, {"code": "missing_color", "message": "Chưa nêu màu"}]},
            {"todos": [{"code": "no_images", "message": "Chưa có ảnh"}]}, {}]
    assert common_issues(docs) == [{"code": "no_images", "message": "Chưa có ảnh", "count": 2},
                                   {"code": "missing_color", "message": "Chưa nêu màu", "count": 1}]


def test_old_score_without_todos_is_stale():
    assert _stale(ListingInput("a"), {"computed_at": NOW, "score": 50})
