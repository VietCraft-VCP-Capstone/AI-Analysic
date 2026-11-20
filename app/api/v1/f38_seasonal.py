import logging
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from fastapi import APIRouter

from app.api.v1._live import db_live, la_shop_live, san_pham_live
from app.api.v1._mart import db
from app.api.v1._template import CurrentShop, build_meta, ok
from app.core import calendar_vn
from app.core.redis_cache import cache_get_json, cache_set_json
from app.core.seasonal_intel import keyword_shop_coverage, summarize_industry_orders
from app.services.f38.f38_campaigns import (
    attach_expected_orders,
    build_all_campaigns,
    build_milestone_actions,
    tao_khuyen_nghi_hanh_dong as _tao_khuyen_nghi_hanh_dong,
)
from app.services.f38.f38_constants import (
    CATEGORY_OCCASION_BLUEPRINTS,
    CAT_LABELS,
    CAT_OCCASION_KEYWORDS,
    EXTERNAL_FRESHNESS_DAYS,
    LUI_SAN_XUAT,
    MART,
    TZ_VN,
    VC_ORDER_WINDOW_DAYS,
    cutoff_utc_dt as _cutoff_utc_dt,
)
from app.services.f38.f38_funnel_and_metrics import (
    build_route_risks,
    build_scorecard_metrics as _build_scorecard_metrics,
    count_shop_orders_for_funnel,
    tinh_campaign_funnel_va_kenh as _tinh_campaign_funnel_va_kenh,
    tinh_motivation_retail as _tinh_motivation_retail,
)
from app.services.f38.f38_keywords import tinh_opportunity_keywords as _tinh_opportunity_keywords
from app.services.f38.f38_market_ideas import (
    build_market_blueprints,
    build_potential_profiles,
    build_ready_and_pod_ideas,
    fetch_external_market_catalog,
)
from app.services.f38.f38_readiness import (
    analyze_product_seasonal_readiness,
    load_and_audit_shop_products,
)
from app.services.f38.f38_story_blueprint import build_idea_draft_blueprint, build_story_and_playbooks
from app.services.f38.f38_traits_and_scale import (
    ap_dung_so_sanh as _ap_dung_so_sanh,
    build_occasion_traits,
    fmt_trait as _fmt_trait,
    loi_khuyen_trait as _loi_khuyen_trait,
)
from app.services.f38.f38_trends_stl import (
    lay_chuoi_trend_cho_tu_khoa as _lay_chuoi_trend_cho_tu_khoa,
    lay_don_hang_lich_su as _lay_don_hang_lich_su,
    load_vietcraft_real_sold_map as _load_vietcraft_real_sold_map,
    tinh_stl_don_gian as _tinh_stl_don_gian,
    tinh_stl_that as _tinh_stl_that,
    tra_cuu_trend as _tra_cuu_trend,
)

router = APIRouter()
log = logging.getLogger("f38_seasonal")


def _detect_shop_category(shop_id: str, explicit_slug: Optional[str]) -> str:
    """Suy đoán ngành hàng từ sản phẩm của shop bằng word-boundary regex; mặc định 'tong-hop' nếu không rõ."""
    if explicit_slug and explicit_slug != "tong-hop":
        return explicit_slug
    if not la_shop_live(shop_id):
        return explicit_slug or "tong-hop"
    live_prods_cat = san_pham_live(shop_id) or []
    if not live_prods_cat:
        return explicit_slug or "tong-hop"
    cat_text = " ".join(
        f"{p.get('title', '')} {' '.join(p.get('categories') or [])} {' '.join(p.get('tags') or [])}".lower()
        for p in live_prods_cat
    )
    cat_rules = [
        ("phu-kien", ("phụ kiện", "túi xách", "ví", "thắt lưng", "kính mát", "mắt kính", "nón", "mũ", "trang sức", "khăn")),
        ("nha-cua", ("gia dụng", "nhà cửa", "bếp", "cốc", "ly sứ", "ly thủy tinh", "bình giữ nhiệt", "móc treo", "đèn")),
        ("thu-cong-qua-tang", ("trang trí", "decor", "tranh", "khung ảnh", "tượng", "nến", "hoa giả", "quà tặng", "thủ công")),
        ("thoi-trang", ("thời trang", "áo", "váy", "đầm", "quần", "hoodie", "khoác", "set đồ")),
    ]
    best_cat, best_hits = "tong-hop", 0
    for c_slug, c_words in cat_rules:
        hits = sum(len(re.findall(rf"(?<!\w){re.escape(w)}(?!\w)", cat_text)) for w in c_words)
        if hits > best_hits:
            best_cat, best_hits = c_slug, hits
    return best_cat


def _compute_platform_order_rates(shop_id: str, cat_slug: Optional[str], camp_id: str) -> Dict[str, Any]:
    """Đo tỷ lệ mua combo và dùng voucher từ đơn hàng hoàn tất thật (không nhân hệ số giả lập)."""
    cache_key = f"seasonal:orders_rates:{shop_id}:{cat_slug or 'all'}:{camp_id}:v2"
    cached = cache_get_json(cache_key)
    if isinstance(cached, dict):
        return cached

    query: Dict[str, Any] = {
        "order_status": {"$in": ["DELIVERED", "COMPLETED", "PAID"]},
        "is_simulated": {"$ne": True},
        "seed_ref": {"$exists": False},
    }
    if la_shop_live(shop_id):
        query["shop_id"] = shop_id
    try:
        live_orders = list(
            db_live()["orders"]
            .find(query, {"items": 1, "coupon_code": 1, "discount_amount": 1})
            .sort("created_at", -1)
            .limit(500)
        )
    except Exception as exc:
        log.warning("orders query failed for seasonal rates: %s", exc)
        return {"raw_combo_rate": None, "raw_voucher_rate": None, "sample_n": 0}

    n = len(live_orders)
    if n < 10:
        return {"raw_combo_rate": None, "raw_voucher_rate": None, "sample_n": n}

    orders_with_multi_items = sum(1 for o in live_orders if len(o.get("items") or []) >= 2)
    orders_with_voucher = sum(
        1 for o in live_orders if o.get("coupon_code") or float(o.get("discount_amount") or 0) > 0
    )
    rates = {
        "raw_combo_rate": round((orders_with_multi_items / n) * 100.0, 1),
        "raw_voucher_rate": round((orders_with_voucher / n) * 100.0, 1),
        "sample_n": n,
    }
    cache_set_json(cache_key, rates, ttl_seconds=1800)
    return rates


@router.get("/api/analytics/forecast/seasonal", tags=["F38 · Kế hoạch cao điểm & Lịch ra hàng"])
def seasonal(
    shop_id: str = CurrentShop,
    categoryId: Optional[str] = None,
    category_slug: Optional[str] = None,
    campaign_id: Optional[str] = None,
    campaignId: Optional[str] = None,
    keyword: Optional[str] = None,
):
    # 1. Xác định ngày hiện tại (giờ VN), ngành hàng shop và danh sách đối thủ tham chiếu
    hom_nay = datetime.now(TZ_VN).date()
    cat_slug = _detect_shop_category(shop_id, category_slug or categoryId)
    target_camp_id = campaign_id or campaignId

    all_competitors = cache_get_json("seasonal:all_competitors:v1")
    if not isinstance(all_competitors, list):
        all_competitors = list(
            db()["mart_competitor"].find({}, {"_id": 0, "shop_name": 1, "price_vnd": 1, "category_id": 1}).limit(100)
        )
        cache_set_json("seasonal:all_competitors:v1", all_competitors, ttl_seconds=1800)

    # 2. Lịch toàn bộ dịp mua sắm trong năm & chọn chiến dịch đang xem
    all_campaigns, active_camp = build_all_campaigns(hom_nay, cat_slug, target_camp_id)
    primary_kw = active_camp["search_keywords"][0] if active_camp["search_keywords"] else "quà tặng"
    trend_series = _lay_chuoi_trend_cho_tu_khoa(primary_kw)
    stl = _tinh_stl_that(trend_series, chu_ky=52)

    ev_info = next(e for e in calendar_vn.SHOPPING_EVENTS if e["key"] == active_camp["id"])
    ev_win = calendar_vn.calculate_occasion_window(ev_info, hom_nay) or {
        "event_date": hom_nay.isoformat(),
        "cut_off_date": (hom_nay + timedelta(days=21)).isoformat(),
    }
    target_ev_d = date.fromisoformat(ev_win["event_date"])
    cut_off_d = date.fromisoformat(ev_win["cut_off_date"])

    event_dates_by_year: Dict[int, date] = {}
    for yr in range(2021, hom_nay.year + 2):
        tw = calendar_vn.calculate_occasion_window(ev_info, date(yr, 6, 1))
        if tw and tw.get("event_date"):
            event_dates_by_year[yr] = date.fromisoformat(tw["event_date"])
    past_ev = {y: d for y, d in event_dates_by_year.items() if d < hom_nay}

    # 3. Đơn hàng lịch sử của shop & tổng hợp đơn toàn sàn (cache Redis 30 phút)
    lw_tmp = active_camp.get("launch_window") or {}
    ind_win_days = (
        max(7, (date.fromisoformat(lw_tmp["peak_date"]) - date.fromisoformat(lw_tmp["start"])).days)
        if (lw_tmp.get("peak_date") and lw_tmp.get("start"))
        else 30
    )
    ind_sum_key = f"seasonal:ind_summary:v1:{active_camp['id']}:{ind_win_days}:{hom_nay.isoformat()}"
    ind_summary = cache_get_json(ind_sum_key)
    if isinstance(ind_summary, dict) and "ind" in ind_summary and "shop_vals" in ind_summary:
        shop_orders_hist, industry_orders_hist = _lay_don_hang_lich_su(shop_id, include_industry=False)
    else:
        shop_orders_hist, industry_orders_hist = _lay_don_hang_lich_su(shop_id, include_industry=True)
        ind_summary = summarize_industry_orders(industry_orders_hist, past_ev, ind_win_days, hom_nay)
        cache_set_json(ind_sum_key, ind_summary, ttl_seconds=1800)

    measured_sample_size = int((ind_summary.get("ind") or {}).get("n_orders") or len(industry_orders_hist))
    measured_cycles = len(past_ev)

    # 4. Sản phẩm thị trường đa sàn & Hồ sơ Tiềm năng 5 lớp
    raw_ext_ready, raw_ext_pod = fetch_external_market_catalog(cat_slug, active_camp, hom_nay)
    real_blueprints = build_market_blueprints(raw_ext_ready, cat_slug, active_camp, primary_kw)
    potential_profiles = build_potential_profiles(
        real_blueprints, raw_ext_ready, event_dates_by_year, target_ev_d, cut_off_d, hom_nay
    )

    # 5. 6 Trục Đặc Điểm Mua Sắm, Radar biểu đồ & Độ lớn toàn ngành đa sàn
    traits_bundle = build_occasion_traits(
        shop_id=shop_id,
        cat_slug=cat_slug,
        active_camp=active_camp,
        ev_info=ev_info,
        target_ev_d=target_ev_d,
        hom_nay=hom_nay,
        primary_kw=primary_kw,
        stl=stl,
        all_competitors=all_competitors,
        shop_orders_hist=shop_orders_hist,
        ind_summary=ind_summary,
        past_ev=past_ev,
        ind_win_days=ind_win_days,
        compute_rates_fn=_compute_platform_order_rates,
    )
    occasion_traits = traits_bundle["occasion_traits"]
    traits_cmp = traits_bundle["traits_cmp"]
    ind_scale = traits_bundle["ind_scale"]
    method_meta = traits_bundle["method_meta"]
    uplift_res = traits_bundle["uplift_res"]
    orders_growth_pct = traits_bundle["orders_growth_pct"]
    spending_growth_pct = traits_bundle["spending_growth_pct"]
    baseline_spending = traits_bundle["baseline_spending"]
    occasion_spending = traits_bundle["occasion_spending"]
    lead_time_days = traits_bundle["lead_time_days"]
    early_order_days = traits_bundle["early_order_days"]
    peak_clump_pct = traits_bundle["peak_clump_pct"]
    ind_combo_blend = traits_bundle["ind_combo_blend"]
    ind_voucher_blend = traits_bundle["ind_voucher_blend"]
    campaign_radar = traits_bundle["campaign_radar"]

    active_camp["occasion_traits"] = occasion_traits
    active_camp["radar"] = campaign_radar
    active_camp["milestone_actions"] = build_milestone_actions(active_camp, cat_slug)

    # 6. Ý tưởng hàng sẵn, phôi POD & cụm sản phẩm cơ hội
    ready_ideas, pod_blanks, opportunity_clusters = build_ready_and_pod_ideas(
        real_blueprints, raw_ext_pod, potential_profiles, traits_cmp, active_camp, hom_nay
    )

    events_payload: List[Dict[str, Any]] = []
    for kw in active_camp["search_keywords"][:5]:
        kw_pts = _lay_chuoi_trend_cho_tu_khoa(kw)
        recent_vals = [p[1] for p in kw_pts[-8:]] if kw_pts else [40.0]
        events_payload.append(
            {
                "name": kw,
                "peak_week_of_year": target_ev_d.isocalendar()[1],
                "amplitude": round((sum(recent_vals) / len(recent_vals)) / 100.0, 2),
                "launch_window": active_camp["launch_window"],
                "ready_to_ship_ideas": ready_ideas,
                "pod_blanks": pod_blanks,
            }
        )

    # 7. Sản phẩm thật của shop & độ sẵn sàng đón dịp
    shop_products, matching_shop_products = load_and_audit_shop_products(shop_id, active_camp, spending_growth_pct)
    for idea in ready_ideas:
        idea["shop_coverage"] = keyword_shop_coverage(idea.get("keyword") or idea["title"], shop_products)

    # 8. Dự kiến đơn từng dịp, kế hoạch áp dụng, báo cáo thành quả & câu chuyện 4 chương
    attach_expected_orders(all_campaigns, shop_orders_hist, hom_nay)
    impact, apply_playbooks, story = build_story_and_playbooks(
        active_camp=active_camp,
        cat_slug=cat_slug,
        ready_ideas=ready_ideas,
        potential_profiles=potential_profiles,
        occasion_traits=occasion_traits,
        shop_orders_hist=shop_orders_hist,
        event_dates_by_year=event_dates_by_year,
        target_ev_d=target_ev_d,
        cut_off_d=cut_off_d,
        lead_time_days=lead_time_days,
        hom_nay=hom_nay,
        uplift_res=uplift_res,
    )

    # 9. Rủi ro vận chuyển tuyến, độ tin cậy mô hình, Từ khóa hot & Phễu chuyển đổi
    route_risks = build_route_risks(active_camp, target_ev_d, hom_nay)
    scorecard_metrics = _build_scorecard_metrics(method_meta, hom_nay)
    opportunity_keywords = _tinh_opportunity_keywords(
        active_camp=active_camp,
        cat_slug=cat_slug,
        hom_nay=hom_nay,
        measured_sample_size=measured_sample_size,
        orders_growth_pct=orders_growth_pct,
        stl=stl,
        shop_products=shop_products,
    )
    shop_base_orders, actual_camp_orders, actual_views, actual_cart_adds = count_shop_orders_for_funnel(
        shop_id, active_camp, shop_products, matching_shop_products
    )
    funnel_data = _tinh_campaign_funnel_va_kenh(
        active_camp=active_camp,
        cat_slug=cat_slug,
        baseline_spending=baseline_spending,
        occasion_spending=occasion_spending,
        orders_growth_pct=orders_growth_pct,
        spending_growth_pct=spending_growth_pct,
        hom_nay=hom_nay,
        base_orders=shop_base_orders,
        actual_camp_orders=actual_camp_orders,
        actual_views=actual_views,
        actual_cart_adds=actual_cart_adds,
    )

    # 10. Bản phác thảo định lượng (Data-Grounded Blueprint) để scope chặt cho LLM
    idea_draft_blueprint = build_idea_draft_blueprint(
        cat_slug=cat_slug,
        active_camp=active_camp,
        shop_products=shop_products,
        shop_orders_hist=shop_orders_hist,
        raw_ext_ready=raw_ext_ready,
        real_blueprints=real_blueprints,
        ind_scale=ind_scale,
        method_meta=method_meta,
        uplift_res=uplift_res,
        orders_growth_pct=orders_growth_pct,
        spending_growth_pct=spending_growth_pct,
        early_order_days=early_order_days,
        peak_clump_pct=peak_clump_pct,
        ind_combo_blend=ind_combo_blend,
        ind_voucher_blend=ind_voucher_blend,
        opportunity_keywords=opportunity_keywords,
    )

    meta = build_meta(
        scope="platform",
        scope_id=active_camp["id"],
        collection=MART,
        mode="derived",
        sample_size=len(trend_series),
        confidence="high" if len(trend_series) >= 100 else "medium",
    )

    return ok(
        {
            "idea_draft_blueprint": idea_draft_blueprint,
            "all_campaigns": all_campaigns,
            "active_campaign": active_camp,
            "occasion_traits": occasion_traits,
            "selected_category_slug": cat_slug,
            "keyword": active_camp["name"],
            "primary_keyword": primary_kw,
            "decomposition": stl,
            "amplitude": round(sum(stl["seasonal"][:10]) / 10, 2) if stl["seasonal"] else 0.5,
            "n_points": len(trend_series),
            "sample_size_n": measured_sample_size,
            "measured_cycles": measured_cycles,
            "route_risks": route_risks,
            "scorecard_metrics": scorecard_metrics,
            "opportunity_keywords": opportunity_keywords,
            "campaign_funnel": funnel_data.get("campaign_funnel"),
            "channel_breakdown": funnel_data.get("channel_breakdown"),
            "motivation_breakdown": funnel_data.get("motivation_breakdown"),
            "events": events_payload,
            "potential_profiles": potential_profiles,
            "campaign_radar": campaign_radar,
            "ready_to_ship_ideas": ready_ideas,
            "pod_blanks": pod_blanks,
            "opportunity_clusters": opportunity_clusters,
            "shop_products": shop_products,
            "matching_shop_products": matching_shop_products,
            "story": story,
            "apply_playbooks": apply_playbooks,
            "impact": impact,
            "industry_compare": traits_cmp["_meta"],
            "forecast_method_info": {
                "method": method_meta.get("method", "seasonal_naive_conformal"),
                "method_display_name": (
                    "Seasonal-Naive Conformal (Hiệu chuẩn lỗi thực nghiệm)"
                    if method_meta.get("method") == "seasonal_naive_conformal"
                    else "Deep Learning TFT + Lunar-Attention (5-Seed Ensemble)"
                ),
                "validated_deep_model": method_meta.get("validated_deep_model", False),
                "empirical_coverage_pct": scorecard_metrics[0]["actualRatePct"],
                "improvement_pct": scorecard_metrics[1]["actualRatePct"],
                "uplift_p10": uplift_res.get("uplift_p10") if uplift_res else None,
                "uplift_p50": uplift_res.get("uplift_p50") if uplift_res else None,
                "uplift_p90": uplift_res.get("uplift_p90") if uplift_res else None,
            },
            "method": f"Thống kê mô tả từ {measured_sample_size:,} đơn hàng thật + Lịch quốc gia calendar_vn + Kiểm chứng 5 lớp",
            "limitation": "Không có dữ liệu nào đảm bảo chắc chắn sản phẩm sẽ bán chạy. Seller cần tự kiểm tra bằng chứng và bắt đầu từ bước Thử nhỏ.",
        },
        meta,
    )
