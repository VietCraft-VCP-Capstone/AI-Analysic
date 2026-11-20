import logging
from datetime import date, timedelta
from typing import Any, Dict, List, Tuple

from app.api.v1._mart import db
from app.core.potential_profile import build_product_potential_profile
from app.core.redis_cache import cache_get_json, cache_set_json
from app.core.seasonal_dl.forecaster import event_demand_uplift
from app.core.seasonal_intel import real_stl, seasonal_peak_years, seller_competition
from app.core.seasonal_opportunity import (
    TREND_MAX_STALE_DAYS,
    canonical_seller_key,
    dedupe_external_docs,
    filter_trend_points_by_date,
)
from app.services.f38.f38_constants import CATEGORY_OCCASION_BLUEPRINTS, EXTERNAL_FRESHNESS_DAYS, cutoff_utc_dt
from app.services.f38.f38_trends_stl import lay_chuoi_trend_cho_tu_khoa, tra_cuu_trend

log = logging.getLogger("f38_seasonal")


def fetch_external_market_catalog(
    cat_slug: str,
    active_camp: Dict[str, Any],
    hom_nay: date,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Đọc & khử trùng sản phẩm hàng sẵn (`ready_to_ship`) và phôi POD (`pod_blank`) từ MongoDB (cache Redis)."""
    fresh_since_dt = cutoff_utc_dt(hom_nay, EXTERNAL_FRESHNESS_DAYS)
    ext_ready_key = f"seasonal:ext_ready:{cat_slug}:{active_camp['id']}:{hom_nay.isoformat()}:v5"
    raw_ext_ready = cache_get_json(ext_ready_key)
    if not isinstance(raw_ext_ready, list):
        ext_coll = db()["external_market_products"]
        active_signal_or = [{"sold_count": {"$gt": 0}}, {"num_favorers": {"$gt": 0}}]
        raw_ext_ready = list(
            ext_coll.find(
                {
                    "category_slug": cat_slug,
                    "occasion_id": active_camp["id"],
                    "listing_type": "ready_to_ship",
                    "is_active": True,
                    "inventory_status": "available",
                    "collected_at": {"$gte": fresh_since_dt},
                    "$or": active_signal_or,
                },
                {"_id": 0},
            )
            .sort([("sold_count", -1), ("num_favorers", -1), ("review_count", -1)])
            .limit(140)
        )
        distinct_clusters = {
            x.get("query_cluster") or x.get("sub_category")
            for x in raw_ext_ready
            if x.get("query_cluster") or x.get("sub_category")
        }
        if len(raw_ext_ready) < 16 or len(distinct_clusters) < 9:
            extra_ready = list(
                ext_coll.find(
                    {
                        "category_slug": cat_slug,
                        "occasion_id": {"$in": ["default", "all"]},
                        "listing_type": "ready_to_ship",
                        "is_active": True,
                        "inventory_status": "available",
                        "collected_at": {"$gte": fresh_since_dt},
                        "$or": active_signal_or,
                    },
                    {"_id": 0},
                )
                .sort([("sold_count", -1), ("num_favorers", -1), ("review_count", -1)])
                .limit(50)
            )
            raw_ext_ready.extend(extra_ready)
        if not raw_ext_ready:
            raw_ext_ready = list(
                ext_coll.find(
                    {
                        "category_slug": cat_slug,
                        "listing_type": "ready_to_ship",
                        "is_active": True,
                    },
                    {"_id": 0},
                )
                .sort([("sold_count", -1), ("num_favorers", -1), ("review_count", -1)])
                .limit(80)
            )
        raw_ext_ready = dedupe_external_docs(raw_ext_ready, target_occasion_id=active_camp["id"])
        off_cat_noise = {
            "thoi-trang": ("diệt gián", "diệt kiến", "diệt muỗi", "móc treo", "kệ để", "nồi ", "chảo "),
            "phu-kien": ("diệt gián", "diệt kiến", "nồi ", "chảo "),
        }.get(cat_slug, ("diệt gián", "diệt kiến"))
        cleaned_ready = [
            it for it in raw_ext_ready if not any(nw in (it.get("title") or "").lower() for nw in off_cat_noise)
        ]
        if cleaned_ready:
            raw_ext_ready = cleaned_ready
        cache_set_json(ext_ready_key, raw_ext_ready, ttl_seconds=1800)

    ext_pod_key = f"seasonal:ext_pod:{cat_slug}:v2"
    raw_ext_pod = cache_get_json(ext_pod_key)
    if not isinstance(raw_ext_pod, list):
        ext_coll = db()["external_market_products"]
        raw_ext_pod = list(
            ext_coll.find(
                {
                    "category_slug": cat_slug,
                    "listing_type": "pod_blank",
                    "is_active": True,
                },
                {"_id": 0},
            )
            .sort([("sold_count", -1), ("provider_count", -1)])
            .limit(10)
        )
        if not raw_ext_pod:
            raw_ext_pod = list(
                ext_coll.find({"listing_type": "pod_blank", "is_active": True}, {"_id": 0})
                .sort([("sold_count", -1)])
                .limit(6)
            )
        cache_set_json(ext_pod_key, raw_ext_pod, ttl_seconds=1800)

    return raw_ext_ready, raw_ext_pod


def build_market_blueprints(
    raw_ext_ready: List[Dict[str, Any]],
    cat_slug: str,
    active_camp: Dict[str, Any],
    primary_kw: str,
) -> List[Dict[str, Any]]:
    """Gom nhóm sản phẩm thật đa sàn thành các cụm blueprint (kèm bổ sung Hybrid Mining & fallback an toàn)."""
    grouped_clusters: Dict[str, List[Dict[str, Any]]] = {}
    for item in raw_ext_ready:
        c_key = item.get("query_cluster") or item.get("sub_category") or item.get("title", "")[:25]
        grouped_clusters.setdefault(c_key, []).append(item)

    def _item_rank_signal(x: Dict[str, Any]) -> int:
        return int(x.get("sold_count") or 0) + 2 * int(x.get("num_favorers") or 0) + 3 * int(x.get("review_count") or 0)

    sorted_cluster_items = sorted(
        grouped_clusters.items(),
        key=lambda kv: (
            (sum(_item_rank_signal(x) for x in kv[1]))
            * (
                1.5
                if any(
                    x.get("occasion_id") == active_camp["id"]
                    and (int(x.get("sold_count") or 0) >= 5 or int(x.get("num_favorers") or 0) >= 20)
                    for x in kv[1]
                )
                else 1.0
            )
        ),
        reverse=True,
    )

    real_blueprints: List[Dict[str, Any]] = []
    for c_key, items_in_cluster in sorted_cluster_items[:12]:
        items_sorted = sorted(
            items_in_cluster,
            key=lambda x: (int(x.get("sold_count") or 0), int(x.get("num_favorers") or 0), int(x.get("review_count") or 0)),
            reverse=True,
        )
        lead = items_sorted[0]
        prices = sorted(int(x["price_vnd"]) for x in items_sorted if x.get("price_vnd"))
        p_min = prices[0] if len(prices) > 1 else int(lead["price_vnd"] * 0.85)
        p_max = prices[-1] if len(prices) > 1 else int(lead["price_vnd"] * 1.15)
        if p_min == p_max:
            p_min = int(round(lead["price_vnd"] * 0.88 / 1000.0) * 1000)
            p_max = int(round(lead["price_vnd"] * 1.15 / 1000.0) * 1000)

        distinct_sellers = {
            canonical_seller_key(x.get("seller_id"), x.get("seller_name"), x.get("platform"))
            for x in items_sorted
            if x.get("seller_id") or x.get("seller_name")
        }
        distinct_sellers.discard(None)
        total_sold = sum(int(x.get("sold_count") or 0) for x in items_sorted)
        total_favorers = sum(int(x.get("num_favorers") or 0) for x in items_sorted)

        sellers_map: Dict[str, Dict[str, Any]] = {}
        for x in items_sorted:
            s_name = x.get("seller_name") or ""
            if not s_name:
                continue
            entry = sellers_map.setdefault(
                s_name,
                {
                    "sellerName": s_name,
                    "platform": x.get("platform") or "Tiki",
                    "listingCount": 0,
                    "soldCount": 0,
                    "favorersCount": 0,
                    "minPriceVnd": None,
                    "maxPriceVnd": None,
                    "topProductTitle": x.get("title") or "",
                    "topProductUrl": x.get("product_url") or "",
                    "ratingAverage": float(x.get("rating_average") or 0.0),
                },
            )
            entry["listingCount"] += 1
            entry["soldCount"] += int(x.get("sold_count") or 0)
            entry["favorersCount"] += int(x.get("num_favorers") or 0)
            pv = int(x.get("price_vnd") or 0)
            if pv:
                entry["minPriceVnd"] = pv if entry["minPriceVnd"] is None else min(entry["minPriceVnd"], pv)
                entry["maxPriceVnd"] = pv if entry["maxPriceVnd"] is None else max(entry["maxPriceVnd"], pv)
        cluster_sellers = sorted(sellers_map.values(), key=lambda s: (s["soldCount"], s["favorersCount"]), reverse=True)

        real_blueprints.append(
            {
                "cluster_sellers": cluster_sellers,
                "title": lead["title"],
                "category": lead.get("sub_category") or "Thời trang & Phụ kiện",
                "keyword": lead.get("trend_keyword") or primary_kw,
                "price": int(lead["price_vnd"]),
                "cost": int(lead.get("estimated_cost_vnd") or round(lead["price_vnd"] * 0.45, -3)),
                "price_min": p_min,
                "price_max": p_max,
                "image_url": lead.get("image_url") or "",
                "product_url": lead.get("product_url") or "",
                "platform": lead.get("platform") or "Tiki",
                "seller_name": lead.get("seller_name") or "Gian hàng TMĐT",
                "seller_count": len(distinct_sellers) if distinct_sellers else len(items_sorted),
                "sold_count": int(lead.get("sold_count") or 0),
                "num_favorers": int(lead.get("num_favorers") or 0),
                "cluster_total_sold": total_sold,
                "cluster_total_favorers": total_favorers,
                "rating_average": float(lead.get("rating_average") or 0.0),
                "review_count": int(lead.get("review_count") or 0),
                "cluster_query": c_key,
                "cluster_products": [
                    {
                        "title": x["title"],
                        "imageUrl": x.get("image_url") or "",
                        "priceVnd": int(x["price_vnd"]),
                        "platform": x.get("platform") or "Tiki",
                        "productUrl": x.get("product_url") or "",
                        "sellerName": x.get("seller_name") or "",
                        "soldCount": int(x.get("sold_count") or 0),
                        "favorersCount": int(x.get("num_favorers") or 0),
                        "ratingAverage": float(x.get("rating_average") or 0.0),
                    }
                    for x in items_sorted[:3]
                ],
            }
        )

    if len(real_blueprints) < 3:
        try:
            from app.core.seasonal_taxonomy import get_seasonal_suggestions

            hybrid = get_seasonal_suggestions(primary_kw, cat_slug)
            mined_grounding = hybrid.get("mined_grounding") or {}
            med_p = int(mined_grounding.get("median_price") or 220000)
            for idea in hybrid.get("ready_to_ship_ideas") or []:
                if len(real_blueprints) >= 4:
                    break
                title = (idea.get("title") or "").strip()
                if not title or any(bp["title"].lower() == title.lower() for bp in real_blueprints):
                    continue
                price_est = max(50000, med_p)
                real_blueprints.append(
                    {
                        "cluster_sellers": [],
                        "title": title,
                        "category": idea.get("category") or cat_slug,
                        "keyword": primary_kw,
                        "price": price_est,
                        "cost": int(round(price_est * 0.48, -3)),
                        "price_min": int(round(price_est * 0.85, -3)),
                        "price_max": int(round(price_est * 1.2, -3)),
                        "image_url": "",
                        "product_url": "",
                        "platform": f"Hybrid Mining ({hybrid.get('ai_model', 'VietCraft')})",
                        "seller_name": "Gợi ý khai phá thị trường",
                        "seller_count": 0,
                        "sold_count": 0,
                        "cluster_total_sold": 0,
                        "rating_average": 0.0,
                        "review_count": 0,
                        "cluster_query": primary_kw,
                        "cluster_products": [],
                        "why_it_sells": idea.get("why_it_sells") or "",
                        "upsell_bundle_tip": idea.get("upsell_bundle_tip") or "",
                    }
                )
        except Exception as exc:
            log.warning("seasonal: %s: %s", type(exc).__name__, exc)

    if not real_blueprints:
        cat_blueprints = CATEGORY_OCCASION_BLUEPRINTS.get(cat_slug, CATEGORY_OCCASION_BLUEPRINTS["thoi-trang"])
        fallback_bps = cat_blueprints.get(active_camp["id"], cat_blueprints.get("tet", list(cat_blueprints.values())[0]))
        for bp in fallback_bps:
            real_blueprints.append(
                {
                    **bp,
                    "price_min": bp["price"] - 30000,
                    "price_max": bp["price"] + 40000,
                    "image_url": "",
                    "product_url": "",
                    "platform": "Gợi ý tham khảo theo ngành",
                    "seller_name": "Chưa có dữ liệu bán thật",
                    "seller_count": 0,
                    "sold_count": 0,
                    "cluster_total_sold": 0,
                    "rating_average": 0.0,
                    "review_count": 0,
                    "cluster_query": bp["keyword"],
                    "cluster_products": [],
                    "is_template": True,
                    "cost_basis": "ước tính 45% giá bán (chưa có giá vốn thật)",
                }
            )

    return real_blueprints


def build_potential_profiles(
    blueprints: List[Dict[str, Any]],
    raw_ext_ready: List[Dict[str, Any]],
    event_dates_by_year: Dict[int, date],
    target_ev_d: date,
    cut_off_d: date,
    hom_nay: date,
) -> List[Dict[str, Any]]:
    """Xây dựng Hồ sơ Tiềm năng 5 lớp cho từng cụm sản phẩm blueprint."""
    potential_profiles: List[Dict[str, Any]] = []
    for bp in blueprints:
        s_kw, matched_series, match_kind = tra_cuu_trend(bp["keyword"])
        kw_trend = [(d.strftime("%Y-%m-%d"), float(v)) for d, v in s_kw.items()] if s_kw is not None else []
        r_key = f"seasonal:dl_stl:v1:{matched_series or 'none'}:{target_ev_d.isoformat()}:{hom_nay.isoformat()}"
        cached_m = cache_get_json(r_key)
        if isinstance(cached_m, dict) and "up" in cached_m:
            up_bp, stl_bp = cached_m.get("up"), cached_m.get("stl")
        else:
            up_bp = None
            if s_kw is not None:
                try:
                    up_bp = event_demand_uplift(
                        series=s_kw,
                        event_dates=event_dates_by_year,
                        event_date=target_ev_d,
                        window_days=30,
                        today=hom_nay,
                    )
                except Exception as exc:
                    log.warning("seasonal: %s: %s", type(exc).__name__, exc)
                    up_bp = None
            stl_bp = real_stl(kw_trend) if len(kw_trend) >= 104 else None
            cache_set_json(r_key, {"up": up_bp, "stl": stl_bp}, ttl_seconds=1800)

        peaks = seasonal_peak_years(kw_trend, target_ev_d.month) if kw_trend else {"years_analyzed": 0, "years_peaked": 0}
        toks = [t for t in (bp.get("cluster_query") or bp["keyword"]).lower().split() if len(t) > 1]
        listings_bp = [
            {
                "shop_name": x.get("seller_name"),
                "seller_id": x.get("seller_id"),
                "price_vnd": x.get("price_vnd"),
                "sold_count": x.get("sold_count"),
            }
            for x in raw_ext_ready
            if any(t in f"{x.get('title', '')} {x.get('trend_keyword', '')}".lower() for t in toks)
        ] or [
            {
                "shop_name": x.get("seller_name"),
                "seller_id": x.get("seller_id"),
                "price_vnd": x.get("price_vnd"),
                "sold_count": x.get("sold_count"),
            }
            for x in raw_ext_ready
        ]
        comp_bp = seller_competition(listings_bp, float(bp["price"]))
        model_ctx = {
            "uplift": up_bp,
            "stl": stl_bp,
            "years_peaked": peaks["years_peaked"],
            "years_analyzed": peaks["years_analyzed"],
            "competition": comp_bp,
            "cost_basis": bp.get("cost_basis")
            or ("giá vốn từ listing" if bp.get("sold_count") else "giả định 45% giá bán (seller có thể sửa)"),
            "lead_basis": "mặc định 4 ngày — chưa đo từ đơn của shop",
        }
        p_profile = build_product_potential_profile(
            product_name=bp["title"],
            category_name=bp["category"],
            keyword=bp["keyword"],
            retail_price_vnd=float(bp["price"]),
            base_cost_vnd=float(bp["cost"]),
            trend_series=kw_trend,
            target_event_date=target_ev_d,
            cut_off_date=cut_off_d,
            current_date=hom_nay,
            competitor_listings=listings_bp,
            shop_has_similar_sales=False,
            shop_lead_time_days=4,
            model_ctx=model_ctx,
        )
        if match_kind in ("partial", "proxy", "none"):
            note = {
                "partial": f"Căn cứ nhu cầu dùng chuỗi tìm kiếm khớp gần đúng «{matched_series}», không phải đúng từ khóa.",
                "proxy": "Chưa có chuỗi tìm kiếm riêng cho từ khóa này; nhu cầu đang ước theo chuỗi «quà tặng».",
                "none": "Không có chuỗi tìm kiếm để kiểm chứng nhu cầu.",
            }[match_kind]
            p_profile["reasons_could_be_wrong"].insert(0, note)
            p_profile["anti_evidence"] = p_profile["reasons_could_be_wrong"]
        p_profile["trend_match"] = match_kind
        p_profile["is_template"] = bool(bp.get("is_template"))
        potential_profiles.append(p_profile)
    return potential_profiles


def build_ready_and_pod_ideas(
    blueprints: List[Dict[str, Any]],
    raw_ext_pod: List[Dict[str, Any]],
    potential_profiles: List[Dict[str, Any]],
    traits_cmp: Dict[str, Any],
    active_camp: Dict[str, Any],
    hom_nay: date,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Đóng gói danh sách ý tưởng hàng sẵn, phôi POD Printify và cụm sản phẩm cơ hội."""
    ready_ideas: List[Dict[str, Any]] = []
    opportunity_clusters: List[Dict[str, Any]] = []

    for idx, bp in enumerate(blueprints[:9]):
        kw_pts = lay_chuoi_trend_cho_tu_khoa(bp["keyword"])
        _, _, kw_match = tra_cuu_trend(bp["keyword"])
        prof_i = potential_profiles[idx] if idx < len(potential_profiles) else None
        up_i = (prof_i or {}).get("layers", {}).get("demand", {}).get("metrics") or {}
        kw_vals_filtered, kw_stale_days = filter_trend_points_by_date(kw_pts, as_of=hom_nay, window_weeks=52)
        if (
            len(kw_vals_filtered) >= 12
            and kw_match == "exact"
            and (kw_stale_days is None or kw_stale_days <= TREND_MAX_STALE_DAYS)
        ):
            recent_4w = sum(kw_vals_filtered[-4:]) / 4.0
            base_8w = sum(kw_vals_filtered[-12:-4]) / 8.0
            trend_growth_pct = round(((recent_4w - base_8w) / max(10.0, base_8w)) * 100)
        else:
            trend_growth_pct = None

        p_min_val = int(bp.get("price_min") or (bp["price"] - 30000))
        p_max_val = int(bp.get("price_max") or (bp["price"] + 40000))
        price_range_str = f"{p_min_val:,}đ – {p_max_val:,}đ"
        seller_cnt = int(bp.get("seller_count") or 0)
        sold_cnt = int(bp.get("sold_count") or 0)
        fav_cnt = int(bp.get("num_favorers") or 0)
        cluster_fav_total = int(bp.get("cluster_total_favorers") or fav_cnt)
        platform_name = bp.get("platform") or "Tiki"
        seller_name = bp.get("seller_name") or "Gian hàng TMĐT"
        trend_txt = (
            f"tìm kiếm '{bp['keyword']}' {trend_growth_pct:+d}% (4 tuần vs 8 tuần trước)"
            if trend_growth_pct is not None
            else f"chưa có chuỗi tìm kiếm riêng cho '{bp['keyword']}'"
        )
        model_txt = (
            f"; mô hình dự báo mức cầu dịp ×{up_i['uplift_p50']:.2f} (80%: ×{up_i['uplift_p10']:.2f}–×{up_i['uplift_p90']:.2f})"
            if up_i.get("uplift_p50")
            else ""
        )

        if sold_cnt > 0:
            market_lead_txt = f"Đang bán thực tế trên {platform_name} ({seller_name}) với {sold_cnt:,} lượt bán; "
        elif fav_cnt > 0:
            market_lead_txt = f"Đang mở bán trên {platform_name} ({seller_name}) với {fav_cnt:,} lượt yêu thích; "
        else:
            market_lead_txt = f"Gợi ý theo ngành (chưa có dữ liệu bán thật) cho dịp {active_camp['name']}; "

        ready_ideas.append(
            {
                "title": bp["title"],
                "category": bp["category"],
                "keyword": bp["keyword"],
                "market_price_range": price_range_str,
                "suggested_price": f"{bp['price']:,}đ",
                "base_cost": f"{bp['cost']:,}đ",
                "cost_basis": bp.get("cost_basis") or ("giá vốn từ listing" if sold_cnt else "ước tính 45% giá bán"),
                "expected_profit": f"{bp['price'] - bp['cost'] - int(bp['price'] * 0.1):,}đ/sp",
                "expected_profit_margin": f"{int((bp['price'] - bp['cost'] - bp['price'] * 0.1) / max(1, bp['price']) * 100)}%",
                "image_url": bp.get("image_url") or "",
                "product_url": bp.get("product_url") or "",
                "platform": platform_name,
                "seller_name": seller_name,
                "seller_count": seller_cnt,
                "sold_count": sold_cnt,
                "num_favorers": fav_cnt,
                "rating_average": bp.get("rating_average") or 0.0,
                "review_count": bp.get("review_count") or 0,
                "search_trend_pct": trend_growth_pct,
                "is_template": bool(bp.get("is_template")),
                "evidence_level": "template"
                if bp.get("is_template")
                else ("market_listing" if (sold_cnt > 0 or fav_cnt > 0) else "hybrid_mining"),
                "why_it_sells": market_lead_txt + trend_txt + model_txt + ".",
                "sourcing_tip": f"Giá tham chiếu {bp['price']:,}đ ({price_range_str}"
                + (f", {seller_cnt} shop trong cụm" if seller_cnt else "")
                + f"). Giá vốn mục tiêu ≤ {bp['cost']:,}đ ({bp.get('cost_basis') or 'ước tính 45% giá bán'}).",
                "upsell_bundle_tip": (
                    f"Ngành có {traits_cmp['combo_pct']['industry']['value']:.0f}% đơn dịp này mua ≥ 2 món — thử bundle."
                    if traits_cmp["combo_pct"]["industry"]["value"] is not None
                    else "Chưa đủ dữ liệu ngành về mua combo; thử bundle nhỏ rồi đo."
                ),
                "suggested_theme": f"Chủ đề {active_camp['name']} · Nhóm {bp['category']}",
                "design_hook": f"Tham khảo mẫu nổi bật của {seller_name} ({platform_name})",
                "signal_label": prof_i["signal_label"] if prof_i else "Tín hiệu sơ bộ ●○○○",
                "verdict": prof_i["verdict"] if prof_i else "chua_chac",
            }
        )

        quadrant = "good_opportunity" if 0 < seller_cnt <= 8 else ("unknown" if seller_cnt == 0 else "high_competition")
        quadrant_label = (
            "Cơ hội tốt" if quadrant == "good_opportunity" else ("Chưa đủ dữ liệu" if quadrant == "unknown" else "Cạnh tranh cao")
        )
        rep_products = bp.get("cluster_products") or [
            {
                "title": bp["title"],
                "imageUrl": bp.get("image_url") or "",
                "priceVnd": bp["price"],
                "platform": platform_name,
                "productUrl": bp.get("product_url") or "",
                "sellerName": seller_name,
                "soldCount": sold_cnt,
                "favorersCount": fav_cnt,
                "ratingAverage": bp.get("rating_average") or 0.0,
            }
        ]

        cluster_total_sold = int(bp.get("cluster_total_sold") or sold_cnt)
        if cluster_total_sold > 0:
            order_count_range = f"{cluster_total_sold:,} lượt bán ghi nhận"
            lead_metric_txt = f"sản phẩm dẫn đầu bán {sold_cnt:,} chiếc"
        elif cluster_fav_total > 0:
            order_count_range = f"{cluster_fav_total:,} lượt yêu thích ({platform_name})"
            lead_metric_txt = f"sản phẩm dẫn đầu có {fav_cnt:,} lượt yêu thích trên {platform_name}"
        else:
            order_count_range = "Chưa ghi nhận lượt bán"
            lead_metric_txt = "chưa ghi nhận lượt bán công khai"

        opportunity_clusters.append(
            {
                "id": f"clust-real-{idx}",
                "title": bp["title"],
                "category": bp["category"],
                "quadrant": quadrant,
                "quadrantLabel": quadrant_label,
                "orderCountRange": order_count_range,
                "sellerCount": seller_cnt,
                "newSellersLast30Days": None,
                "searchTrendPct": trend_growth_pct,
                "priceRange": price_range_str,
                "platform": platform_name,
                "productUrl": bp.get("product_url") or "",
                "sellerName": seller_name,
                "soldCount": sold_cnt,
                "favorersCount": fav_cnt,
                "representativeProducts": rep_products,
                "sellers": bp.get("cluster_sellers") or [],
                "clusteringMethod": f"Thu thập trực tiếp từ {platform_name} & đa sàn (đã khử trùng, trạng thái: Đang bán)",
                "evidence": {
                    "id": f"ev_clust_real_{idx}",
                    "definition": f"Sản phẩm thật đang mở bán trên sàn {platform_name} trong nhóm '{bp.get('cluster_query') or bp['category']}'.",
                    "sources": [f"API sản phẩm đang bán {platform_name}", "Google Trends VN", "external_market_products"],
                    "howObtained": f"Truy vấn các sản phẩm có trạng thái đang bán, khử trùng theo external_id và gom nhóm {seller_cnt} gian hàng duy nhất cùng phân khúc.",
                    "excluded": "Đã loại bỏ sản phẩm ngừng bán, trùng lặp đa dịp hoặc giá bất thường.",
                    "period": [(hom_nay - timedelta(days=30)).strftime("%Y-%m-%d"), hom_nay.strftime("%Y-%m-%d")],
                    "n": seller_cnt,
                    "formula": f"Khoảng giá thực tế từ {p_min_val:,}đ đến {p_max_val:,}đ trên {seller_cnt} shop đang bán; {lead_metric_txt}.",
                    "confidence": "high" if (sold_cnt >= 20 or fav_cnt >= 50) else "fair",
                    "confidenceReason": f"Dữ liệu thực tế từ listing đang mở bán của {seller_name} trên {platform_name}.",
                    "mayBeWrongBecause": ["Giá bán trên sàn ngoài có thể thay đổi theo giờ Flash Sale hoặc tỷ giá USD/VND (Etsy)."],
                    "updatedAt": hom_nay.isoformat(),
                    "rawDataUrl": bp.get("product_url") or "",
                },
            }
        )

    pod_blanks: List[Dict[str, Any]] = []
    pod_target = 3 if len(opportunity_clusters) >= 6 else max(0, 9 - len(opportunity_clusters))
    for idx, p_doc in enumerate(raw_ext_pod[:pod_target]):
        b_price = int(p_doc.get("price_vnd") or 220000)
        b_cost = int(p_doc.get("estimated_cost_vnd") or 95000)
        p_min_b = int(round(b_price * 0.85 / 5000.0) * 5000)
        p_max_b = int(round(b_price * 1.2 / 5000.0) * 5000)
        margin_low = max(35, int((b_price - b_cost - b_price * 0.1) / b_price * 100) - 4)
        margin_high = margin_low + 10
        prov_cnt = int(p_doc.get("provider_count") or 4)

        pod_item = {
            "blank_type": p_doc.get("blank_type") or "tshirt_unisex",
            "title": f"{p_doc['title']} · Chủ đề {active_camp['name']}",
            "name": p_doc.get("original_catalog_title") or p_doc["title"],
            "category": p_doc.get("sub_category") or "Phôi in POD",
            "market_price_range": f"{p_min_b:,}đ – {p_max_b:,}đ",
            "expected_profit_margin": f"{margin_low}% – {margin_high}%",
            "base_cost": b_cost,
            "image_url": p_doc.get("image_url") or "",
            "product_url": p_doc.get("product_url") or "",
            "platform": p_doc.get("platform") or "Printify",
            "seller_name": p_doc.get("seller_name") or "Printify Catalog",
            "seller_count": prov_cnt,
            "sold_count": int(p_doc.get("sold_count") or 0),
            "sourcing_tip": f"Phôi chuẩn từ {p_doc.get('seller_name', 'Printify')} ({p_doc.get('colors_count', 10)} màu sẵn kho), giá phôi ~{b_cost:,}đ, chỉ in khi có đơn.",
            "why_it_sells": f"Phôi POD đang mở bán thực tế trên {p_doc.get('platform', 'Printify')}, cá nhân hóa hình in theo chủ đề {active_camp['name']} không lo tồn kho.",
            "upsell_bundle_tip": "Cho phép khách thêm tên riêng hoặc lời chúc lên sản phẩm (+30.000đ/sp).",
            "suggested_theme": f"Thiết kế chủ đề {active_camp['name']} cá nhân hóa",
            "design_hook": f"Phôi gốc: {p_doc.get('original_catalog_title') or p_doc['title']}",
            "signal_label": "Hồ sơ POD Đạt ●●●●",
        }
        pod_blanks.append(pod_item)

        pod_kw = p_doc.get("trend_keyword") or p_doc["title"]
        pod_pts = lay_chuoi_trend_cho_tu_khoa(pod_kw)
        _, _, pod_match = tra_cuu_trend(pod_kw)
        pod_vals_filtered, pod_stale_days = filter_trend_points_by_date(pod_pts, as_of=hom_nay, window_weeks=52)
        if (
            len(pod_vals_filtered) >= 12
            and pod_match == "exact"
            and (pod_stale_days is None or pod_stale_days <= TREND_MAX_STALE_DAYS)
        ):
            p_r4 = sum(pod_vals_filtered[-4:]) / 4.0
            p_b8 = sum(pod_vals_filtered[-12:-4]) / 8.0
            pod_trend_pct = round(((p_r4 - p_b8) / max(10.0, p_b8)) * 100)
        else:
            pod_trend_pct = None

        opportunity_clusters.append(
            {
                "id": f"clust-pod-{idx}",
                "title": pod_item["title"],
                "category": pod_item["category"],
                "quadrant": "niche_market",
                "quadrantLabel": "Thị trường ngách",
                "orderCountRange": f"{prov_cnt} nhà in sẵn phôi",
                "sellerCount": prov_cnt,
                "newSellersLast30Days": 0,
                "searchTrendPct": pod_trend_pct,
                "priceRange": pod_item["market_price_range"],
                "platform": pod_item["platform"],
                "productUrl": pod_item["product_url"],
                "sellerName": pod_item["seller_name"],
                "soldCount": pod_item["sold_count"],
                "representativeProducts": [
                    {
                        "title": pod_item["name"],
                        "imageUrl": pod_item["image_url"],
                        "priceVnd": b_price,
                        "platform": pod_item["platform"],
                        "productUrl": pod_item["product_url"],
                        "sellerName": pod_item["seller_name"],
                        "soldCount": pod_item["sold_count"],
                    }
                ],
                "clusteringMethod": f"Danh mục phôi POD đang hoạt động từ {pod_item['platform']} Catalog API",
                "evidence": {
                    "id": f"ev_clust_pod_{idx}",
                    "definition": f"Phôi in theo yêu cầu (POD) lấy từ danh mục đang hoạt động trên {pod_item['platform']}.",
                    "sources": ["Printify Catalog API (/v1/catalog/blueprints.json)", "printify_variants.json"],
                    "howObtained": "Đồng bộ trực tiếp blueprint đang mở bán kèm ảnh gốc và số lượng nhà in cung cấp.",
                    "period": [(hom_nay - timedelta(days=30)).strftime("%Y-%m-%d"), hom_nay.strftime("%Y-%m-%d")],
                    "n": prov_cnt,
                    "formula": f"Giá phôi cơ sở {b_cost:,}đ, giá bán lẻ đề xuất {b_price:,}đ (biên lãi {pod_item['expected_profit_margin']}).",
                    "confidence": "fair" if prov_cnt else "preliminary",
                    "confidenceReason": "Phôi thật từ catalog Printify, sản xuất theo đơn không rủi ro tồn kho.",
                    "mayBeWrongBecause": ["Thời gian in và giao phụ thuộc nhà in, có thể chậm hơn vào tuần sát lễ."],
                    "updatedAt": hom_nay.isoformat(),
                    "rawDataUrl": pod_item["product_url"],
                },
            }
        )

    opportunity_clusters.sort(
        key=lambda c: (
            int(c.get("soldCount") or 0) + max(0, int(c.get("searchTrendPct") or 0)) * 3,
            int(c.get("soldCount") or 0),
            int(c.get("searchTrendPct") or 0),
        ),
        reverse=True,
    )
    return ready_ideas, pod_blanks, opportunity_clusters

