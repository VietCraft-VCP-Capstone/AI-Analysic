"""
Công thức tính Điểm Cơ Hội Từ Khóa (Opportunity Score) thống nhất 1 công thức duy nhất cho Module Seasonal.

Nguyên tắc thiết kế (nhất quán 100%, không chia nhánh phức tạp, không kẹp điểm hàng loạt):
1. Quy đổi mọi nguồn dữ liệu sản phẩm thật về cùng 1 đơn vị «Sức cầu» (`effective_demand`):
   - 1 lượt bán thật (Tiki + đơn hoàn tất VietCraft 90 ngày) = 1,0 đơn vị cầu
   - 10 lượt yêu thích Etsy (`num_favorers`) = 1,0 đơn vị cầu
   => `Sức cầu = Lượt bán + (Lượt thích Etsy / 10)`
   => `Cầu mỗi shop = Sức cầu / max(1, Số gian hàng đã khử trùng)`
2. Chấm mọi từ khóa có `Sức cầu > 0` bằng ĐÚNG 1 công thức duy nhất (thang 0–100):
   - **50% Sức cầu** (tối đa 50đ): thang log neo tại mốc 1.000 cầu = 100đ (50/50đ).
   - **50% Dư địa / Shop** (tối đa 50đ): thang log neo tại mốc 200 cầu/shop = 100đ (50/50đ).
   - `Điểm cơ hội = round(0.50 × Điểm_Sức_cầu + 0.50 × Điểm_Dư_địa)`
3. Thiếu dữ liệu thị trường (`Sức cầu = 0`) -> trả `None` (`N/A`), tuyệt đối không bịa điểm.
4. Google Trends VN (52 tuần đến `hom_nay`, chỉ khớp `exact` và trễ <= 28 ngày) được giữ làm thông tin
   tham khảo đà tìm kiếm 4 tuần bên cạnh, không làm xáo trộn tỷ trọng 50/50.
"""

from __future__ import annotations

from datetime import date, timedelta
import math
from typing import Any, Dict, List, Optional, Tuple


DEMAND_LOG_ANCHOR = 1000.0        # 1.000 đơn vị cầu -> 100đ trên trục Sức cầu (50/50đ tổng)
HEADROOM_LOG_ANCHOR = 200.0       # 200 đơn vị cầu/shop -> 100đ trên trục Dư địa/Shop (50/50đ tổng)
ETSY_FAVORERS_PER_UNIT = 10.0     # Quy đổi: 10 lượt thích Etsy = 1 đơn vị cầu
TREND_MAX_STALE_DAYS = 28         # Chuỗi Trends trễ > 28 ngày so với hôm nay -> không hiển thị đà 4 tuần cũ


def canonical_seller_key(
    seller_id: Optional[Any],
    seller_name: Optional[str] = None,
    platform: Optional[str] = None,
) -> Optional[str]:
    """Chuẩn hóa định danh shop xuyên nguồn để không bao giờ đếm trùng giữa Tiki, Etsy, Printify, VietCraft."""
    plat = (platform or "").strip().lower()
    sid = str(seller_id or "").strip()
    sname = (seller_name or "").strip().lower()

    if sid:
        low_sid = sid.lower()
        if low_sid.startswith("vc_"):
            return f"vc:{sid[3:]}"
        if low_sid.startswith("tiki_"):
            return f"tiki:{sid[5:]}"
        if low_sid.startswith("etsy_"):
            return f"etsy:{sid[5:]}"
        if low_sid.startswith("printify_"):
            return f"printify:{sid[9:]}"
        if plat in ("vietcraft", "vc"):
            return f"vc:{sid}"
        if plat:
            return f"{plat}:{sid}"
        return f"shop:{sid}"

    if sname:
        return f"{plat or 'ext'}:name:{sname}"
    return None


def dedupe_external_docs(
    docs: List[Dict[str, Any]],
    target_occasion_id: str = "",
) -> List[Dict[str, Any]]:
    """
    Khử trùng các bản ghi `external_market_products` theo `external_id`.
    Khi 1 sản phẩm (Tiki/Etsy/VietCraft) xuất hiện ở nhiều dịp, ưu tiên bản ghi khớp dịp đang xem
    và giữ đúng 1 bản ghi để không cộng trùng `sold_count` hoặc `listing_count`.
    """
    target_occ = (target_occasion_id or "").strip().lower()
    by_ext_id: Dict[str, Dict[str, Any]] = {}
    fallback_rows: List[Dict[str, Any]] = []

    for doc in docs:
        ext_id = str(doc.get("external_id") or "").strip()
        if not ext_id:
            soft = f"{(doc.get('platform') or '').lower()}::{(doc.get('title') or '').strip().lower()}::{doc.get('seller_id') or ''}"
            if soft == "::::":
                fallback_rows.append(doc)
                continue
            ext_id = soft

        existing = by_ext_id.get(ext_id)
        if existing is None:
            by_ext_id[ext_id] = doc
            continue

        cur_match = (str(doc.get("occasion_id") or "").strip().lower() == target_occ) and bool(target_occ)
        old_match = (str(existing.get("occasion_id") or "").strip().lower() == target_occ) and bool(target_occ)

        if cur_match and not old_match:
            by_ext_id[ext_id] = doc
        elif cur_match == old_match:
            cur_sig = int(doc.get("sold_count") or 0) + int(doc.get("num_favorers") or doc.get("review_count") or 0)
            old_sig = int(existing.get("sold_count") or 0) + int(existing.get("num_favorers") or existing.get("review_count") or 0)
            if cur_sig > old_sig:
                by_ext_id[ext_id] = doc

    return list(by_ext_id.values()) + fallback_rows


def filter_trend_points_by_date(
    trend_points: List[Tuple[str, float]],
    as_of: Optional[date] = None,
    window_weeks: int = 52,
) -> Tuple[List[float], Optional[int]]:
    """
    Lọc chuỗi Google Trends theo đúng cửa sổ ngày `[as_of - window_weeks, as_of]` (loại bỏ điểm tương lai hoặc quá hạn).
    Trả về `(vals_in_window, stale_days)`.
    """
    if not trend_points:
        return [], None

    parsed: List[Tuple[date, float]] = []
    for pt in trend_points:
        if len(pt) < 2 or pt[1] is None:
            continue
        raw_d = pt[0]
        try:
            d_obj = raw_d if isinstance(raw_d, date) else date.fromisoformat(str(raw_d)[:10])
        except ValueError:
            continue
        parsed.append((d_obj, float(pt[1])))

    if not parsed:
        return [], None

    parsed.sort(key=lambda x: x[0])
    if as_of is None:
        return [v for _, v in parsed[-window_weeks:]], None

    valid_to_as_of = [(d, v) for d, v in parsed if d <= as_of]
    if not valid_to_as_of:
        return [], None

    latest_date = valid_to_as_of[-1][0]
    stale_days = max(0, (as_of - latest_date).days)
    cutoff = as_of - timedelta(days=window_weeks * 7)
    in_window = [v for d, v in valid_to_as_of if d >= cutoff]
    if not in_window:
        in_window = [v for _, v in valid_to_as_of[-window_weeks:]]
    return in_window, stale_days


def normalize_trends_52w(
    trend_vals: List[float],
    match_kind: str,
    trend_points: Optional[List[Tuple[str, float]]] = None,
    as_of: Optional[date] = None,
    max_stale_days: int = TREND_MAX_STALE_DAYS,
) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """
    Tính (raw_mean, norm_0_100, wow_4w_vs_8w) CHỈ khi chuỗi khớp chính xác `exact`.
    Dùng làm thông tin tham khảo đà tìm kiếm, không làm thay đổi công thức 50/50.
    """
    if match_kind != "exact":
        return None, None, None

    stale_days: Optional[int] = None
    if trend_points:
        vals, stale_days = filter_trend_points_by_date(trend_points, as_of=as_of, window_weeks=52)
    else:
        vals = [float(v) for v in (trend_vals or [])[-52:] if v is not None]

    if not vals:
        return None, None, None

    raw_mean = round(sum(vals) / len(vals), 1)
    peak_52 = max(vals)
    norm_0_100 = round(min(100.0, max(0.0, (raw_mean / peak_52) * 100.0)), 1) if peak_52 > 0 else 0.0

    is_stale = stale_days is not None and stale_days > max_stale_days
    wow: Optional[float] = None
    if len(vals) >= 12 and not is_stale:
        recent_4w = sum(vals[-4:]) / 4.0
        base_8w = sum(vals[-12:-4]) / 8.0
        if base_8w > 0:
            wow = round(((recent_4w - base_8w) / max(1.0, base_8w)) * 100.0, 1)
        elif recent_4w > 0:
            wow = 100.0
        else:
            wow = 0.0

    return raw_mean, norm_0_100, wow


def _log_score(value: float, anchor: float) -> float:
    if value <= 0 or anchor <= 0:
        return 0.0
    return min(100.0, max(0.0, (math.log1p(value) / math.log1p(anchor)) * 100.0))


def score_opportunity_keywords(
    candidates: List[Dict[str, Any]],
    as_of: Optional[date] = None,
    max_trend_stale_days: int = TREND_MAX_STALE_DAYS,
) -> List[Dict[str, Any]]:
    """
    Chấm điểm cơ hội bằng ĐÚNG 1 CÔNG THỨC DUY NHẤT (50% Sức cầu + 50% Dư địa/Shop):
      - `Sức cầu` = `sold_real + etsy_favorers / 10`
      - `Cầu / shop` = `Sức cầu / max(1, sellers_real)`
      - `Điểm Sức cầu (0–100)` = `100 × min(1, ln(1 + Sức cầu) / ln(1 + 1000))`
      - `Điểm Dư địa/Shop (0–100)` = `100 × min(1, ln(1 + Cầu/shop) / ln(1 + 200))`
      - `Điểm cơ hội (0–100)` = `round(0.50 × Điểm Sức cầu + 0.50 × Điểm Dư địa/Shop)`
      - Nếu `Sức cầu == 0` -> trả `None` (`N/A`).
    """
    if not candidates:
        return []

    results: List[Dict[str, Any]] = []
    for item in candidates:
        sold = max(0, int(item.get("sold_real") or 0))
        sellers = max(0, int(item.get("sellers_real") or 0))
        etsy_fav = max(0, int(item.get("etsy_favorers") or 0))
        match_kind = str(item.get("trend_match") or "none").lower()
        raw_vals = item.get("trend_vals") or []
        raw_pts = item.get("trend_points") or []

        stale_days: Optional[int] = None
        if match_kind == "exact" and raw_pts:
            _, stale_days = filter_trend_points_by_date(raw_pts, as_of=as_of, window_weeks=52)

        trend_raw, trend_norm, wow = normalize_trends_52w(
            raw_vals,
            match_kind,
            trend_points=raw_pts if raw_pts else None,
            as_of=as_of,
            max_stale_days=max_trend_stale_days,
        )
        is_trend_stale = stale_days is not None and stale_days > max_trend_stale_days

        effective_demand = round(sold + (etsy_fav / ETSY_FAVORERS_PER_UNIT), 1)

        if effective_demand > 0:
            demand_per_shop = round(effective_demand / max(1, sellers), 1)
            demand_score = round(_log_score(effective_demand, DEMAND_LOG_ANCHOR), 1)
            headroom_score = round(_log_score(demand_per_shop, HEADROOM_LOG_ANCHOR), 1)

            demand_pts = round(0.50 * demand_score, 1)
            headroom_pts = round(0.50 * headroom_score, 1)
            final_score: Optional[int] = int(round(max(0.0, min(100.0, demand_pts + headroom_pts))))

            if sold > 0 and etsy_fav > 0:
                score_basis = "sales+etsy"
            elif sold > 0:
                score_basis = "sales_only"
            else:
                score_basis = "etsy_only"

            formula_text = (
                f"50% Sức cầu ({demand_pts}/50đ · tổng cầu {effective_demand:g}) + "
                f"50% Dư địa/Shop ({headroom_pts}/50đ · ~{demand_per_shop:g}/shop) = {final_score}/100"
            )
        else:
            demand_per_shop = None
            demand_score = None
            headroom_score = None
            demand_pts = None
            headroom_pts = None
            final_score = None
            score_basis = "insufficient"
            formula_text = "Chưa có dữ liệu lượt bán (Tiki/VietCraft) hay lượt thích Etsy nên không chấm điểm."

        results.append({
            "keyword_score": final_score,
            "score_basis": score_basis,
            "effective_demand": effective_demand,
            "sales_per_shop": demand_per_shop,
            "trend_index_raw": trend_raw,
            "trend_index_norm": trend_norm,
            "search_wow_pct": wow,
            "trend_stale_days": stale_days,
            "is_trend_stale": is_trend_stale,
            "score_breakdown": {
                "demand": demand_score,
                "demand_pts": demand_pts,
                "headroom": headroom_score,
                "headroom_pts": headroom_pts,
                "effective_demand": effective_demand,
                "sales_per_shop": demand_per_shop,
                "momentum": None,
                "applied_caps": [],
                "formula_text": formula_text,
            },
        })

    return results
