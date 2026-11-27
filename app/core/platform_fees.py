"""Phí sàn do admin cấu hình (`platform_cost_configs.policies.default_commission_rate`).

Cùng nguồn với checkout và `seasonal-math.ts` ở backend.
"""
import logging
from typing import Any, Optional

from app.core.redis_cache import cache_get_json, cache_set_json

log = logging.getLogger("platform_fees")

DEFAULT_COMMISSION_RATE = 0.10
_CACHE_KEY = "platform:commission_rate:v1"


def parse_commission_rate(cfg: Optional[Any]) -> float:
    try:
        r = float(((cfg or {}).get("policies") or {}).get("default_commission_rate"))
    except (TypeError, ValueError):
        return DEFAULT_COMMISSION_RATE
    return r if 0 < r < 1 else DEFAULT_COMMISSION_RATE


def commission_rate() -> float:
    cached = cache_get_json(_CACHE_KEY)
    if isinstance(cached, (int, float)):
        return float(cached)
    try:
        from app.api.v1._live import db_live

        cfg = db_live()["platform_cost_configs"].find_one({}, {"policies": 1}, sort=[("updated_at", -1)])
    except Exception as exc:
        log.warning("commission_rate: %s: %s", type(exc).__name__, exc)
        return DEFAULT_COMMISSION_RATE
    rate = parse_commission_rate(cfg)
    cache_set_json(_CACHE_KEY, rate, ttl_seconds=600)
    return rate


def net_margin_pct(price: float, cost: float, rate: float) -> int:
    """% lãi sau giá vốn và phí sàn (làm tròn như backend)."""
    return round((price - cost - price * rate) / max(1.0, price) * 100)
