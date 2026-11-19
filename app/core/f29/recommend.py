from typing import Any, Dict, List, Optional

from app.core.f29 import title_check
from app.core.f29.constants import FACTOR_WEIGHT
from app.core.f29.rec_base import factor, make, num
from app.core.f29.rec_desc import description_recs
from app.core.f29.rec_image import image_recs
from app.core.f29.rec_info import category_recs, review_recs
from app.core.f29.rec_search import search_recs, tag_recs

METHOD_RANK = {"rule": 0, "heuristic": 1, "weak_supervision": 2, "ml_unvalidated": 3}
BLOCKER_TITLES = {
    "title": "Tên có thông tin liên hệ hoặc chữ thừa",
    "materials": "Chất liệu không khớp tên",
    "moderation_status": "Bị từ chối kiểm duyệt",
    "images": "Chưa có ảnh",
    "variants.retail_price": "Giá bán thấp hơn giá vốn",
    "variants.stock": "Hết hàng",
}
BLOCKER_ACTIONS = {
    "title": "Sửa tên sản phẩm, bỏ chữ thừa và thông tin liên hệ",
    "materials": "Sửa ô Chất liệu cho khớp với tên",
    "moderation_status": "Sửa theo lý do từ chối rồi gửi duyệt lại",
    "images": "Thêm ít nhất 1 ảnh sản phẩm",
    "variants.retail_price": "Nâng giá bán cao hơn giá vốn",
    "variants.stock": "Nhập tồn kho cho ít nhất 1 biến thể đang bán",
}


def _title_target(title: str) -> Optional[str]:
    return next((h["target"] for h in title_check.check(title) if h.get("target")), None)


def _blocker_recs(result: Dict[str, Any]) -> List[Dict[str, Any]]:
    target = _title_target(result["content_snapshot"]["title"])
    recs = []
    for b in result["blockers"]:
        field, action, evidence = b["field"], BLOCKER_ACTIONS.get(b["field"], "Sửa mục này"), {}
        if field == "title" and target:
            action, evidence = f"Đổi tên thành “{target}”", {"target": target}
        title = BLOCKER_TITLES.get(field, "Lỗi chặn")
        recs.append(make("blocker", field, field, title, b["message"], action, field, 0.0, "rule", evidence))
    return recs


def _price_recs(price: Dict[str, Any]) -> List[Dict[str, Any]]:
    if price["state"] == "seller_missing":
        why = f"Chưa có giá bán (0/{FACTOR_WEIGHT} điểm). Giá trong vùng phổ biến sẽ được {FACTOR_WEIGHT} điểm"
        return [make("price", "missing", "price", "Chưa có giá bán", why,
                     "Nhập giá bán cho biến thể đang bán", "price", FACTOR_WEIGHT, "rule")]
    if price["state"] != "scored" or price["points"] >= FACTOR_WEIGHT:
        return []
    ev = price["evidence"]
    why = f"Giá nằm ngoài vùng phổ biến của {ev['n']} sản phẩm tương đồng (P10–P90: {num(ev['p10'])}–{num(ev['p90'])} đ)"
    return [make("price", "price", "price", "Giá bán", why, "Xem lại giá bán so với sản phẩm cùng loại", "price",
                 FACTOR_WEIGHT - price["points"], "rule", ev)]


def sort_recs(recs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(recs, key=lambda r: (r["kind"] != "blocker", -r["gain_points"] / r["effort"],
                                       METHOD_RANK[r["method"]]))


def build(result: Dict[str, Any], image: Dict[str, Any], queries: List[Dict[str, Any]],
          zero_result: List[Dict[str, Any]], category_hint: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    tags, desc = factor(result, "tags"), factor(result, "description")
    category = result["search"]["category"]
    recs = [*_blocker_recs(result), *tag_recs(tags, queries),
            *search_recs(tags, queries, zero_result, category),
            *image_recs(image, category), *description_recs(desc, result["blockers"], category),
            *review_recs(factor(result, "review")), *_price_recs(factor(result, "price")),
            *category_recs(category_hint)]
    return sort_recs(recs)
