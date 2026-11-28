"""Giá vốn dùng chung cho Seasonal: lấy số thật trước, ước tính sau cùng.

Thứ tự: giá phôi thật (Printify) / giá vốn thật của sản phẩm VietCraft
→ tỷ lệ giá vốn / giá bán đo từ dòng hàng trong đơn của shop
→ tỷ lệ đo từ đơn toàn sàn
→ một tỷ lệ ước tính duy nhất (DEFAULT_COST_RATIO).
BE đọc lại `cost_model` do AI trả về để ý tưởng AI và ý tưởng thị trường cùng một cách tính.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, Optional, Tuple

log = logging.getLogger(__name__)

DEFAULT_COST_RATIO = 0.45
MIN_SHOP_ITEMS = 5
MIN_PLATFORM_ITEMS = 30
REAL_LISTING_COST_PLATFORMS = {"printify": "giá phôi thật trên Printify", "vietcraft": "giá vốn thật của sản phẩm trên VietCraft"}


def _num(v: Any) -> float:
    try:
        return float(str(v.to_decimal()) if hasattr(v, "to_decimal") else v)
    except (TypeError, ValueError):
        return 0.0


def _ratio(items: Iterable[Dict[str, Any]]) -> Tuple[Optional[float], int]:
    cost_sum = price_sum = 0.0
    n = 0
    for it in items:
        cost, price, qty = _num(it.get("base_cost")), _num(it.get("retail_price")), _num(it.get("quantity") or 1)
        if cost <= 0 or price <= 0 or cost >= price or qty <= 0:
            continue
        cost_sum += cost * qty
        price_sum += price * qty
        n += 1
    return (round(cost_sum / price_sum, 2) if price_sum else None), n


def cost_model_from_items(items_shop: Iterable[Dict[str, Any]], items_platform: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    ratio, n = _ratio(items_shop)
    if ratio is not None and n >= MIN_SHOP_ITEMS:
        return {"ratio": ratio, "source": "shop_orders", "n_items": n}
    ratio, n = _ratio(items_platform)
    if ratio is not None and n >= MIN_PLATFORM_ITEMS:
        return {"ratio": ratio, "source": "platform_orders", "n_items": n}
    return {"ratio": DEFAULT_COST_RATIO, "source": "default", "n_items": 0}


def cost_basis_label(model: Dict[str, Any]) -> str:
    pct = round(float(model["ratio"]) * 100)
    if model["source"] == "shop_orders":
        return f"{pct}% giá bán, đo từ giá vốn {model['n_items']} dòng hàng trong đơn của shop"
    if model["source"] == "platform_orders":
        return f"{pct}% giá bán, đo từ giá vốn {model['n_items']} dòng hàng trong đơn toàn sàn"
    return f"ước tính {pct}% giá bán (chưa có giá vốn thật)"


def real_listing_cost(price: float, listing_cost: Optional[float], platform: Optional[str]) -> Optional[Tuple[int, str]]:
    """Giá vốn thật của đúng sản phẩm này (phôi Printify / sản phẩm VietCraft); None khi không có."""
    real_label = REAL_LISTING_COST_PLATFORMS.get(str(platform or "").strip().lower())
    if real_label and listing_cost and 0 < float(listing_cost) < float(price):
        return int(round(float(listing_cost), -3)), real_label
    return None


def resolve_cost(price: float, model: Dict[str, Any], listing_cost: Optional[float] = None,
                 platform: Optional[str] = None) -> Tuple[int, str]:
    """Giá vốn (VND, làm tròn nghìn) và căn cứ để hiển thị cho seller."""
    real = real_listing_cost(price, listing_cost, platform)
    if real:
        return real
    return int(round(float(price) * float(model["ratio"]), -3)), cost_basis_label(model)


def load_cost_model(shop_id: Optional[str], hom_nay: date) -> Dict[str, Any]:
    """Đọc dòng hàng có giá vốn trong 400 ngày (chỉ đọc), cache theo shop và ngày."""
    from app.core.redis_cache import cache_get_json, cache_set_json

    key = f"seasonal:cost_model:{shop_id or 'none'}:{hom_nay.isoformat()}:v1"
    cached = cache_get_json(key)
    if isinstance(cached, dict) and "ratio" in cached:
        return cached
    model = {"ratio": DEFAULT_COST_RATIO, "source": "default", "n_items": 0}
    try:
        from bson import ObjectId

        from app.api.v1._live import db_live
        from app.core.order_validity import VALID_ORDER_FILTER

        since = hom_nay - timedelta(days=400)
        base = {**VALID_ORDER_FILTER, "created_at": {"$gte": datetime(since.year, since.month, since.day)}}
        proj = {"_id": 0, "items.base_cost": 1, "items.retail_price": 1, "items.quantity": 1}
        orders = db_live()["orders"]

        def items_of(q: Dict[str, Any], limit: int):
            return [it for o in orders.find(q, proj).sort("created_at", -1).limit(limit) for it in (o.get("items") or [])]

        shop_items = items_of({**base, "shop_id": ObjectId(shop_id)}, 1500) if shop_id and ObjectId.is_valid(shop_id) else []
        platform_items = [] if len(shop_items) >= MIN_SHOP_ITEMS else items_of(base, 3000)
        model = cost_model_from_items(shop_items, platform_items)
        cache_set_json(key, model, ttl_seconds=21600)
    except Exception as exc:  # noqa: BLE001
        log.warning("cost model unavailable: %s: %s", type(exc).__name__, exc)
    return model
