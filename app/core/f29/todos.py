"""Cảnh báo ưu tiên 0 và việc cần sửa (§4.3)."""

from typing import Any, Dict, FrozenSet, List, Optional, Tuple

from app.api.v1._live import LOC_SP_THAT
from app.core.f29.constants import (
    EFFORT,
    MIN_CATEGORY_SAMPLE,
    MIN_DESCRIPTION_LENGTH,
    MIN_IMAGES,
    MIN_STOCK_RATIO_PCT,
    MIN_TAGS_APPROVED,
)
from app.core.f29.scoring import (
    category_key,
    content_axis_score,
    content_component_scores,
    count_approved_tags,
    count_pending_tags,
    median_or,
    to_float,
    total_score,
)


def build_warnings(product: Dict[str, Any], variants: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Không trừ/cộng điểm: 0 ảnh, bán dưới giá vốn, bị từ chối kiểm duyệt,
    cân nặng/kích thước còn mặc định (500g, 10×10×10cm)."""
    warnings: List[Dict[str, Any]] = []

    if len(product.get("images") or []) == 0:
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
                    f"Giá bán ({retail:,.0f}đ) thấp hơn giá vốn ({cost:,.0f}đ) ở ít nhất "
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


def tag_message(n_approved: int, n_pending: int, target: int) -> str:
    cho_duyet = f" · {n_pending} tag đang chờ duyệt" if n_pending else ""
    return f"Chọn thêm {target - n_approved} tag{cho_duyet}"


def content_peer_stats(live_db, cat_key: Optional[Any], pending_tag_ids: FrozenSet = frozenset()) -> Tuple[List[int], List[int], List[int], bool]:
    """Số ảnh / độ dài mô tả / số tag của listing cùng danh mục; danh mục quá ít
    listing thì lấy toàn sàn. Phần tử cuối cho biết mốc lấy từ danh mục hay không."""
    products_coll = live_db["products"]
    fields = {"images": 1, "description": 1, "tags": 1, "tag_ids": 1}

    peers: List[Dict[str, Any]] = []
    used_category = False
    if cat_key is not None:
        peers = list(products_coll.find({**LOC_SP_THAT, "category_ids.0": cat_key}, fields))
        if len(peers) >= MIN_CATEGORY_SAMPLE:
            used_category = True

    if not used_category:
        peers = list(products_coll.find(LOC_SP_THAT, fields))

    n_images = [len(p.get("images") or []) for p in peers]
    desc_lens = [len((p.get("description") or "")) for p in peers]
    n_tags = [count_approved_tags(p, pending_tag_ids) for p in peers]
    return n_images, desc_lens, n_tags, used_category


def build_todos(
    live_db,
    product: Dict[str, Any],
    axes: Dict[str, Optional[float]],
    n_images: int,
    desc_len: int,
    n_tags: int,
    inventory_ratio_pct: Optional[float],
    pending_tag_ids: FrozenSet = frozenset(),
) -> List[Dict[str, Any]]:
    """Chỉ cho thứ seller sửa trực tiếp (ảnh, mô tả, tag, tồn kho). Mốc =
    max(trung vị, mức sàn); `impact` = điểm tổng chấm lại khi kéo đúng chỉ số
    đó lên mốc. Sắp theo impact / effort."""
    current_total = total_score(axes)
    if current_total is None:
        return []

    img_peers, desc_peers, tag_peers, _ = content_peer_stats(live_db, category_key(product), pending_tag_ids)

    moc_anh = max(int(round(median_or(img_peers, MIN_IMAGES))), MIN_IMAGES)
    moc_mo_ta = max(int(round(median_or(desc_peers, MIN_DESCRIPTION_LENGTH))), MIN_DESCRIPTION_LENGTH)
    moc_tag = max(int(round(median_or(tag_peers, MIN_TAGS_APPROVED))), MIN_TAGS_APPROVED)

    candidates: List[Dict[str, Any]] = []

    def _gain_from_content_override(**overrides) -> float:
        vals = {"n_images": n_images, "desc_len": desc_len, "n_tags": n_tags}
        vals.update(overrides)
        comps = content_component_scores(vals["n_images"], vals["desc_len"], vals["n_tags"])
        new_content = round(content_axis_score(comps), 1)
        new_total = total_score({**axes, "content": new_content})
        if new_total is None:
            return 0.0
        return round(max(0.0, new_total - current_total), 1)

    if n_images < moc_anh:
        gain = _gain_from_content_override(n_images=moc_anh)
        if gain > 0:
            candidates.append({
                "type": "todo", "field": "images",
                "message": f"Thêm {moc_anh - n_images} ảnh (đang có {n_images})",
                "current_value": n_images, "target": moc_anh,
                "impact": gain, "_effort": EFFORT["images"],
            })

    if desc_len < moc_mo_ta:
        gain = _gain_from_content_override(desc_len=moc_mo_ta)
        if gain > 0:
            candidates.append({
                "type": "todo", "field": "description",
                "message": f"Viết mô tả dài hơn ({desc_len}/{moc_mo_ta} ký tự)",
                "current_value": desc_len, "target": moc_mo_ta,
                "impact": gain, "_effort": EFFORT["description"],
            })

    if n_tags < moc_tag:
        gain = _gain_from_content_override(n_tags=moc_tag)
        if gain > 0:
            candidates.append({
                "type": "todo", "field": "tags",
                "message": tag_message(n_tags, count_pending_tags(product, pending_tag_ids), moc_tag),
                "current_value": n_tags, "target": moc_tag,
                "impact": gain, "_effort": EFFORT["tags"],
            })

    if inventory_ratio_pct is not None and inventory_ratio_pct < MIN_STOCK_RATIO_PCT:
        new_inventory = round(min(100.0, MIN_STOCK_RATIO_PCT), 1)
        new_total = total_score({**axes, "inventory": new_inventory})
        gain = round(max(0.0, (new_total - current_total) if new_total is not None else 0.0), 1)
        if gain > 0:
            candidates.append({
                "type": "todo", "field": "stock_quantity",
                "message": f"Nhập thêm hàng: {inventory_ratio_pct:.0f}% phân loại còn hàng",
                "current_value": round(inventory_ratio_pct, 1), "target": MIN_STOCK_RATIO_PCT,
                "impact": gain, "_effort": EFFORT["stock"],
            })

    candidates.sort(key=lambda c: c["impact"] / c["_effort"], reverse=True)
    for c in candidates:
        c.pop("_effort", None)
    return candidates
