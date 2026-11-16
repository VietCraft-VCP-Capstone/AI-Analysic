import threading
import time
from typing import Any, Dict, FrozenSet, List, Optional, Tuple

from app.api.v1._live import LOC_SP_THAT
from app.core.f29.breakdown import score_of
from app.core.f29.constants import EFFORT, MIN_CATEGORY_SAMPLE, PRICE_CHECK_HIGH, PRICE_CHECK_LOW
from app.core.f29.factors import desc_words
from app.core.f29.scoring import count_approved_tags, to_float

PEER_STATS_TTL = 900
_peer_stats_cache: dict = {}
_peer_stats_lock = threading.Lock()


def clear_peer_stats_cache() -> None:
    with _peer_stats_lock:
        _peer_stats_cache.clear()


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


def tag_message(n_approved: int, n_pending: int, target: int) -> str:
    cho_duyet = f" · {n_pending} tag đang chờ duyệt" if n_pending else ""
    return f"Chọn thêm {target - n_approved} tag{cho_duyet}"


def content_peer_stats(live_db, cat_key: Optional[Any], pending_tag_ids: FrozenSet = frozenset()) -> Tuple[List[int], List[int], List[int], bool]:
    now = time.monotonic()
    cache_key = str(cat_key)
    with _peer_stats_lock:
        hit = _peer_stats_cache.get(cache_key)
        if hit and now - hit["at"] < PEER_STATS_TTL:
            return hit["value"]

    products_coll = live_db["products"]
    fields = {"images": 1, "description": 1, "tags": 1, "tag_ids": 1}

    peers: List[Dict[str, Any]] = []
    used_category = False
    if cat_key is not None:
        peers = list(products_coll.find({**LOC_SP_THAT, "categories.0": cat_key}, fields))
        if not peers:
            peers = list(products_coll.find({**LOC_SP_THAT, "category_ids.0": cat_key}, fields))
        if len(peers) >= MIN_CATEGORY_SAMPLE:
            used_category = True

    if not used_category:
        peers = list(products_coll.find(LOC_SP_THAT, fields))

    def _count_img(p):
        raw = p.get("images")
        if isinstance(raw, list):
            return len(raw)
        if isinstance(raw, str) and raw.strip():
            return 1
        return 0

    def _desc_len(p):
        return desc_words(p.get("description"))

    n_images = [_count_img(p) for p in peers]
    desc_lens = [_desc_len(p) for p in peers]
    n_tags = [count_approved_tags(p, pending_tag_ids) for p in peers]
    res = (n_images, desc_lens, n_tags, used_category)
    with _peer_stats_lock:
        _peer_stats_cache[cache_key] = {"value": res, "at": now}
    return res


def _popular(row: Dict[str, Any]) -> str:
    s = row.get("suggestion")
    return f" · Tham khảo: {_vnd(s['low'])}–{_vnd(s['high'])}" if s else ""


def _peers(ref: Dict[str, Any]) -> str:
    mats = ", ".join(ref.get("materials") or [])
    return f"{ref['n']} sản phẩm cùng loại, cùng chất liệu" + (f" {mats}" if mats else "")


def price_check(row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    reference = row.get("reference") or {}
    value, ref = row.get("value"), reference.get("price")
    if not value or not ref or not reference.get("comparable") or PRICE_CHECK_LOW < value / ref < PRICE_CHECK_HIGH:
        return None
    rel = value / ref
    side, times = ("thấp", round(1 / rel)) if rel < 1 else ("cao", round(rel))
    return {"type": "warning", "field": "price", "current_value": value, "target": ref, "impact": 0,
            "message": (f"Giá {_vnd(value)} {side} hơn khoảng {times} lần so với mức tham khảo {_vnd(ref)}. "
                        "Kiểm tra lại xem có gõ thiếu hoặc thừa số 0 không.")}


def _message(row: Dict[str, Any]) -> str:
    key, value, target = row["key"], row["value"], row["target"]
    if key == "image":
        return f"Thêm {int(target - value)} ảnh (đang có {value}/{int(target)})"
    if key == "description":
        return f"Viết thêm {int(target - value)} từ ({value}/{int(target)})"
    if key == "tags":
        return tag_message(value, row["pending"], int(target))
    if key == "material":
        return "Ghi rõ chất liệu (ví dụ: cotton, len, gốm…) vào ô Chất liệu"
    if key == "review":
        if not value:
            return "Chưa có đánh giá nào, mời khách đã mua để lại đánh giá"
        return f"Tỉ lệ đánh giá tốt {round(row['n_good'] / value * 100)}%, tiếp tục chăm sóc khách để giữ đánh giá tốt"
    if not value:
        return "Chưa có giá bán cho biến thể nào" + _popular(row)
    ref = row["reference"]
    if value < ref["price"]:
        pct = round((1 - value / ref["price"]) * 100)
        return f"Giá thấp hơn {pct}% so với {_peers(ref)}, kiểm tra lại chi phí để không bán lỗ" + _popular(row)
    pct = round((value / ref["price"] - 1) * 100)
    return f"Giá cao hơn {pct}% so với {_peers(ref)} (mức giữa {_vnd(ref['price'])})" + _popular(row)


def _fixed_points(row: Dict[str, Any]) -> float:
    if row.get("key") == "review" and row.get("p0") is not None and row.get("m") is not None:
        n, n_good, p0, m = row.get("value") or 0, row.get("n_good", 0), row["p0"], row["m"]
        return round(row["weight"] * (n_good + 1 + m * p0) / (n + 1 + m), 1)
    return float(row["weight"])


def _impact(row: Dict[str, Any], rows: List[Dict[str, Any]]) -> float:
    fixed = [{**r, "points": _fixed_points(r)} if r is row else r for r in rows]
    return round(score_of(fixed) - score_of(rows), 1)


def build_todos(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    todos = [{
        "type": "todo", "code": r["key"], "field": r["key"], "message": _message(r),
        "current_value": r["value"], "target": r["target"], "impact": _impact(r, rows),
    } for r in rows if r.get("scored", True) and r["sub_score"] < 100 and _impact(r, rows) > 0]
    todos.sort(key=lambda t: (-t["impact"], EFFORT[t["code"]]))
    return todos
