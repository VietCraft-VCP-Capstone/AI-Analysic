from typing import Any, Dict, List, Optional

from app.core.f29.rec_base import make, scope


def _empty(desc: Dict[str, Any], category: Optional[str]) -> List[Dict[str, Any]]:
    ev = desc["evidence"]
    where = scope(category, ev["in_category"])
    why = (f"Chưa có mô tả, mặt bằng {where} là {ev['median_words']:g} từ. "
           f"Mô tả đủ 4 tiêu chí sẽ được {desc['weight']} điểm")
    return [make("info", "empty", "description", "Chưa có mô tả", why,
                 "Viết mô tả đủ 4 tiêu chí: số từ, kích thước, chất liệu, khác tên", "description",
                 desc["weight"], "rule", {"median_words": ev["median_words"]})]


def description_recs(desc: Dict[str, Any], blockers: List[Dict[str, str]],
                     category: Optional[str]) -> List[Dict[str, Any]]:
    if desc["state"] == "seller_missing":
        return _empty(desc, category)
    if desc["state"] != "scored":
        return []
    ev = desc["evidence"]
    checks = ev["checks"]
    per = desc["weight"] / len(checks)
    where = scope(category, ev["in_category"])
    recs = []
    if not checks["words"]:
        recs.append(make("info", "words", "description", "Mô tả quá ngắn",
                         f"Mô tả có {ev['words']} từ, mặt bằng {where} là {ev['median_words']:g} từ",
                         "Viết thêm mô tả: chất liệu, công dụng, cách dùng", "description", per, "rule"))
    if not checks["not_title"]:
        recs.append(make("info", "not_title", "description", "Mô tả trùng tên",
                         "Mô tả đang giống hệt tên sản phẩm", "Viết mô tả riêng, không lặp lại tên sản phẩm",
                         "description", per, "rule"))
    if not checks["size"]:
        recs.append(make("info", "size", "description", "Thiếu kích thước thật",
                         "Kích thước đang là giá trị mặc định 10×10×10 cm / 500 g",
                         "Nhập kích thước (cm) và cân nặng (g) thật", "description", per, "rule"))
    if not checks["material"] and not any(b["field"] == "materials" for b in blockers):
        recs.append(make("info", "material", "materials", "Thiếu chất liệu",
                         "Chưa ghi chất liệu trong mô tả, tên hoặc ô Chất liệu",
                         "Ghi rõ chất liệu (ví dụ: cotton, len, gốm…) vào ô Chất liệu", "material", per, "rule"))
    if not ev["care"]:
        recs.append(make("info", "care", "description", "Thiếu hướng dẫn giặt và bảo quản",
                         "Mô tả chưa có hướng dẫn giặt hoặc bảo quản",
                         "Thêm hướng dẫn giặt và bảo quản vào mô tả", "description", 0.0, "heuristic"))
    return recs
