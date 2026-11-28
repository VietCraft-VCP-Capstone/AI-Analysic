from typing import Any, Dict, List, Optional

from app.core.f29.score import text_rules
from app.core.f29.score.price import HIGH_PCT
from app.core.f29.score.rec_factors import factor, make, num
from app.core.f29.score.rec_factors import description_recs
from app.core.f29.score.rec_factors import image_recs
from app.core.f29.score.rec_factors import review_recs
from app.core.f29.score.rec_factors import search_recs, tag_recs
from app.core.f29.score.scoring import to_float


def _vnd(amount: float) -> str:
    return f"{amount:,.0f}".replace(",", ".") + "đ"


def build_warnings(product: Dict[str, Any], variants: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    warnings: List[Dict[str, Any]] = []

    imgs = product.get("images")
    n_imgs = len(imgs) if isinstance(imgs, list) else (1 if isinstance(imgs, str) and imgs.strip() else 0)
    if n_imgs == 0:
        warnings.append({
            "type": "warning",
            "field": "images",
            "message": "Chưa có ảnh nào — sản phẩm gần như không hiển thị được trên sàn.",
            "current_value": 0,
            "target": None,
            "impact": 0,
        })

    for v in variants:
        retail = to_float(v.get("retail_price"))
        cost = to_float(v.get("base_cost"))
        if retail is not None and cost is not None and retail < cost:
            warnings.append({
                "type": "warning",
                "field": "variants.retail_price",
                "message": (
                    f"Giá bán ({_vnd(retail)}) thấp hơn giá vốn ({_vnd(cost)}) ở ít nhất "
                    "một biến thể — đang bán lỗ."
                ),
                "current_value": retail,
                "target": cost,
                "impact": 0,
            })
            break

    if product.get("moderation_status") == "REJECTED":
        ly_do = product.get("rejection_reason")
        warnings.append({
            "type": "warning",
            "field": "moderation_status",
            "message": ("Sản phẩm đang bị từ chối kiểm duyệt" +
                        (f": {ly_do}" if ly_do else ".")),
            "current_value": "REJECTED",
            "target": "APPROVED",
            "impact": 0,
        })

    return warnings


CODE = {"images": "image", "materials": "material"}


def _item(kind: str, r: Dict[str, Any], message: str, impact: float) -> Dict[str, Any]:
    ev = r["evidence"]
    return {"type": kind, "code": CODE.get(r["field"], r["field"]), "field": r["field"], "message": message,
            "current_value": ev.get("current_value"), "target": ev.get("target"), "impact": impact,
            "method": r["method"]}


def todos_of(recs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [_item("todo", r, r["action"], r["gain_points"]) for r in recs if r["kind"] != "blocker"]


def warnings_of(recs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [_item("warning", r, r["why"], 0) for r in recs if r["kind"] == "blocker"]


METHOD_RANK = {"rule": 0, "learned": 1, "heuristic": 1, "weak_supervision": 2, "ml_unvalidated": 3}
CHECK_EFFORT = {"print": "images", "image": "images", "duplicate": "images", "description": "description"}
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
    return next((h["target"] for h in text_rules.check(title) if h.get("target")), None)


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
    weight = price["weight"]
    if price["state"] == "seller_missing":
        why = f"Chưa có giá bán (0/{weight} điểm). Nhập giá để được chấm mục này"
        return [make("price", "missing", "price", "Chưa có giá bán", why,
                     "Nhập giá bán cho biến thể đang bán", "price", weight, "rule")]
    if price["state"] != "scored":
        return []
    ev = price["evidence"]
    band = f"vùng phổ biến {num(ev['p10'])}–{num(ev['p90'])} đ của {ev['n']} sản phẩm tương đồng"
    if ev["pct"] > HIGH_PCT and not ev["reasons"]:
        return [make("price", "price", "price", "Giá cao chưa có lý do", f"Giá cao hơn {band}",
                     "Nêu rõ lý do giá trong mô tả: cách làm (làm tay, chạm khắc), kích thước, xuất xứ hoặc bảo hành",
                     "description", 0.0, "rule", ev)]
    if ev["pct"] < 100 - HIGH_PCT:
        return [make("info", "price_low", "price", "Giá thấp bất thường", f"Giá thấp hơn {band}",
                     "Kiểm tra lại giá có nhập nhầm không", "price", 0.0, "rule", ev)]
    return []


def _check_recs(checks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    recs = []
    for c in checks:
        if c.get("mode") != "live" or c.get("severity") not in ("block", "warn"):
            continue
        block = c["severity"] == "block"
        method = "rule" if c.get("model_version") == "rule" else "ml_unvalidated"
        recs.append(make("blocker" if block else "info", c["id"], c["pillar"], "Chặn" if block else "Cảnh báo",
                         c["action"], c["action"], CHECK_EFFORT[c["pillar"]], 0.0, method, {"check": c["id"]}))
    return recs


def sort_recs(recs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(recs, key=lambda r: (r["kind"] != "blocker", "check" not in r.get("evidence", {}),
                                       -r["gain_points"] / r["effort"], METHOD_RANK[r["method"]]))


def build(result: Dict[str, Any], image: Dict[str, Any], queries: List[Dict[str, Any]],
          zero_result: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    tags, desc = factor(result, "tags"), factor(result, "description")
    category = result["search"]["category"]
    recs = [*_blocker_recs(result), *_check_recs(result.get("checks") or []), *tag_recs(tags, queries),
            *search_recs(tags, queries, zero_result, category),
            *image_recs(image, category), *description_recs(desc, result["blockers"], category),
            *review_recs(factor(result, "review")), *_price_recs(factor(result, "price"))]
    return sort_recs(recs)
