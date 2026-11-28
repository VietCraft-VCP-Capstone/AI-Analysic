import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.api.v1._live import db_live, la_shop_live
from app.core.redis_cache import cache_get_json, cache_set_json
from app.services.f38.f38_constants import TZ_VN, VALID_ORDER_FILTER, cutoff_utc_dt

log = logging.getLogger("f38_seasonal")


def build_scorecard_metrics(method_meta: Dict[str, Any], hom_nay: date) -> List[Dict[str, Any]]:
    """Chấm điểm độ tin cậy mô hình dự báo từ số liệu backtest thật (không dùng số giả)."""
    emp_cov = method_meta.get("avg_coverage_raw")
    cov_val = round(float(emp_cov) * 100, 1) if emp_cov is not None else None
    imp_raw = method_meta.get("improvement_vs_naive_pct")
    imp_val = round(float(imp_raw), 1) if imp_raw is not None else None
    data_meta = method_meta.get("data") or {}
    n_series = data_meta.get("n_series")
    period_start = data_meta.get("first_week")
    period_end = data_meta.get("last_week")
    is_deep_validated = bool(method_meta.get("validated_deep_model", False))
    n_label = f"{n_series} chuỗi" if n_series is not None else "các chuỗi"

    if cov_val is None:
        cov_text = "Chưa có dữ liệu backtest conformal."
        cov_conf = "preliminary"
    elif cov_val >= 80.0:
        cov_text = f"Hiệu chuẩn Split-Conformal đạt {cov_val}% độ phủ trên {n_label} ngành TMĐT."
        cov_conf = "high"
    else:
        cov_text = f"Độ phủ thực nghiệm đạt {cov_val}% (dưới mục tiêu 80.0%) trên {n_label} ngành TMĐT."
        cov_conf = "fair" if cov_val >= 70.0 else "preliminary"

    if imp_val is None:
        imp_text = "Chưa có dữ liệu so sánh với baseline Seasonal-Naive."
        imp_conf = "preliminary"
    elif is_deep_validated:
        imp_text = f"Mô hình Deep Learning Temporal Fusion + Lunar-Attention vượt qua kiểm định trên mọi fold với mức cải thiện {imp_val}% sMAE so với baseline cùng kỳ."
        imp_conf = "high"
    else:
        imp_text = f"Mô hình Deep Learning đạt cải thiện {imp_val}% sMAE nhưng chưa qua đủ ngưỡng kiểm định từng fold. Hệ thống chuyển sang Seasonal-Naive Conformal."
        imp_conf = "fair"

    return [
        {
            "title": "Tỷ lệ số quan sát nằm trong khoảng tin cậy conformal (P10 - P90)",
            "actualRatePct": cov_val,
            "targetRatePct": 80.0,
            "comparedWithBaselineText": cov_text,
            "totalEvaluatedCases": n_series,
            "evidence": {
                "id": "ev_scorecard_coverage",
                "definition": "Độ phủ thực nghiệm (Empirical Coverage) của khoảng dự báo P10-P90 qua quy trình Split-Conformal Calibration.",
                "sources": ["Báo cáo Backtest mô hình trên dữ liệu Google Trends"],
                "howObtained": f"Rolling-origin backtest 2-fold trên {n_label} ngành hàng TMĐT Google Trends.",
                "period": [period_start, period_end] if period_start and period_end else [],
                "n": n_series,
                "formula": f"Độ phủ thực tế đạt {cov_val}%. Mục tiêu >= 80%." if cov_val is not None else "Chưa có số liệu backtest.",
                "confidence": cov_conf,
                "confidenceReason": "Hiệu chuẩn conformal phi tham số, bảo đảm khoảng tin cậy trung thực không giả định phân phối chuẩn.",
                "mayBeWrongBecause": ["Biến động thị trường hoặc xu hướng bộc phát bất ngờ có thể làm lệch độ phủ."],
                "updatedAt": hom_nay.strftime("%Y-%m-%d"),
            },
        },
        {
            "title": "Mô hình dự báo & Kiểm định vượt trội so với Baseline cùng kỳ",
            "actualRatePct": imp_val,
            "targetRatePct": 3.0,
            "comparedWithBaselineText": imp_text,
            "totalEvaluatedCases": n_series,
            "evidence": {
                "id": "ev_scorecard_vs_baseline",
                "definition": "Mức cải thiện sai số tuyệt đối chuẩn hóa (sMAE) của mô hình so với Seasonal-Naive.",
                "sources": ["Báo cáo Backtest mô hình trên dữ liệu Google Trends"],
                "howObtained": f"So sánh sMAE trên {n_label} qua 2 fold rolling-origin.",
                "period": [period_start, period_end] if period_start and period_end else [],
                "n": n_series,
                "formula": f"Cải thiện sMAE = {imp_val}% (ngưỡng kiểm định >= 3.0% và coverage >= 70% mỗi fold)."
                if imp_val is not None
                else "Chưa có số liệu.",
                "confidence": imp_conf,
                "confidenceReason": imp_text,
                "mayBeWrongBecause": ["Độ phủ trên một fold có thể dưới ngưỡng 70% khi xu hướng thay đổi đột ngột."],
                "updatedAt": hom_nay.strftime("%Y-%m-%d"),
            },
        },
    ]


ROUTE_LABELS: Dict[str, str] = {
    "north": "Giao đến miền Bắc",
    "central": "Giao đến miền Trung & Tây Nguyên",
    "south": "Giao đến miền Nam",
}
MIN_DELIVERED_FOR_RATES = 10


def region_of_province(province_id: Any) -> Optional[str]:
    """Vùng theo mã tỉnh chính thức (01 Hà Nội ... 37 Ninh Bình; 38 Thanh Hóa ... 68 Lâm Đồng; 70 Bình Phước ... 96 Cà Mau)."""
    try:
        code = int(str(province_id).strip())
    except (TypeError, ValueError):
        return None
    if 1 <= code <= 37:
        return "north"
    if 38 <= code <= 68:
        return "central"
    if 70 <= code <= 96:
        return "south"
    return None


def _nearest_rank(sorted_vals: List[float], q: float) -> Optional[float]:
    if not sorted_vals:
        return None
    import math

    return float(sorted_vals[max(0, math.ceil(q * len(sorted_vals)) - 1)])


def summarize_route_orders(orders: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Theo vùng nhận hàng: số đơn, đơn hủy, số ngày từ đặt tới giao xong (mốc DELIVERED trong status_history)."""
    out: Dict[str, Dict[str, Any]] = {k: {"total": 0, "cancelled": 0, "days": []} for k in (*ROUTE_LABELS, "unknown")}
    for o in orders:
        region = region_of_province((o.get("shipping_address") or {}).get("province_id")) or "unknown"
        b = out[region]
        b["total"] += 1
        if (o.get("order_status") or "").upper() == "CANCELLED":
            b["cancelled"] += 1
        done = [h.get("changed_at") for h in (o.get("status_history") or []) if h.get("status") == "DELIVERED" and h.get("changed_at")]
        created = o.get("created_at")
        if done and created:
            b["days"].append(round((min(done) - created).total_seconds() / 86400.0, 1))
    for b in out.values():
        days = sorted(b.pop("days"))
        b["delivered"] = len(days)
        b["days_p50"] = _nearest_rank(days, 0.5)
        b["days_p90"] = _nearest_rank(days, 0.9)
    return out


def build_route_risks(active_camp: Dict[str, Any], target_ev_d: date, hom_nay: date) -> List[Dict[str, Any]]:
    """Thời gian giao và tỷ lệ hủy theo vùng nhận hàng, đo từ đơn thật 90 ngày (không hiện số khi < 10 đơn đã giao)."""
    route_cache_key = f"seasonal:route_summary:{hom_nay.isoformat()}:v4"
    summary = cache_get_json(route_cache_key)
    if not isinstance(summary, dict) or not all(k in summary for k in ROUTE_LABELS):
        summary = summarize_route_orders([])
        try:
            recent_orders = list(
                db_live()["orders"].find(
                    {"created_at": {"$gte": cutoff_utc_dt(hom_nay, 90)}, "is_simulated": {"$ne": True}, "seed_ref": {"$exists": False}},
                    {"_id": 0, "order_status": 1, "shipping_address.province_id": 1, "created_at": 1, "status_history": 1},
                ).limit(5000)
            )
            summary = summarize_route_orders(recent_orders)
            cache_set_json(route_cache_key, summary, ttl_seconds=1800)
        except Exception as exc:  # noqa: BLE001
            log.warning("seasonal: %s: %s", type(exc).__name__, exc)

    central_storm = target_ev_d.month in (9, 10, 11, 12)
    route_risks: List[Dict[str, Any]] = []
    for idx_r, (key, label) in enumerate(ROUTE_LABELS.items()):
        b = summary[key]
        n_orders, n_done = int(b["total"]), int(b["delivered"])
        enough = n_done >= MIN_DELIVERED_FOR_RATES
        cancel_pct = round(100.0 * b["cancelled"] / n_orders, 1) if enough and n_orders else None
        p50, p90 = (b["days_p50"], b["days_p90"]) if enough else (None, None)
        if enough:
            notice = f"Đơn giao xong trung vị {p50:g} ngày, 90% đơn trong {p90:g} ngày kể từ lúc đặt."
            if key == "central" and central_storm:
                notice += " Mùa mưa bão cuối năm có thể làm chậm tuyến này, nên gửi sớm hơn hạn chốt."
            formula_txt = f"Trên {n_done} đơn đã giao: trung vị {p50:g} ngày, p90 {p90:g} ngày; hủy {b['cancelled']}/{n_orders} đơn = {cancel_pct}%."
            conf = "high" if n_done >= 30 else "fair"
            conf_reason = f"Đo trực tiếp từ {n_done} đơn đã giao đến vùng này trong 90 ngày gần nhất."
        else:
            notice = f"Mới có {n_done} đơn đã giao đến vùng này trong 90 ngày, cần ít nhất {MIN_DELIVERED_FOR_RATES} đơn để đo thời gian giao."
            formula_txt = f"Chưa đủ mẫu (n = {n_done}/{MIN_DELIVERED_FOR_RATES} đơn đã giao)."
            conf = "preliminary"
            conf_reason = notice
        route_risks.append(
            {
                "route": label,
                "carrier": "",
                "delayRatePct": None,
                "cancelRatePct": cancel_pct,
                "deliveryDaysP50": p50,
                "deliveryDaysP90": p90,
                "sampleOrders": n_done,
                "isReferenceBenchmark": False,
                "insufficientData": not enough,
                "criticalDayNotice": notice,
                "evidence": {
                    "id": f"ev_route_{idx_r}",
                    "definition": f"Số ngày từ lúc đặt tới lúc giao xong và tỷ lệ đơn hủy, {label.lower()}.",
                    "sources": ["Đơn hàng thực tế 90 ngày (mốc DELIVERED trong lịch sử trạng thái, mã tỉnh nhận hàng)"],
                    "howObtained": "Chia đơn theo vùng của mã tỉnh nhận hàng; đo ngày đặt → ngày giao xong của đơn đã giao. Đơn chưa ghi hãng vận chuyển nên không tách theo hãng.",
                    "period": [(hom_nay - timedelta(days=90)).strftime("%Y-%m-%d"), hom_nay.strftime("%Y-%m-%d")],
                    "n": n_done,
                    "formula": formula_txt,
                    "confidence": conf,
                    "confidenceReason": conf_reason,
                    "mayBeWrongBecause": ["Đơn chưa ghi hãng vận chuyển nên không biết hãng nào chậm.", "Tải tuyến tuần cận lễ có thể khác 90 ngày trước."],
                    "updatedAt": hom_nay.strftime("%Y-%m-%d"),
                },
            }
        )
    return route_risks
