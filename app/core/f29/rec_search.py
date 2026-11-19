from typing import Any, Dict, List, Optional

from app.core.f29 import factors_v3 as f3
from app.core.f29.rec_base import make


def _tags_points(tags: Dict[str, Any], queries: List[Dict[str, Any]], approved: Optional[int] = None) -> float:
    ev = tags["evidence"]
    return f3.tags_row(ev["approved"] if approved is None else approved, ev["pending"], queries,
                       tags["method"])["points"]


def tag_recs(tags: Dict[str, Any], queries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    ev = tags["evidence"]
    if ev["approved"]:
        return []
    gain = _tags_points(tags, queries, approved=1) - tags["points"]
    why = "Chưa có tag đã duyệt"
    if ev["pending"]:
        why += f", còn {ev['pending']} tag đang chờ duyệt"
    action = "Chọn ít nhất 1 tag có sẵn của sàn" + (" (tag bạn tự tạo phải chờ admin duyệt mới được tính)" if ev["pending"] else "")
    return [make("info", "tags", "tags", "Thêm tag", why, action, "tags", gain, tags["method"])]


TOP = 3
CAVEAT = "Chỉ thêm từ đúng với sản phẩm của bạn, thêm sai thì khách vào xem rồi thoát ra"


def _list(rows: List[Dict[str, Any]]) -> str:
    return ", ".join(f'"{r["query"]}" ({r["searches"]} lần)' for r in rows)


def search_recs(tags: Dict[str, Any], queries: List[Dict[str, Any]], zero_result: List[Dict[str, Any]],
                category: Optional[str]) -> List[Dict[str, Any]]:
    recs = []
    missing = [q for q in queries if not q["covered"]][:TOP]
    if missing:
        names = {q["query"] for q in missing}
        flipped = [{**r, "covered": True} if r["query"] in names else r for r in queries]
        gain = _tags_points(tags, flipped) - tags["points"]
        why = f"30 ngày qua khách hay tìm trong danh mục {category}: {_list(missing)}. Tên và tag của bạn chưa có các từ này"
        recs.append(make("search", "missing", "tags", "Thêm từ khách đang tìm", why, CAVEAT, "tags", gain,
                         tags["method"], {"queries": missing}))
    seen = {q["query"] for q in queries}
    zero = [z for z in zero_result if z["query"] not in seen][:TOP]
    if zero:
        why = f"30 ngày qua khách tìm {_list(zero)} nhưng sàn không có sản phẩm nào khớp"
        recs.append(make("search", "zero", "tags", "Từ khách tìm không ra kết quả", why, CAVEAT, "tags", 0.0, "rule",
                         {"queries": zero}))
    return recs
