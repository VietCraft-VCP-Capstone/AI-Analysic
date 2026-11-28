from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

from app.core.seasonal_intel import build_playbook, impact_report
from app.services.f38.f38_constants import CAT_LABELS


def build_story_and_playbooks(
    *,
    active_camp: Dict[str, Any],
    cat_slug: str,
    ready_ideas: List[Dict[str, Any]],
    potential_profiles: List[Dict[str, Any]],
    occasion_traits: List[Dict[str, Any]],
    shop_orders_hist: List[Dict[str, Any]],
    event_dates_by_year: Dict[int, date],
    target_ev_d: date,
    cut_off_d: date,
    lead_time_days: int,
    hom_nay: date,
    uplift_res: Optional[Dict[str, Any]],
) -> Tuple[Dict[str, Any], List[Dict[str, Any]], Dict[str, Any]]:
    """Tạo báo cáo thành quả (phản thực), bộ kế hoạch áp dụng và câu chuyện 4 chương."""
    prev_candidates = [d for d in event_dates_by_year.values() if d < target_ev_d - timedelta(days=60)]
    prev_event = max(prev_candidates) if prev_candidates else None
    adopted_kws = [i["keyword"] for i in ready_ideas[:3] if i.get("keyword")]

    impact = impact_report(shop_orders_hist, target_ev_d, lead_time_days, hom_nay, adopted_kws, uplift_res, prev_event)
    impact["shop_orders_total"] = len(shop_orders_hist)
    impact["uplift_basis"] = (uplift_res or {}).get("basis")

    apply_playbooks = [
        {
            **build_playbook(i, cut_off_d, target_ev_d, hom_nay, uplift_res, impact.get("baseline_orders_per_day"), 4),
            "evidence_level": i.get("evidence_level"),
            "signal_label": i.get("signal_label"),
            "shop_coverage": i.get("shop_coverage"),
        }
        for i in ready_ideas[:4]
    ]

    days_to_event = (target_ev_d - hom_nay).days
    days_to_cut = (cut_off_d - hom_nay).days
    n_pass = sum(1 for p in potential_profiles if p.get("is_recommended_for_launch"))
    measured_traits = [t for t in occasion_traits if t.get("comparison_basis") == "measured_shop"]
    gap_traits = sorted(
        [t for t in measured_traits if t["comparison"]["gap"] is not None],
        key=lambda t: abs(t["comparison"]["gap"]),
        reverse=True,
    )

    story: Dict[str, Any] = {
        "overview": {
            "title": "Tổng quan",
            "headline": f"{active_camp['name']} — {n_pass}/{len(potential_profiles)} ý tưởng đạt chuẩn triển khai",
            "bullets": [f"Còn {days_to_event} ngày đến cao điểm · {days_to_cut} ngày đến hạn chốt đơn"],
            "next_step": "Xem ý tưởng",
            "cta_tab": "act1",
        },
        "ideas": {
            "title": "Ý tưởng",
            "headline": f"{len(ready_ideas)} ý tưởng cho ngành {CAT_LABELS.get(cat_slug, 'Toàn ngành hàng TMĐT')} · {n_pass} đạt hồ sơ 5 lớp",
            "bullets": [
                (
                    f"Hành vi mua: shop khác ngành rõ nhất ở «{gap_traits[0]['name']}» ({gap_traits[0]['diffText']})"
                    if gap_traits
                    else "Chưa đủ đơn dịp trước của shop để so với ngành — đang dùng mặt bằng ngành/mô hình"
                ),
                f"{sum(1 for i in ready_ideas if i.get('evidence_level') == 'template')} ý tưởng chỉ là gợi ý tham khảo (chưa có dữ liệu bán thật)",
            ],
            "next_step": "Sang Áp dụng",
            "cta_tab": "act2",
        },
        "apply": {
            "title": "Áp dụng",
            "headline": f"{sum(1 for p in apply_playbooks if p['feasible'])}/{len(apply_playbooks)} kế hoạch kịp hạn chốt đơn",
            "bullets": [
                f"Mỗi kế hoạch lùi từ hạn chốt {cut_off_d.strftime('%d/%m')} với mốc, KPI và dừng lỗ",
                (
                    "Mức ngày thường = nhịp đơn nền 8 tuần của shop × số ngày (chưa tính độ tăng của dịp)"
                    if impact.get("baseline_orders_per_day") is not None
                    else "Shop chưa đủ đơn nền 8 tuần để ước lượng kỳ vọng đơn"
                ),
            ],
            "next_step": "Xem thành quả",
            "cta_tab": "act3",
        },
        "results": {
            "title": "Thành quả",
            "headline": {
                "upcoming": "Chưa vào mùa — đây là số đơn nếu bán như ngày thường",
                "running": "Đang vào mùa — so với kịch bản bán như ngày thường",
                "ended": "Mùa đã kết thúc — kết quả so với kịch bản bán như ngày thường",
            }[impact["phase"]],
            "bullets": [],
            "next_step": "Quay lại tổng quan",
            "cta_tab": "hub",
        },
    }

    if impact.get("status") == "measured":
        cf = impact["counterfactual_orders"]
        story["results"]["bullets"] = [
            f"Thực tế {impact['actual_orders']} đơn · nếu bán như ngày thường ≈ {cf['p50']:.0f} đơn (80%: {cf['p10']:.0f}–{cf['p90']:.0f})",
            f"Đơn từ ý tưởng đã gợi ý: {impact['adopted_orders']} ({impact['adopted_share_pct']}% tổng đơn)",
        ]
    elif impact.get("status") == "projected":
        story["results"]["bullets"] = [
            f"Nếu bán như ngày thường: {impact['expected_orders_p10']:.0f}–{impact['expected_orders_p90']:.0f} đơn trong cửa sổ dịp (trung vị {impact['expected_orders_p50']:.0f})",
            "Số đo thật xuất hiện khi dịp bắt đầu",
        ]
    else:
        story["results"]["bullets"] = ["Shop chưa đủ đơn nền 8 tuần trước dịp để ước lượng kịch bản không áp dụng"]

    return impact, apply_playbooks, story


def build_idea_draft_blueprint(
    *,
    cat_slug: str,
    active_camp: Dict[str, Any],
    shop_products: List[Dict[str, Any]],
    shop_orders_hist: List[Dict[str, Any]],
    raw_ext_ready: List[Dict[str, Any]],
    real_blueprints: List[Dict[str, Any]],
    ind_scale: Dict[str, Any],
    method_meta: Dict[str, Any],
    uplift_res: Optional[Dict[str, Any]],
    orders_growth_pct: Optional[int],
    spending_growth_pct: Optional[int],
    early_order_days: Optional[int],
    peak_clump_pct: Optional[float],
    ind_combo_blend: Optional[float],
    ind_voucher_blend: Optional[float],
    opportunity_keywords: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Đóng gói bản phác thảo định lượng (Data-Grounded Blueprint) để scope chặt cho LLM."""
    tag_counts: Dict[str, int] = {}
    s_prices: List[int] = []
    s_titles: List[str] = []
    for sp in shop_products:
        if sp.get("title"):
            s_titles.append(str(sp["title"]))
        pv = int(sp.get("price_vnd") or 0)
        if pv >= 30000:
            s_prices.append(pv)
        for tg in sp.get("tags") or []:
            clean_tg = str(tg or "").strip().lower()
            if clean_tg:
                tag_counts[clean_tg] = tag_counts.get(clean_tg, 0) + 1

    style_kws = [k for k, _ in sorted(tag_counts.items(), key=lambda kv: kv[1], reverse=True)[:6]]
    p_min = min(s_prices) if s_prices else 150000
    p_max = max(s_prices) if s_prices else 450000
    p_avg = int(round(sum(s_prices) / len(s_prices), -3)) if s_prices else 260000

    occ_prices = [int(x.get("price_vnd") or 0) for x in raw_ext_ready if int(x.get("price_vnd") or 0) > 0]
    occ_p_min = min(occ_prices) if occ_prices else p_min
    occ_p_max = max(occ_prices) if occ_prices else p_max
    occ_p_avg = int(round(sum(occ_prices) / len(occ_prices), -3)) if occ_prices else p_avg

    top_occ_clusters = [
        {
            "title": bp.get("title"),
            "keyword": bp.get("keyword"),
            "price_vnd": bp.get("price"),
            "sold_count": bp.get("cluster_total_sold") or bp.get("sold_count") or 0,
            "favorers_count": bp.get("cluster_total_favorers") or bp.get("num_favorers") or 0,
            "seller_count": bp.get("seller_count") or 0,
            "platform": bp.get("platform") or "Tiki",
        }
        for bp in (real_blueprints or [])[:4]
    ]

    return {
        "category_slug": cat_slug,
        "occasion_id": active_camp["id"],
        "occasion_name": active_camp["name"],
        "shop_dna": {
            "style_keywords": style_kws,
            "sample_titles": s_titles[:5],
            "price_band": {"min": p_min, "max": p_max, "avg": p_avg},
            "product_count": len(shop_products),
            "order_count": len(shop_orders_hist),
        },
        "occasion_industry_benchmarks": {
            "price_band": {"min": occ_p_min, "max": occ_p_max, "avg": occ_p_avg},
            "top_selling_clusters": top_occ_clusters,
            "occasion_products_count": ind_scale.get("occasionProductsCount") or len(raw_ext_ready),
        },
        "dl_and_stl_signals": {
            "model": method_meta.get("method", "seasonal_naive_conformal"),
            "uplift_p10": uplift_res.get("uplift_p10") if uplift_res else None,
            "uplift_p50": uplift_res.get("uplift_p50") if uplift_res else None,
            "uplift_p90": uplift_res.get("uplift_p90") if uplift_res else None,
            "orders_growth_pct": orders_growth_pct,
            "spending_growth_pct": spending_growth_pct,
            "early_order_days": early_order_days,
            "peak_clump_pct": peak_clump_pct,
            "combo_pct": ind_combo_blend,
            "voucher_pct": ind_voucher_blend,
        },
        "market_scale": ind_scale,
        "top_opportunity_keywords": [
            {
                "tag": k.get("tag"),
                "volume": k.get("sold_count_real") or k.get("etsy_favorers") or k.get("volume") or 0,
                "sold_count_real": k.get("sold_count_real") or 0,
                "etsy_favorers": k.get("etsy_favorers") or 0,
                "sales_per_shop": k.get("sales_per_shop"),
                "keyword_score": k.get("keyword_score"),
                "competition": k.get("competition", 0),
                "wow": k.get("search_wow_pct"),
            }
            for k in (opportunity_keywords or [])
            if k.get("keyword_score") is not None
        ][:5],
        "strict_scope": {
            "allowed_price_min": min(p_min, occ_p_min),
            "allowed_price_max": max(int(round(p_max * 1.25, -3)), occ_p_max),
            "must_ground_in_shop_style": True,
            "must_ground_in_occasion_industry": True,
        },
    }

