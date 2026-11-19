from typing import Any, Dict, List, Optional

from app.core.f29 import factors_v3 as f3
from app.core.f29.constants import FACTOR_WEIGHT
from app.core.f29.rec_base import make


def category_recs(hint: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not hint:
        return []
    return [make("info", "categories", "categories", "Đổi danh mục", hint["message"],
                 f"Đổi danh mục sang “{hint['target']}”", "categories", 0.0, "heuristic",
                 {"current": hint["current_value"], "target": hint["target"]})]


def review_recs(review: Dict[str, Any]) -> List[Dict[str, Any]]:
    if review["state"] != "scored" or review["points"] >= FACTOR_WEIGHT:
        return []
    ev = review["evidence"]
    fixed = f3.review_row(ev["good"] + 1, ev["total"] + 1, ev["p0"], ev["m"])
    why = f"Có {ev['good']}/{ev['total']} đánh giá tốt, mỗi đánh giá tốt thêm sẽ nâng điểm"
    return [make("info", "review", "review", "Thêm đánh giá tốt", why,
                 "Mời khách đã mua để lại đánh giá", "review", fixed["points"] - review["points"], "rule")]
