from typing import Any, Dict, List, Optional

from app.core.f29 import factors_v3 as f3
from app.core.f29.rec_base import make, scope

ISSUE_LABEL = {"blurry": "mờ", "too_dark": "tối", "too_bright": "quá sáng", "low_resolution": "độ phân giải thấp"}
MISMATCH = "có thể không đúng sản phẩm (AI nhận diện, chưa kiểm chứng trên VietCraft)"


def _parts(img: Dict[str, Any]) -> List[str]:
    parts = ["trùng"] if img["duplicate"] else []
    parts += [ISSUE_LABEL.get(code, code) for code in img["issues"]]
    if img["category_match"] is False:
        parts.append(MISMATCH)
    return parts


def _per_image(image: Dict[str, Any]) -> List[Dict[str, Any]]:
    ev = image["evidence"]
    recs = []
    for i, img in enumerate(ev["images"], 1):
        parts = _parts(img)
        if not parts:
            continue
        counted = not img["duplicate"] and not img["issues"]
        fixed = f3.image_row({"state": "scored", "useful": ev["useful"] + 1}, ev["target"])
        gain = 0.0 if counted else fixed["points"] - image["points"]
        action = f"Thay hoặc chụp lại ảnh số {i}" if not counted else f"Kiểm tra ảnh số {i} có đúng sản phẩm không"
        method = "ml_unvalidated" if MISMATCH in parts else "heuristic"
        recs.append(make("image", str(i), "images", "Ảnh cần thay hoặc kiểm tra", f"Ảnh số {i}: {', '.join(parts)}",
                         action, "images", gain, method, {"index": i, "issues": img["issues"]}))
    return recs


def _coverage(image: Dict[str, Any], category: Optional[str]) -> Dict[str, Any]:
    ev = image["evidence"]
    fixed = f3.image_row({"state": "scored", "useful": ev["useful"] + 1}, ev["target"])
    where = scope(category, ev["in_category"])
    why = f"Thêm ảnh khác góc: bạn có {ev['useful']} ảnh đạt, sản phẩm {where} thường có {ev['median']:g} ảnh"
    return make("image", "coverage", "images", "Thêm ảnh khác góc", why,
                "Chụp thêm ảnh khác góc của sản phẩm", "images", fixed["points"] - image["points"], "heuristic",
                {"useful": ev["useful"], "median": ev["median"]})


def image_recs(image: Dict[str, Any], category: Optional[str]) -> List[Dict[str, Any]]:
    if image["state"] != "scored":
        return []
    recs = _per_image(image)
    if image["evidence"]["useful"] < image["evidence"]["median"]:
        recs.append(_coverage(image, category))
    return recs
