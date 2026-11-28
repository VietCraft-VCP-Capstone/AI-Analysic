"""Lead time thực tế của shop: p90 số ngày từ lúc đặt đơn tới lúc giao xong (từ `status_history`).

Dùng để tính hạn chốt đơn của dịp thay cho con số mặc định khi shop giao chậm hơn mặc định.
"""
import logging
import math
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from app.core.redis_cache import cache_get_json, cache_set_json

log = logging.getLogger("shop_lead_time")

MIN_SAMPLES = 10
BUFFER_DAYS = 2
LOOKBACK_DAYS = 120


def _delivery_days(o: Dict[str, Any]) -> Optional[float]:
    created = o.get("created_at")
    done = [h.get("changed_at") for h in (o.get("status_history") or []) if h.get("status") == "DELIVERED" and h.get("changed_at")]
    if not created or not done:
        return None
    d = (done[-1] - created).total_seconds() / 86400
    return d if d >= 0 else None


def _p90(values: List[float]) -> float:
    v = sorted(values)
    return v[max(0, math.ceil(0.9 * len(v)) - 1)]  # nearest-rank


def measure_lead_time(orders: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """p90 theo loại hàng (ready/pod); lead_days = p90 của loại chậm hơn (đủ mẫu) + BUFFER_DAYS."""
    groups: Dict[str, List[float]] = {"ready": [], "pod": []}
    for o in orders:
        d = _delivery_days(o)
        if d is not None:
            groups["pod" if o.get("is_pod") else "ready"].append(d)
    out: Dict[str, Any] = {}
    for k, vals in groups.items():
        if len(vals) >= MIN_SAMPLES:
            out[k] = {"p90_days": round(_p90(vals), 1), "n": len(vals)}
    if not out:
        return None
    basis_type = max(out, key=lambda k: out[k]["p90_days"])
    out["basis_type"] = basis_type
    out["lead_days"] = math.ceil(out[basis_type]["p90_days"]) + BUFFER_DAYS
    return out


def load_shop_lead_time(shop_id: str) -> Optional[Dict[str, Any]]:
    """Đo từ đơn đã giao của shop trong LOOKBACK_DAYS ngày (cache 6 giờ)."""
    ckey = f"seasonal:shop_lead_time:v1:{shop_id}"
    cached = cache_get_json(ckey)
    if isinstance(cached, dict):
        return cached or None
    try:
        from bson import ObjectId

        from app.api.v1._live import db_live, la_shop_live

        if not la_shop_live(shop_id):
            return None
        docs = list(
            db_live()["orders"].find(
                {
                    "shop_id": ObjectId(shop_id),
                    "order_status": "DELIVERED",
                    "is_simulated": {"$ne": True},
                    "created_at": {"$gte": datetime.utcnow() - timedelta(days=LOOKBACK_DAYS)},
                },
                {"created_at": 1, "status_history": 1, "is_pod": 1},
            ).limit(2000)
        )
    except Exception as exc:
        log.warning("shop_lead_time: %s: %s", type(exc).__name__, exc)
        return None
    res = measure_lead_time(docs)
    cache_set_json(ckey, res or {}, ttl_seconds=6 * 3600)
    return res
