"""Tính trước phần dữ liệu thị trường dùng chung của Seasonal (theo ngành x dịp), không phụ thuộc shop.

Catalog đa sàn, crawler F42, Trends và tìm kiếm trên sàn được đọc và chấm điểm sẵn rồi nạp vào Redis,
để request của seller chỉ còn tính phần riêng của shop. Chạy sau các lượt thu dữ liệu (xem f29_scheduler).
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any, Dict, List

from app.core import calendar_vn
from app.core.category_groups import GROUP_LABELS
from app.core.seasonal_uplift import market_uplift_for_camp
from app.services.f38.f38_campaigns import build_all_campaigns
from app.services.f38.f38_keywords import tinh_opportunity_keywords
from app.services.f38.f38_market_ideas import fetch_external_market_catalog

log = logging.getLogger("f38_seasonal")

OPEN_PHASES = {"upcoming", "rd_sprint", "traction", "peak", "last_call"}
MAX_OPEN_OCCASIONS = 3


def _past_event_dates(camp: Dict[str, Any], today: date) -> List[date]:
    ev = next((e for e in calendar_vn.SHOPPING_EVENTS if e["key"] == camp["id"]), None)
    if ev is None:
        return []
    return sorted(d for d in calendar_vn.event_dates_by_year(ev, range(2021, today.year + 1)).values() if d < today)


def warm_seasonal_market_cache(today: date) -> int:
    """Trả số cặp (ngành, dịp) đã tính xong."""
    done = 0
    for cat_slug in GROUP_LABELS:
        camps, _ = build_all_campaigns(today, cat_slug, None)
        open_camps = [c for c in camps if c.get("current_phase") in OPEN_PHASES][:MAX_OPEN_OCCASIONS]
        for camp in open_camps:
            try:
                fetch_external_market_catalog(cat_slug, camp, today)
                ow = camp.get("occasion_window") or {}
                if ow.get("traction_start") and ow.get("event_date"):
                    market_uplift_for_camp(camp, date.fromisoformat(ow["traction_start"]), date.fromisoformat(ow["event_date"]), today)
                tinh_opportunity_keywords(
                    active_camp=camp,
                    cat_slug=cat_slug,
                    hom_nay=today,
                    measured_sample_size=0,
                    orders_growth_pct=0,
                    stl={},
                    shop_products=[],
                    past_event_dates=_past_event_dates(camp, today),
                )
                done += 1
            except Exception as exc:  # noqa: BLE001
                log.warning("seasonal warm %s/%s failed: %s: %s", cat_slug, camp.get("id"), type(exc).__name__, exc)
    return done
