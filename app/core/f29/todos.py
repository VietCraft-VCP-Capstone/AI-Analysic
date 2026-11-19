from typing import Any, Dict, List

from app.core.f29.scoring import to_float


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
