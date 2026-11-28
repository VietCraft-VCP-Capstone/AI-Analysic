"""Mức tăng đơn theo mùa, đo từ dữ liệu BÁN thật (không dùng lượt tìm kiếm).

Đơn dự kiến của một dịp = mức bán ngày thường × mức tăng đo được. Nguồn mức tăng theo thứ tự:
1. đơn của chính shop ở dịp đó các năm trước,
2. đơn toàn sàn (cùng ngành) ở dịp đó các năm trước,
3. tốc độ bán thật trên Tiki (số đã bán theo từng lượt cào của crawler F42) trong kỳ dịp so với trước dịp.
Không nguồn nào đủ dữ liệu thì không nhân gì (chỉ còn mức ngày thường) và trang ghi rõ chưa đo được.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from statistics import median
from typing import Any, Dict, Iterable, List, Optional

from scipy.stats import poisson

PRE_SEASON_DAYS = 60          # nhịp nền trước mùa (đơn)
MIN_PRE_SEASON_ORDERS = 20
MARKET_BASELINE_DAYS = 28     # nhịp nền trước mùa (tốc độ bán trên Tiki)
MARKET_MIN_BASELINE_DAYS = 14
MARKET_MIN_WINDOW_DAYS = 7


def _dt(v: Any) -> Optional[datetime]:
    if isinstance(v, datetime):
        return v.replace(tzinfo=None)
    if isinstance(v, str):
        try:
            return datetime.fromisoformat(v.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            return None
    return None


def order_uplift_from_history(orders: Iterable[Dict[str, Any]], past_event_dates: List[date], window_days: int,
                              min_pre_orders: int = MIN_PRE_SEASON_ORDERS) -> Optional[Dict[str, Any]]:
    """Mỗi năm: (đơn/ngày trong kỳ dịp) / (đơn/ngày 60 ngày trước kỳ). Trả thấp/giữa/cao qua các năm."""
    times = [t for t in (_dt(o.get("created_at")) for o in orders) if t]
    ratios: List[float] = []
    for ev in past_event_dates:
        w_end = datetime.combine(ev, datetime.max.time())
        w_start = datetime.combine(ev - timedelta(days=window_days - 1), datetime.min.time())  # đủ window_days ngày, tính cả ngày lễ
        b_start = w_start - timedelta(days=PRE_SEASON_DAYS)
        n_w = sum(1 for t in times if w_start <= t <= w_end)
        n_b = sum(1 for t in times if b_start <= t < w_start)
        if n_b < min_pre_orders:
            continue
        ratios.append((n_w / window_days) / (n_b / PRE_SEASON_DAYS))
    if not ratios:
        return None
    return {"low": round(min(ratios), 2), "mid": round(median(ratios), 2), "high": round(max(ratios), 2), "n_cycles": len(ratios)}


def _sold_at(history: List[Dict[str, Any]], t: datetime) -> Optional[float]:
    pts = [(at, float(h.get("sold") or 0)) for h in history if (at := _dt(h.get("at"))) and at <= t]
    return max(pts)[1] if pts else None


def market_uplift_from_sold_history(listings: Iterable[Dict[str, Any]], window_start: date, today: date) -> Optional[Dict[str, Any]]:
    """Tổng tốc độ bán (số đã bán tăng thêm mỗi ngày) trong kỳ dịp so với 28 ngày trước kỳ, trên các listing Tiki liên quan."""
    end_of = lambda d: datetime.combine(d, datetime.max.time())  # noqa: E731 - số đã bán tính tới cuối ngày
    window_days = (today - window_start).days
    if window_days < MARKET_MIN_WINDOW_DAYS:
        return None
    base_v = win_v = 0.0
    n = 0
    for ml in listings:
        hist = ml.get("sold_history") or []
        first = min((at for h in hist if (at := _dt(h.get("at")))), default=None)
        if first is None or first.date() > window_start - timedelta(days=MARKET_MIN_BASELINE_DAYS):
            continue
        b_day = max(first.date(), window_start - timedelta(days=MARKET_BASELINE_DAYS))
        s_b0, s_ws, s_now = _sold_at(hist, end_of(b_day)), _sold_at(hist, end_of(window_start)), _sold_at(hist, end_of(today))
        if s_b0 is None or s_ws is None or s_now is None:
            continue
        base_days = max(1, (window_start - b_day).days)
        base_v += max(0.0, s_ws - s_b0) / base_days
        win_v += max(0.0, s_now - s_ws) / window_days
        n += 1
    if n == 0 or base_v <= 0:
        return None
    ratio = round(win_v / base_v, 2)
    return {"low": ratio, "mid": ratio, "high": ratio, "n_listings": n}


def expected_orders_range(rate: float, days: float, uplift: Optional[Dict[str, Any]]) -> Dict[str, float]:
    """Khoảng 80% số đơn: Poisson quanh nhịp nền × số ngày × mức tăng (p10 theo mức tăng thấp, p90 theo mức tăng cao)."""
    lo, mid, hi = (uplift["low"], uplift["mid"], uplift["high"]) if uplift else (1.0, 1.0, 1.0)
    base = max(0.0, float(rate) * float(days))
    return {
        "p10": int(poisson.ppf(0.1, base * lo)) if base * lo > 0 else 0,
        "p50": round(base * mid, 1),
        "p90": int(poisson.ppf(0.9, base * hi)) if base * hi > 0 else 0,
    }


def load_platform_order_times(hom_nay: date) -> List[Dict[str, Any]]:
    """Thời điểm các đơn hợp lệ toàn sàn (chỉ đọc), dùng đo mức tăng theo mùa các năm trước. Cache theo ngày."""
    from app.core.redis_cache import cache_get_json, cache_set_json

    key = f"seasonal:platform_order_times:{hom_nay.isoformat()}:v1"
    cached = cache_get_json(key)
    if isinstance(cached, list):
        return [{"created_at": t} for t in cached]
    try:
        from app.api.v1._live import db_live
        from app.core.order_validity import VALID_ORDER_FILTER, is_valid_demand_order

        since = datetime(hom_nay.year - 5, 1, 1)
        rows = db_live()["orders"].find(
            {**VALID_ORDER_FILTER, "created_at": {"$gte": since}},
            {"_id": 0, "created_at": 1, "order_status": 1, "payment_method": 1, "payment_status": 1, "refund_status": 1, "is_simulated": 1},
        ).limit(100000)
        times = [o["created_at"].isoformat() for o in rows if o.get("created_at") and is_valid_demand_order(o)]
        cache_set_json(key, times, ttl_seconds=21600)
        return [{"created_at": t} for t in times]
    except Exception:  # noqa: BLE001
        return []


def market_uplift_for_camp(camp: Dict[str, Any], start: date, end: date, hom_nay: date) -> Optional[Dict[str, Any]]:
    """
    Mức tăng tốc độ bán trên Tiki cho dịp: đang trong mùa thì đo kỳ hiện tại (đủ ≥ 7 ngày),
    chưa tới mùa thì đo đúng kỳ đó năm trước (cần lịch sử số đã bán ≥ 1 năm). Cache theo dịp và ngày.
    """
    from app.core.redis_cache import cache_get_json, cache_set_json
    from app.core.seasonal_keyword_pool import is_relevant, occasion_markers, occasion_terms

    key = f"seasonal:market_uplift:{camp.get('id')}:{start.isoformat()}:{hom_nay.isoformat()}:v1"
    cached = cache_get_json(key)
    if isinstance(cached, dict):
        return cached.get("uplift")
    if start <= hom_nay:
        w_start, w_today = start, min(hom_nay, end)
    else:
        w_start, w_today = start - timedelta(days=365), end - timedelta(days=365)
    uplift = None
    try:
        from app.services.f42.orchestrator import _get_data_db

        data_db = _get_data_db()
        if data_db is not None:
            terms = occasion_terms(camp.get("search_keywords") or []) | occasion_markers(str(camp.get("id")))
            docs = data_db["market_price_listing"].find(
                {"source": "tiki", "sold_history.1": {"$exists": True}},
                {"_id": 0, "keywords": 1, "title": 1, "sold_history": {"$slice": -300}},
            ).limit(8000)
            relevant = [d for d in docs if any(is_relevant(k, terms) for k in (d.get("keywords") or []))]
            uplift = market_uplift_from_sold_history(relevant, w_start, w_today)
    except Exception:  # noqa: BLE001
        uplift = None
    cache_set_json(key, {"uplift": uplift}, ttl_seconds=21600)
    return uplift
