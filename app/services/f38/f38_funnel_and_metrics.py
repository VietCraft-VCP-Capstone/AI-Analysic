import logging
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from app.api.v1._live import db_live, la_shop_live
from app.core.redis_cache import cache_get_json, cache_set_json
from app.services.f38.f38_constants import cutoff_utc_dt

log = logging.getLogger("f38_seasonal")


def tinh_motivation_retail(cat_slug: str, camp_id: str) -> Dict[str, Any]:
    """Không bịa tỷ lệ % Tự mua dùng / Mua tặng khi chưa có đủ đơn thực tế của shop."""
    return {
        "gift_purchases_pct": None,
        "self_purchases_pct": None,
        "source_type": "insufficient",
        "sample_size": 0,
        "source_description": "Chưa có đủ đơn hàng thực tế trong dịp để phân loại mục đích mua (tự dùng hay mua tặng).",
        "top_reasons": [],
    }


def tinh_campaign_funnel_va_kenh(
    active_camp: Dict[str, Any],
    cat_slug: str,
    baseline_spending: int,
    occasion_spending: int,
    orders_growth_pct: int,
    spending_growth_pct: int,
    hom_nay: date,
    base_orders: int,
    actual_camp_orders: int = 0,
    actual_views: int = 0,
    actual_cart_adds: int = 0,
) -> Dict[str, Any]:
    """
    Phễu chuyển đổi 3 tầng thật từ `product_events` (`view`, `add_to_cart`) + `orders`:
    - Không bịa ngược lượt hiển thị (`impressions = None`), không chia ngược `views` / `cart_adds` từ đơn hàng.
    - Không bịa tỷ trọng kênh `45/25/15/15%` hay tăng trưởng kênh giả lập khi chưa có đơn thực tế.
    """
    camp_id = (active_camp.get("id") or "").lower()

    multiplier = max(1.0, 1.0 + orders_growth_pct / 100.0)
    target_orders = max(1, int(round(base_orders * multiplier))) if base_orders > 0 else 0

    real_cart_rate_pct = round((actual_cart_adds / actual_views) * 100.0, 1) if actual_views > 0 else None
    real_order_rate_pct = round((actual_camp_orders / actual_cart_adds) * 100.0, 1) if actual_cart_adds > 0 else None
    real_view_to_order_pct = round((actual_camp_orders / actual_views) * 100.0, 1) if actual_views > 0 else None

    funnel = {
        "impressions": None,
        "clicks": actual_views,
        "views": actual_views,
        "ctr_pct": None,
        "ctr_vs_baseline_pct": None,
        "cart_adds": actual_cart_adds,
        "cart_rate_pct": real_cart_rate_pct,
        "orders": target_orders,
        "conversion_rate_pct": real_order_rate_pct,
        "view_to_order_pct": real_view_to_order_pct,
        "cvr_multiplier": None,
        "pv_uv_ratio": None,
        "tracking_stages": ["view", "add_to_cart", "order"],
        "actual": {
            "orders": actual_camp_orders,
            "views": actual_views,
            "clicks": actual_views,
            "cart_adds": actual_cart_adds,
            "impressions": None,
        },
        "real_ctr_pct": None,
        "real_cart_rate_pct": real_cart_rate_pct,
        "real_order_rate_pct": real_order_rate_pct,
        "real_view_to_order_pct": real_view_to_order_pct,
    }

    # Chưa có đơn thực tế: trả 0 đơn / 0đ (Node.js sẽ lấp số thật từ `orders` khi shop có đơn trong kỳ)
    channels = [
        {
            "channel_key": "organic_listing",
            "name": "Tìm kiếm & Khám phá tự nhiên (SEO sàn)",
            "share_pct": 0.0,
            "gmv_vnd": 0,
            "orders_count": 0,
            "sku_orders": 0,
            "items_sold": 0,
            "aov_vnd": 0,
            "growth_pct": None,
            "action_tip": "Tối ưu ảnh concept và gắn bộ 5 thẻ tag ngách điểm cao.",
            "source_type": "insufficient",
            "is_target_plan": True,
        },
        {
            "channel_key": "campaign_promo",
            "name": "Chiến dịch sàn & Khuyến mãi theo dịp",
            "share_pct": 0.0,
            "gmv_vnd": 0,
            "orders_count": 0,
            "sku_orders": 0,
            "items_sold": 0,
            "aov_vnd": 0,
            "growth_pct": None,
            "action_tip": "Đăng ký tham gia sự kiện mùa lễ của sàn và thiết lập mã ưu đãi dịp cao điểm.",
            "source_type": "insufficient",
            "is_target_plan": True,
        },
        {
            "channel_key": "direct_social",
            "name": "Liên kết ngoài & Mạng xã hội của shop",
            "share_pct": 0.0,
            "gmv_vnd": 0,
            "orders_count": 0,
            "sku_orders": 0,
            "items_sold": 0,
            "aov_vnd": 0,
            "growth_pct": None,
            "action_tip": "Chia sẻ link bộ sưu tập lên Facebook, TikTok, Zalo để kéo khách về gian hàng.",
            "source_type": "insufficient",
            "is_target_plan": True,
        },
        {
            "channel_key": "repeat_buyers",
            "name": "Khách quen quay lại đặt hàng theo dịp",
            "share_pct": 0.0,
            "gmv_vnd": 0,
            "orders_count": 0,
            "sku_orders": 0,
            "items_sold": 0,
            "aov_vnd": 0,
            "growth_pct": None,
            "action_tip": "Gửi tin nhắn chăm sóc và voucher tri ân khách từng mua dịp trước.",
            "source_type": "insufficient",
            "is_target_plan": True,
        },
    ]

    return {
        "campaign_funnel": funnel,
        "channel_breakdown": channels,
        "motivation_breakdown": tinh_motivation_retail(cat_slug, camp_id),
    }


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


def build_route_risks(active_camp: Dict[str, Any], target_ev_d: date, hom_nay: date) -> List[Dict[str, Any]]:
    """Đánh giá rủi ro vận chuyển theo tuyến từ đơn hàng thực tế 90 ngày gần nhất (không bịa % khi < 10 đơn)."""
    route_buckets: Dict[str, Dict[str, Any]] = {
        "Tuyến trục chính (HN ↔ TP.HCM)": {"carrier": "Giao Hàng Nhanh (GHN)", "total": 0, "delayed": 0, "cancelled": 0},
        "Tuyến Miền Trung & Tây Nguyên": {"carrier": "Viettel Post", "total": 0, "delayed": 0, "cancelled": 0},
        "Tuyến Miền Bắc & Lân cận": {"carrier": "J&T Express / SPX", "total": 0, "delayed": 0, "cancelled": 0},
    }
    route_cache_key = f"seasonal:route_buckets:{hom_nay.isoformat()}:v3"
    cached_rb = cache_get_json(route_cache_key)
    if isinstance(cached_rb, dict) and all(k in cached_rb for k in route_buckets):
        route_buckets = cached_rb
    else:
        try:
            since_90_dt = cutoff_utc_dt(hom_nay, 90)
            recent_orders = list(
                db_live()["orders"]
                .find(
                    {
                        "created_at": {"$gte": since_90_dt},
                        "is_simulated": {"$ne": True},
                        "seed_ref": {"$exists": False},
                    },
                    {
                        "_id": 0,
                        "order_status": 1,
                        "shipping_address": 1,
                        "shipping_province": 1,
                        "city": 1,
                        "province": 1,
                        "carrier": 1,
                        "created_at": 1,
                        "delivered_at": 1,
                        "expected_delivery_at": 1,
                    },
                )
                .limit(1500)
            )
            for o in recent_orders:
                addr = o.get("shipping_address") or {}
                if isinstance(addr, dict):
                    prov = (
                        addr.get("city")
                        or addr.get("province")
                        or addr.get("state")
                        or o.get("shipping_province")
                        or o.get("province")
                        or ""
                    ).lower()
                else:
                    prov = (o.get("shipping_province") or o.get("province") or str(addr)).lower()

                if any(k in prov for k in ("hồ chí minh", "hcm", "sài gòn", "bình dương", "đồng nai", "long an")):
                    b_key = "Tuyến trục chính (HN ↔ TP.HCM)"
                elif any(k in prov for k in ("đà nẵng", "huế", "quảng", "khánh hòa", "nha trang", "đắk", "lâm đồng", "nghệ an", "hà tĩnh")):
                    b_key = "Tuyến Miền Trung & Tây Nguyên"
                else:
                    b_key = "Tuyến Miền Bắc & Lân cận"

                bucket = route_buckets[b_key]
                bucket["total"] += 1
                status = (o.get("order_status") or "").upper()
                if status in ("CANCELLED", "CANCELED", "RETURNED", "FAILED"):
                    bucket["cancelled"] += 1
                delivered_at = o.get("delivered_at")
                expected_at = o.get("expected_delivery_at")
                created_at = o.get("created_at")
                if delivered_at and expected_at and delivered_at > expected_at:
                    bucket["delayed"] += 1
                elif delivered_at and created_at and hasattr(delivered_at, "__sub__") and (delivered_at - created_at).days > 4:
                    bucket["delayed"] += 1
            cache_set_json(route_cache_key, route_buckets, ttl_seconds=1800)
        except Exception as exc:
            log.warning("seasonal: %s: %s", type(exc).__name__, exc)

    is_peak_season = active_camp["id"] in ("tet", "noel", "12/12") or target_ev_d.month in (10, 11, 12, 1)
    route_notices = {
        "Tuyến trục chính (HN ↔ TP.HCM)": (
            "Trục vận chuyển chính thường tăng tải dịp cao điểm. Nên gửi hàng trước hạn chốt ít nhất 1 ngày."
            if is_peak_season
            else "Tuyến trục chính thường ổn định (giao tiêu chuẩn 3–4 ngày)."
        ),
        "Tuyến Miền Trung & Tây Nguyên": (
            "Mùa mưa bão cuối năm có thể làm chậm giao liên tỉnh miền Trung. Nên cộng thêm 2 ngày dự phòng."
            if target_ev_d.month in (10, 11, 12)
            else "Tuyến liên tỉnh miền Trung ổn định, thời gian giao tiêu chuẩn 3–4 ngày."
        ),
        "Tuyến Miền Bắc & Lân cận": "Lưu ý tải kho trung chuyển phía Bắc trong tuần cận lễ.",
    }

    route_risks: List[Dict[str, Any]] = []
    for idx_r, (r_name, bucket) in enumerate(route_buckets.items()):
        n_orders = bucket["total"]
        notice = route_notices[r_name]
        if n_orders >= 10:
            delay_pct: Optional[float] = round((bucket["delayed"] / n_orders) * 100.0, 1)
            cancel_pct: Optional[float] = round((bucket["cancelled"] / n_orders) * 100.0, 1)
            conf = "high" if n_orders >= 30 else "fair"
            conf_reason = f"Đo trực tiếp từ {n_orders} đơn hàng thực tế trên tuyến trong 90 ngày gần nhất."
            how_obtained = "Tổng hợp tỷ lệ đơn giao vượt SLA và đơn hủy trên tập đơn hàng thực tế (loại đơn mô phỏng)."
            insufficient = False
            formula_txt = f"({bucket['delayed']} trễ / {n_orders} đơn) = {delay_pct}%, ({bucket['cancelled']} hủy / {n_orders} đơn) = {cancel_pct}%."
        else:
            delay_pct = None
            cancel_pct = None
            conf = "preliminary"
            conf_reason = f"Mới ghi nhận {n_orders} đơn thực tế trên tuyến này trong 90 ngày (cần ≥ 10 đơn để tính tỷ lệ trễ/hủy)."
            how_obtained = "Chưa đủ 10 đơn thực tế trong 90 ngày nên hệ thống không hiển thị tỷ lệ % ước đoán."
            insufficient = True
            formula_txt = f"Chưa đủ mẫu để tính tỷ lệ (n = {n_orders}/10 đơn tối thiểu)."

        route_risks.append(
            {
                "route": r_name,
                "carrier": bucket["carrier"],
                "delayRatePct": delay_pct,
                "cancelRatePct": cancel_pct,
                "sampleOrders": n_orders,
                "isReferenceBenchmark": False,
                "insufficientData": insufficient,
                "criticalDayNotice": notice,
                "evidence": {
                    "id": f"ev_route_{idx_r}",
                    "definition": f"Tỷ lệ đơn hàng giao trễ SLA và tỷ lệ hủy trên {r_name}.",
                    "sources": ["Dữ liệu đơn hàng thực tế db_live.orders (90 ngày)"],
                    "howObtained": how_obtained,
                    "period": [(hom_nay - timedelta(days=90)).strftime("%Y-%m-%d"), hom_nay.strftime("%Y-%m-%d")],
                    "n": n_orders,
                    "formula": formula_txt,
                    "confidence": conf,
                    "confidenceReason": conf_reason,
                    "mayBeWrongBecause": ["Đơn vị vận chuyển thay đổi tải tuyến hoặc thời tiết cực đoan cục bộ."],
                    "updatedAt": hom_nay.strftime("%Y-%m-%d"),
                },
            }
        )
    return route_risks


def count_shop_orders_for_funnel(
    shop_id: str,
    active_camp: Dict[str, Any],
    shop_products: List[Dict[str, Any]],
    matching_shop_products: List[Dict[str, Any]],
) -> Tuple[int, int, int, int]:
    """Đếm đơn cơ sở, đơn trong kỳ, lượt xem (`view`) và thêm giỏ (`add_to_cart`) thật từ MongoDB."""
    shop_base_orders = 0
    actual_camp_orders = 0
    actual_views = 0
    actual_cart_adds = 0
    try:
        if la_shop_live(shop_id):
            from bson import ObjectId

            real_order_flt = {
                "shop_id": ObjectId(shop_id),
                "order_status": {"$in": ["DELIVERED", "COMPLETED", "PAID"]},
                "is_simulated": {"$ne": True},
                "seed_ref": {"$exists": False},
            }
            shop_base_orders = db_live()["orders"].count_documents(real_order_flt)

            launch_w = active_camp.get("launch_window") or {}
            c_start = launch_w.get("start") or launch_w.get("traction_start")
            c_end = launch_w.get("peak_date") or launch_w.get("end")
            if c_start and c_end:
                d_start = datetime.fromisoformat(c_start + "T00:00:00")
                d_end = datetime.fromisoformat(c_end + "T23:59:59")
                actual_camp_orders = db_live()["orders"].count_documents(
                    {**real_order_flt, "created_at": {"$gte": d_start, "$lte": d_end}}
                )

                prod_oids = []
                for p in shop_products:
                    pid = str(p.get("_id") or "")
                    if len(pid) == 24:
                        try:
                            prod_oids.append(ObjectId(pid))
                        except Exception:
                            pass
                if prod_oids:
                    ev_agg = db_live()["product_events"].aggregate(
                        [
                            {
                                "$match": {
                                    "product_id": {"$in": prod_oids},
                                    "created_at": {"$gte": d_start, "$lte": d_end},
                                }
                            },
                            {"$group": {"_id": "$event_type", "total": {"$sum": 1}}},
                        ]
                    )
                    for row in ev_agg:
                        if row.get("_id") == "view":
                            actual_views = int(row.get("total") or 0)
                        elif row.get("_id") == "add_to_cart":
                            actual_cart_adds = int(row.get("total") or 0)
    except Exception as exc:
        log.warning("seasonal: %s: %s", type(exc).__name__, exc)

    return shop_base_orders, actual_camp_orders, actual_views, actual_cart_adds
