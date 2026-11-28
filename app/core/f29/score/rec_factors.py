from typing import Any, Dict, List, Optional

from app.core.f29.score import scoring
from app.core.f29.constants import EFFORT
from app.core.f29.constants import review_score


def make(kind: str, key: str, field: str, title: str, why: str, action: str, effort_key: str,
         gain: float, method: str, evidence: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {"id": f"{kind}:{key}", "kind": kind, "title": title, "why": why, "action": action,
            "field": field, "effort": EFFORT[effort_key], "gain_points": round(gain, 1),
            "method": method, "evidence": evidence or {}}


def factor(result: Dict[str, Any], key: str) -> Dict[str, Any]:
    return next(f for f in result["factors"] if f["key"] == key)


def num(value: float) -> str:
    return f"{value:,.0f}".replace(",", ".")


def scope(category: Optional[str], in_category: bool) -> str:
    return f"danh mục {category}" if in_category and category else "toàn sàn"


def _empty(desc: Dict[str, Any], category: Optional[str]) -> List[Dict[str, Any]]:
    ev = desc["evidence"]
    where = scope(category, ev["in_category"])
    why = (f"Chưa có mô tả, mặt bằng {where} là {ev['median_words']:g} từ. "
           "Mô tả đủ dài sẽ được cộng điểm")
    return [make("info", "empty", "description", "Chưa có mô tả", why,
                 "Viết mô tả đủ dài, có kích thước và chất liệu, không chép lại tên", "description",
                 scoring.gain(desc, ev["median_words"]), "rule", {"median_words": ev["median_words"]})]


def description_recs(desc: Dict[str, Any], blockers: List[Dict[str, str]],
                     category: Optional[str]) -> List[Dict[str, Any]]:
    if desc["state"] == "seller_missing":
        return _empty(desc, category)
    if desc["state"] != "scored":
        return []
    ev = desc["evidence"]
    checks = ev["checks"]
    where = scope(category, ev["in_category"])
    info = desc["weight"] * 50 / len(scoring.DESC_INFO) / 100
    recs = []
    if not checks["words"]:
        recs.append(make("info", "words", "description", "Mô tả quá ngắn",
                         f"Mô tả có {ev['words']} từ, mặt bằng {where} là {ev['median_words']:g} từ",
                         "Viết thêm mô tả: chất liệu, công dụng, cách dùng", "description",
                         scoring.gain(desc, ev["median_words"]), "rule"))
    if not checks["not_title"]:
        recs.append(make("info", "not_title", "description", "Mô tả trùng tên",
                         "Mô tả đang giống hệt tên sản phẩm", "Viết mô tả riêng, không lặp lại tên sản phẩm",
                         "description", info, "rule"))
    if not checks["size"]:
        recs.append(make("info", "size", "description", "Thiếu kích thước thật",
                         "Kích thước đang là giá trị mặc định 10×10×10 cm / 500 g",
                         "Nhập kích thước (cm) và cân nặng (g) thật", "description", info, "rule"))
    if not checks["material"] and not any(b["field"] == "materials" for b in blockers):
        recs.append(make("info", "material", "materials", "Thiếu chất liệu",
                         "Chưa ghi chất liệu trong mô tả, tên hoặc ô Chất liệu",
                         "Ghi rõ chất liệu (ví dụ: cotton, len, gốm…) vào ô Chất liệu", "material", info, "rule"))
    if not ev["care"]:
        recs.append(make("info", "care", "description", "Thiếu hướng dẫn giặt và bảo quản",
                         "Mô tả chưa có hướng dẫn giặt hoặc bảo quản",
                         "Thêm hướng dẫn giặt và bảo quản vào mô tả", "description", 0.0, "heuristic"))
    return recs


ISSUE_LABEL = {"blurry": "mờ", "too_dark": "tối", "too_bright": "quá sáng", "low_resolution": "độ phân giải thấp"}


def _parts(img: Dict[str, Any]) -> List[str]:
    parts = ["trùng"] if img["duplicate"] else []
    parts += [ISSUE_LABEL.get(code, code) for code in img.get("issues") or []]
    return parts


def _per_image(image: Dict[str, Any]) -> List[Dict[str, Any]]:
    ev = image["evidence"]
    recs = []
    for i, img in enumerate(ev["images"], 1):
        parts = _parts(img)
        if not parts:
            continue
        recs.append(make("image", str(i), "images", "Ảnh cần thay hoặc kiểm tra", f"Ảnh số {i}: {', '.join(parts)}",
                         f"Thay hoặc chụp lại ảnh số {i}", "images", scoring.gain(image, ev["useful"] + 1),
                         "heuristic", {"index": i, "issues": img["issues"]}))
    return recs


def _coverage(image: Dict[str, Any], category: Optional[str]) -> Dict[str, Any]:
    ev = image["evidence"]
    where = scope(category, ev["in_category"])
    why = f"Thêm ảnh khác góc: bạn có {ev['useful']} ảnh đạt, sản phẩm {where} thường có {ev['median']:g} ảnh"
    return make("image", "coverage", "images", "Thêm ảnh khác góc", why,
                "Chụp thêm ảnh khác góc của sản phẩm", "images", scoring.gain(image, ev["useful"] + 1), "heuristic",
                {"useful": ev["useful"], "median": ev["median"]})


def image_recs(image: Dict[str, Any], category: Optional[str]) -> List[Dict[str, Any]]:
    if image["state"] != "scored":
        return []
    recs = _per_image(image)
    if image["evidence"]["useful"] < image["evidence"]["median"]:
        recs.append(_coverage(image, category))
    return recs


def review_recs(review: Dict[str, Any]) -> List[Dict[str, Any]]:
    if review["state"] != "scored" or review["points"] >= review["weight"]:
        return []
    ev = review["evidence"]
    why = f"Có {ev['good']}/{ev['total']} đánh giá tốt, mỗi đánh giá tốt thêm sẽ nâng điểm"
    gain = scoring.gain(review, review_score(ev["good"] + 1, ev["total"] + 1, ev["p0"], ev["m"]))
    return [make("info", "review", "review", "Thêm đánh giá tốt", why,
                 "Mời khách đã mua để lại đánh giá", "review", gain, "rule")]


def tag_recs(tags: Dict[str, Any], queries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    ev = tags["evidence"]
    if ev["approved"]:
        return []
    gain = scoring.gain(tags, 1)
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
        why = f"30 ngày qua khách hay tìm trong danh mục {category}: {_list(missing)}. Tên và tag của bạn chưa có các từ này"
        recs.append(make("search", "missing", "tags", "Thêm từ khách đang tìm", why, CAVEAT, "tags", 0.0,
                         tags["method"], {"queries": missing}))
    seen = {q["query"] for q in queries}
    zero = [z for z in zero_result if z["query"] not in seen][:TOP]
    if zero:
        why = f"30 ngày qua khách tìm {_list(zero)} nhưng sàn không có sản phẩm nào khớp"
        recs.append(make("search", "zero", "tags", "Từ khách tìm không ra kết quả", why, CAVEAT, "tags", 0.0, "rule",
                         {"queries": zero}))
    return recs
