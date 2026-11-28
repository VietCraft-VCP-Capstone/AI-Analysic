"""Độ tươi của từng nguồn dữ liệu thị trường mà Seasonal dùng, để trang ghi rõ số liệu được thu đến ngày nào."""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Dict, Mapping, Optional

log = logging.getLogger(__name__)

# Số ngày tối đa được coi là còn tươi, theo lịch thu của từng nguồn
MAX_AGE_DAYS: Dict[str, int] = {"trends": 14, "catalog": 3, "market_crawl": 3}
LABELS: Dict[str, str] = {
    "trends": "Google Trends",
    "catalog": "Catalog Tiki/Etsy/Printify",
    "market_crawl": "Crawler giá Tiki/Etsy",
}


def freshness_summary(latest: Mapping[str, Optional[datetime]], today: date) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for key, at in latest.items():
        if at is None:
            out[key] = {"as_of": None, "age_days": None, "stale": True, "label": LABELS.get(key, key)}
            continue
        d = at.date() if isinstance(at, datetime) else at
        age = (today - d).days
        out[key] = {
            "as_of": d.isoformat(),
            "age_days": age,
            "stale": age > MAX_AGE_DAYS.get(key, 7),
            "label": LABELS.get(key, key),
        }
    return out


def load_market_freshness(today: date) -> Dict[str, Dict[str, Any]]:
    """Đọc mốc mới nhất của từng nguồn (chỉ đọc)."""
    latest: Dict[str, Optional[datetime]] = {"trends": None, "catalog": None, "market_crawl": None}
    try:
        from app.core.listing_intel.trend_store import weekly_series

        weeks = [s.index.max() for s in weekly_series().values() if len(s)]
        latest["trends"] = max(weeks).to_pydatetime() if weeks else None
    except Exception as exc:  # noqa: BLE001
        log.warning("freshness: trends unavailable: %s", exc)
    try:
        from app.api.v1._mart import db

        doc = db()["external_market_products"].find_one({}, {"collected_at": 1}, sort=[("collected_at", -1)])
        latest["catalog"] = doc.get("collected_at") if doc else None
    except Exception as exc:  # noqa: BLE001
        log.warning("freshness: catalog unavailable: %s", exc)
    try:
        from app.services.f42.orchestrator import _get_data_db

        data_db = _get_data_db()
        doc = data_db["market_price_listing"].find_one({}, {"last_seen_at": 1}, sort=[("last_seen_at", -1)]) if data_db is not None else None
        latest["market_crawl"] = doc.get("last_seen_at") if doc else None
    except Exception as exc:  # noqa: BLE001
        log.warning("freshness: market crawl unavailable: %s", exc)
    return freshness_summary(latest, today)
