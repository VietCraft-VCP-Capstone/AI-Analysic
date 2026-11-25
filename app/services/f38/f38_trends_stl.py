import logging
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from app.api.v1._live import db_live, la_shop_live
from app.core.listing_intel.trend_store import weekly_series
from app.core.redis_cache import cache_get_json, cache_set_json
from app.core.seasonal_intel import real_stl
from app.services.f38.f38_constants import TZ_VN, VC_ORDER_WINDOW_DAYS, cutoff_utc_dt

log = logging.getLogger("f38_seasonal")


def tra_cuu_trend(kw: str):
    """Tra chuỗi Trends cho từ khóa. Trả (series, khóa khớp, mức khớp).

    mức khớp: exact | partial (trùng từ) | proxy (dùng 'quà tặng' thay thế) | none.
    Người dùng phải được biết khi con số dựa trên chuỗi thay thế.
    """
    all_series = weekly_series()
    low = (kw or "").lower().strip()
    if kw in all_series:
        return all_series[kw], kw, "exact"
    for k, s in all_series.items():
        if k.lower() == low:
            return s, k, "exact"
    for k, s in all_series.items():
        if low and (low in k.lower() or k.lower() in low):
            return s, k, "partial"
    toks = set(low.split())
    best = None
    for k, s in all_series.items():
        ov = len(toks & set(k.lower().split()))
        if ov > 0 and (best is None or ov > best[0]):
            best = (ov, k, s)
    if best:
        return best[2], best[1], "partial"
    if "quà tặng" in all_series:
        return all_series["quà tặng"], "quà tặng", "proxy"
    return None, None, "none"


def lay_chuoi_trend_cho_tu_khoa(kw: str) -> List[tuple]:
    """Lấy chuỗi tuần Google Trends thật (2021-2026) cho từ khóa."""
    s, _, _ = tra_cuu_trend(kw)
    if s is None:
        return []
    return [(d.strftime("%Y-%m-%d"), float(v)) for d, v in s.items()]


def lay_don_hang_lich_su(shop_id: str, include_industry: bool = True):
    """Đơn hoàn tất của shop và toàn sàn (4 năm) để so sánh hành vi mua."""
    proj = {
        "_id": 0,
        "shop_id": 1,
        "created_at": 1,
        "order_status": 1,
        "items": 1,
        "coupon_code": 1,
        "financial_breakdown": 1,
    }
    since = datetime.now() - timedelta(days=365 * 4)
    flt = {
        "created_at": {"$gte": since},
        "order_status": {"$in": ["DELIVERED", "COMPLETED", "PAID"]},
        "is_simulated": {"$ne": True},
        "seed_ref": {"$exists": False},
    }
    shop_o: List[Dict[str, Any]] = []
    ind_o: List[Dict[str, Any]] = []
    try:
        col = db_live()["orders"]
        if include_industry:
            ind_o = list(col.find(flt, proj))
        if la_shop_live(shop_id):
            from bson import ObjectId

            shop_o = list(col.find({**flt, "shop_id": ObjectId(shop_id)}, proj))
    except Exception as exc:
        log.warning("seasonal: %s: %s", type(exc).__name__, exc)
    return shop_o, ind_o


def load_vietcraft_real_sold_map(
    window_days: int = VC_ORDER_WINDOW_DAYS,
    as_of: Optional[date] = None,
) -> Dict[str, int]:
    """Đếm lượt bán thật theo product_id từ `db_live()['orders']` trong `window_days` ngày gần nhất.

    Chỉ tính đơn hoàn tất (`DELIVERED`, `COMPLETED`, `PAID`) và loại trừ đơn mô phỏng (`is_simulated=True`).
    """
    ref_day = as_of or datetime.now(TZ_VN).date()
    ckey = f"seasonal:vc_real_sold:{window_days}d:{ref_day.isoformat()}:v1"
    cached = cache_get_json(ckey)
    if isinstance(cached, dict):
        return {str(k): int(v) for k, v in cached.items()}

    sold_map: Dict[str, int] = {}
    since_dt = cutoff_utc_dt(ref_day, window_days)
    try:
        pipeline = [
            {
                "$match": {
                    "created_at": {"$gte": since_dt},
                    "order_status": {"$in": ["DELIVERED", "COMPLETED", "PAID"]},
                    "is_simulated": {"$ne": True},
                    "seed_ref": {"$exists": False},
                }
            },
            {"$unwind": "$items"},
            {
                "$group": {
                    "_id": {"$toString": "$items.product_id"},
                    "qty": {"$sum": {"$ifNull": ["$items.quantity", 1]}},
                }
            },
        ]
        for row in db_live()["orders"].aggregate(pipeline):
            pid = str(row.get("_id") or "").strip()
            qty = int(row.get("qty") or 0)
            if pid and qty > 0:
                sold_map[pid] = qty
        cache_set_json(ckey, sold_map, ttl_seconds=1800)
    except Exception as exc:
        log.warning("seasonal: vc_real_sold aggregation failed: %s: %s", type(exc).__name__, exc)
    return sold_map


def tinh_stl_don_gian(series_points: List[tuple], chu_ky: int = 52) -> Dict[str, Any]:
    """Phân rã đơn giản (dự phòng khi chuỗi ngắn hơn 2 chu kỳ, KHÔNG phải STL)."""
    if len(series_points) < chu_ky:
        vals = [p[1] for p in series_points] if series_points else [50.0] * chu_ky
        return {
            "trend": vals[-52:],
            "seasonal": [0.0] * min(52, len(vals)),
            "residual": [0.0] * min(52, len(vals)),
            "window": "52 tuần gần nhất",
            "method": "insufficient",
            "seasonal_strength": None,
        }

    recent = series_points[-chu_ky:]
    y = [p[1] for p in recent]

    trend = []
    for i in range(len(y)):
        sub = y[max(0, i - 2) : min(len(y), i + 3)]
        trend.append(round(sum(sub) / len(sub), 2))

    seasonal = []
    if len(series_points) >= chu_ky * 2:
        last_year = [p[1] for p in series_points[-chu_ky * 2 : -chu_ky]]
        for i in range(chu_ky):
            diff = (y[i] - trend[i] + last_year[i] - (sum(last_year) / len(last_year))) / 2.0
            seasonal.append(round(diff, 2))
    else:
        for i in range(chu_ky):
            seasonal.append(round(y[i] - trend[i], 2))

    residual = [round(y[i] - trend[i] - seasonal[i], 2) for i in range(chu_ky)]

    return {
        "trend": trend,
        "seasonal": seasonal,
        "residual": residual,
        "window": "52 tuần gần nhất",
    }


def tinh_stl_that(series_points: List[tuple], chu_ky: int = 52) -> Dict[str, Any]:
    """Phân rã STL robust (statsmodels) trên toàn chuỗi; chỉ khi < 2 chu kỳ mới dùng làm mượt đơn giản."""
    if len(series_points) >= chu_ky * 2:
        try:
            res = real_stl(series_points, chu_ky)
            if res.get("trend"):
                return res
        except Exception as exc:
            log.warning("seasonal: %s: %s", type(exc).__name__, exc)
    return tinh_stl_don_gian(series_points, chu_ky)

