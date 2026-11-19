"""
Công thức tính Điểm Cơ Hội Từ Khóa (Opportunity Score) chuẩn AI Analytic cho Module Seasonal.

Nguyên tắc thiết kế:
1. Thống nhất thước đo: Điểm cơ hội bám sát Lượt bán thật (Tiki + VietCraft), Dư địa trên mỗi shop
   (lượt bán / số shop đối thủ đã khử trùng đa nguồn), Tín hiệu quan tâm quốc tế (Etsy Open API v3
   num_favorers), và Đà tăng tìm kiếm Google Trends VN (CHỈ khi khớp chính xác `exact`).
2. Mô hình lai (Hybrid Log-Anchored + Percentile Rank):
   - Kết hợp 60% thang log neo cố định + 40% hạng phần trăm trong nhóm từ khóa của dịp (khi N >= 4),
     tránh bẫy thổi điểm khi nhóm nhỏ (N <= 10) mà vẫn so sánh công bằng giữa các dịp khác nhau.
   - Không kẹp cứng [15, 95] làm mất thông tin xếp hạng.
3. Chốt chặn chống mâu thuẫn (Guardrails):
   - Lượt bán < 50 -> trần tối đa 40đ ("ít shop vì không ai cần").
   - Đông shop (>= max(10, P75)) và bán/shop < 30 -> trần tối đa 55đ ("bão hòa").
   - Chưa có lượt bán thật (chỉ có Etsy favorers hoặc Trends exact) -> điểm sơ bộ, trần tối đa 55đ.
   - Chỉ khớp Trends một phần (partial/proxy) và không có lượt bán / Etsy -> trả None (N/A), không bịa điểm.
"""

from __future__ import annotations

from datetime import date, timedelta
import math
from typing import Any, Dict, List, Optional, Tuple


DEMAND_LOG_ANCHOR = 1000.0        # 1.000 lượt bán thật -> 100đ trên trục tuyệt đối
HEADROOM_LOG_ANCHOR = 150.0       # 150 lượt bán/shop -> 100đ trên trục dư địa
ETSY_FAV_LOG_ANCHOR = 500.0       # 500 lượt yêu thích trên Etsy -> 100đ trên trục quan tâm quốc tế
LOW_DEMAND_SOLD_THRESHOLD = 50
LOW_DEMAND_SCORE_CAP = 40
SATURATION_MIN_SHOPS = 10
SATURATION_MAX_SALES_PER_SHOP = 30.0
SATURATION_SCORE_CAP = 55
PRELIMINARY_NO_SALES_CAP = 55
TREND_MAX_STALE_DAYS = 28         # Chuỗi Trends trễ > 28 ngày so với hôm nay -> không tính đà 4 tuần ảo


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
            # Fallback khóa mềm theo (platform, title, seller_id)
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
            # Ưu tiên bản ghi có dữ liệu lượt bán/yêu thích mới hoặc đầy đủ hơn
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
    Trả về `(vals_in_window, stale_days)`:
      - `stale_days`: số ngày từ điểm quan sát mới nhất đến `as_of` (None nếu không có `as_of` hoặc không có dữ liệu).
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
    - Nếu có `trend_points` + `as_of`: lọc đúng cửa sổ `[as_of - 52 tuần, as_of]`.
    - Nếu chuỗi bị trễ quá `max_stale_days` (mặc định 28 ngày) so với `as_of`, trả `wow = None`
      để không lấy đà tăng cũ cách đây vài tháng cộng/trừ vào điểm hôm nay.
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


def _percentile_ranks(values: List[float]) -> List[float]:
    """Hạng phần trăm trung bình (midrank) trong thang [0, 100], ổn định khi có giá trị trùng nhau."""
    n = len(values)
    if n == 0:
        return []
    if n == 1:
        return [50.0]

    ranks: List[float] = []
    for v in values:
        less = sum(1 for x in values if x < v)
        equal = sum(1 for x in values if x == v)
        midrank = less + 0.5 * (equal - 1)
        ranks.append((midrank / (n - 1)) * 100.0)
    return ranks


def _percentile_value(values: List[float], p: float) -> float:
    """Tính phân vị thứ p (0..100) bằng nội suy tuyến tính."""
    if not values:
        return 0.0
    s = sorted(values)
    if len(s) == 1:
        return s[0]
    k = (p / 100.0) * (len(s) - 1)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return s[int(k)]
    return s[f] + (k - f) * (s[c] - s[f])


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
    Chấm điểm cơ hội chuẩn AI Analytic cho danh sách từ khóa ứng viên trong 1 dịp.

    Mỗi phần tử đầu vào cần có (các trường thiếu mặc định 0/None):
      - tag: str
      - sold_real: int (lượt bán thật Tiki + đơn hoàn tất VietCraft 90 ngày)
      - sold_delta_30d: Optional[int] (chênh lệch lượt bán 30 ngày đo từ snapshot nếu có)
      - sellers_real: int (số shop đối thủ duy nhất đã khử trùng)
      - etsy_favorers: int (tổng lượt yêu thích trên Etsy cho từ khóa này)
      - etsy_listings: int (số listing Etsy khớp)
      - trend_match: 'exact' | 'partial' | 'proxy' | 'none'
      - trend_vals: List[float] (chuỗi 52 tuần)
      - trend_points: Optional[List[Tuple[str, float]]] (cặp (YYYY-MM-DD, value) để lọc đúng cửa sổ ngày & độ trễ)
    """
    if not candidates:
        return []

    # Bước 1: Tính trước các đại lượng gốc cho từng từ khóa (có lọc ngày cho Trends)
    prepped: List[Dict[str, Any]] = []
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
        has_exact_trend = trend_norm is not None
        sales_per_shop = round(sold / max(1, sellers), 1) if sold > 0 else None

        prepped.append({
            "sold": sold,
            "sellers": sellers,
            "etsy_fav": etsy_fav,
            "match_kind": match_kind,
            "has_exact_trend": has_exact_trend,
            "trend_raw": trend_raw,
            "trend_norm": trend_norm,
            "wow": wow,
            "stale_days": stale_days,
            "is_trend_stale": is_trend_stale,
            "sales_per_shop": sales_per_shop,
        })

    # Bước 2: Tính hạng phần trăm trên tập từ khóa có lượt bán thật (chỉ kích hoạt khi >= 4 từ khóa có bán)
    sold_indices = [i for i, p in enumerate(prepped) if p["sold"] > 0]
    use_relative = len(sold_indices) >= 4

    demand_pct_map: Dict[int, float] = {}
    headroom_pct_map: Dict[int, float] = {}
    if use_relative:
        log_solds = [math.log1p(prepped[i]["sold"]) for i in sold_indices]
        sps_vals = [float(prepped[i]["sales_per_shop"] or 0.0) for i in sold_indices]
        d_ranks = _percentile_ranks(log_solds)
        h_ranks = _percentile_ranks(sps_vals)
        for pos, idx in enumerate(sold_indices):
            demand_pct_map[idx] = d_ranks[pos]
            headroom_pct_map[idx] = h_ranks[pos]

    all_seller_counts = [float(p["sellers"]) for p in prepped if p["sellers"] > 0]
    p75_sellers = _percentile_value(all_seller_counts, 75.0) if all_seller_counts else float(SATURATION_MIN_SHOPS)
    sat_shop_threshold = max(float(SATURATION_MIN_SHOPS), p75_sellers)

    # Bước 3: Chấm điểm + áp chốt chặn chống mâu thuẫn
    results: List[Dict[str, Any]] = []
    for idx, p in enumerate(prepped):
        sold = p["sold"]
        sellers = p["sellers"]
        etsy_fav = p["etsy_fav"]
        trend_norm = p["trend_norm"]
        wow = p["wow"]
        sps = p["sales_per_shop"]

        momentum: Optional[float] = None
        if wow is not None:
            momentum = round(max(0.0, min(100.0, 50.0 + wow * 1.5)), 1)

        etsy_signal = round(_log_score(float(etsy_fav), ETSY_FAV_LOG_ANCHOR), 1) if etsy_fav > 0 else None
        applied_caps: List[str] = []

        if sold > 0:
            d_abs = _log_score(float(sold), DEMAND_LOG_ANCHOR)
            h_abs = _log_score(float(sps or 0.0), HEADROOM_LOG_ANCHOR)

            if use_relative:
                demand_core = 0.60 * d_abs + 0.40 * demand_pct_map[idx]
                headroom_score = 0.60 * h_abs + 0.40 * headroom_pct_map[idx]
            else:
                demand_core = d_abs
                headroom_score = h_abs

            # Nếu có thêm dữ liệu quan tâm thật từ Etsy, hỗ trợ tối đa 12% vào trụ Cầu để tăng độ chính xác đa sàn
            if etsy_signal is not None:
                demand_score = 0.88 * demand_core + 0.12 * etsy_signal
            else:
                demand_score = demand_core

            demand_score = round(demand_score, 1)
            headroom_score = round(headroom_score, 1)

            if momentum is not None:
                raw_score = 0.45 * demand_score + 0.40 * headroom_score + 0.15 * momentum
                score_basis = "sales+trends"
                formula_core = f"0.45×Cầu({demand_score}) + 0.40×Dư địa({headroom_score}) + 0.15×Đà({momentum})"
            else:
                raw_score = 0.53 * demand_score + 0.47 * headroom_score
                score_basis = "sales_only"
                formula_core = f"0.53×Cầu({demand_score}) + 0.47×Dư địa({headroom_score})"

            final_f = raw_score

            # Chốt chặn 1: Cầu quá thấp (< 50 lượt bán) -> tối đa 40đ
            if sold < LOW_DEMAND_SOLD_THRESHOLD:
                if final_f > LOW_DEMAND_SCORE_CAP:
                    final_f = float(LOW_DEMAND_SCORE_CAP)
                applied_caps.append(f"Cầu thấp (< {LOW_DEMAND_SOLD_THRESHOLD} lượt bán): trần {LOW_DEMAND_SCORE_CAP}đ")

            # Chốt chặn 2: Bão hòa (đông shop >= max(10, P75) và mỗi shop bán < 30) -> tối đa 55đ
            if sellers >= sat_shop_threshold and (sps or 0.0) < SATURATION_MAX_SALES_PER_SHOP:
                if final_f > SATURATION_SCORE_CAP:
                    final_f = float(SATURATION_SCORE_CAP)
                applied_caps.append(
                    f"Cạnh tranh bão hòa ({sellers} shop, ~{sps} bán/shop): trần {SATURATION_SCORE_CAP}đ"
                )

            final_score: Optional[int] = int(round(max(0.0, min(100.0, final_f))))
            cap_note = f" | Chốt chặn: {'; '.join(applied_caps)}" if applied_caps else ""
            formula_text = f"{formula_core} → {final_score}/100{cap_note}"

        elif etsy_signal is not None or trend_norm is not None:
            # Chưa có lượt bán nội địa, nhưng có tín hiệu thật từ Etsy (num_favorers) hoặc Google Trends khớp chính xác
            low_comp_bonus = max(0.0, min(100.0, 100.0 - sellers * 5.0))
            if etsy_signal is not None and trend_norm is not None:
                demand_score = round(0.55 * etsy_signal + 0.45 * trend_norm, 1)
                score_basis = "etsy+trends"
            elif etsy_signal is not None:
                demand_score = etsy_signal
                score_basis = "etsy_engagement"
            else:
                demand_score = round(float(trend_norm), 1)
                score_basis = "trends_only"

            headroom_score = round(low_comp_bonus, 1)
            if momentum is not None:
                raw_score = 0.50 * demand_score + 0.25 * headroom_score + 0.25 * momentum
                formula_core = f"Sơ bộ: 0.50×Tín hiệu({demand_score}) + 0.25×Ít đối thủ({headroom_score}) + 0.25×Đà({momentum})"
            else:
                raw_score = 0.65 * demand_score + 0.35 * headroom_score
                formula_core = f"Sơ bộ: 0.65×Tín hiệu({demand_score}) + 0.35×Ít đối thủ({headroom_score})"

            final_f = min(float(PRELIMINARY_NO_SALES_CAP), raw_score)
            applied_caps.append(f"Chưa có lượt bán thực tế (tín hiệu sơ bộ): trần {PRELIMINARY_NO_SALES_CAP}đ")
            final_score = int(round(max(0.0, min(100.0, final_f))))
            formula_text = f"{formula_core} → {final_score}/100 (trần sơ bộ {PRELIMINARY_NO_SALES_CAP}đ)"

        else:
            # Thiếu cả lượt bán, Etsy engagement lẫn Trends khớp chính xác -> trả None (N/A), không bịa điểm
            demand_score = None
            headroom_score = None
            final_score = None
            score_basis = "insufficient"
            formula_text = "Chưa đủ dữ liệu (chưa có lượt bán, tín hiệu Etsy hoặc chuỗi Google Trends khớp chính xác)."

        results.append({
            "keyword_score": final_score,
            "score_basis": score_basis,
            "sales_per_shop": sps,
            "trend_index_raw": p["trend_raw"],
            "trend_index_norm": trend_norm,
            "search_wow_pct": wow,
            "trend_stale_days": p["stale_days"],
            "is_trend_stale": p["is_trend_stale"],
            "score_breakdown": {
                "demand": demand_score,
                "headroom": headroom_score,
                "momentum": momentum,
                "etsy_signal": etsy_signal,
                "sales_per_shop": sps,
                "applied_caps": applied_caps,
                "formula_text": formula_text,
            },
        })

    return results

