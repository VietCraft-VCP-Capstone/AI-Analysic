import logging
from datetime import date
from typing import Any, Dict, List, Optional

from app.api.v1._live import db_live
from app.api.v1._mart import db
from app.core.redis_cache import cache_get_json, cache_set_json
from app.core.seasonal_intel import keyword_shop_coverage
from app.core.seasonal_opportunity import (
    TREND_MAX_STALE_DAYS,
    canonical_seller_key,
    dedupe_external_docs,
    score_opportunity_keywords,
)
from app.services.f38.f38_constants import (
    CAT_OCCASION_KEYWORDS,
    EXTERNAL_FRESHNESS_DAYS,
    VC_ORDER_WINDOW_DAYS,
    cutoff_utc_dt,
)
from app.services.f38.f38_trends_stl import load_vietcraft_real_sold_map, tra_cuu_trend

log = logging.getLogger("f38_seasonal")


def tinh_opportunity_keywords(
    active_camp: Dict[str, Any],
    cat_slug: str,
    hom_nay: date,
    measured_sample_size: int,
    orders_growth_pct: int,
    stl: Dict[str, Any],
    shop_products: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """
    Tính danh sách Từ khóa hot & Thẻ Tag đón đầu dịp:
    - Hợp nhất & khử trùng tuyệt đối 4 nguồn dữ liệu thật: Tiki + Etsy Open API v3 + VietCraft Live (90 ngày) + Google Trends VN.
    - Lọc độ tươi 30 ngày cho listing thị trường (`collected_at` / `fetched_at`), cửa sổ 90 ngày cho đơn VietCraft.
    - Chấm điểm theo 1 công thức thống nhất: 50% Sức cầu + 50% Dư địa/Shop (`score_opportunity_keywords`).
    - Trả kèm `source_breakdown` (số lượng & % theo từng sàn, phôi POD, sản phẩm cá nhân hóa).
    """
    camp_id = (active_camp.get("id") or "").lower()
    fresh_since_dt = cutoff_utc_dt(hom_nay, EXTERNAL_FRESHNESS_DAYS)

    # 1. Đọc & khử trùng sản phẩm thị trường đa sàn (ưu tiên bản ghi tươi trong 30 ngày gần nhất)
    ext_query: Dict[str, Any] = {"is_active": True}
    if cat_slug and cat_slug != "tong-hop":
        ext_query["category_slug"] = cat_slug

    ext_cache_key = f"seasonal:opp_ext_docs:{cat_slug or 'all'}:{camp_id}:{hom_nay.isoformat()}:v3"
    cached_ext_pack = cache_get_json(ext_cache_key)
    ext_data_stale = False
    if isinstance(cached_ext_pack, dict) and isinstance(cached_ext_pack.get("docs"), list):
        ext_docs = cached_ext_pack["docs"]
        ext_data_stale = bool(cached_ext_pack.get("stale"))
    else:
        try:
            proj = {
                "_id": 0,
                "external_id": 1,
                "platform": 1,
                "trend_keyword": 1,
                "sub_category": 1,
                "title": 1,
                "tags": 1,
                "sold_count": 1,
                "sold_delta_30d": 1,
                "favorers_delta_30d": 1,
                "delta_window_days": 1,
                "num_favorers": 1,
                "views": 1,
                "review_count": 1,
                "price_vnd": 1,
                "seller_id": 1,
                "seller_name": 1,
                "listing_type": 1,
                "customizable": 1,
                "occasion_id": 1,
                "rating_average": 1,
                "collected_at": 1,
            }
            fresh_ext_q = {**ext_query, "collected_at": {"$gte": fresh_since_dt}}
            occ_docs = list(
                db()["external_market_products"]
                .find({**fresh_ext_q, "occasion_id": camp_id}, proj)
                .sort([("sold_count", -1), ("num_favorers", -1)])
                .limit(200)
            )
            cat_docs = list(
                db()["external_market_products"]
                .find(fresh_ext_q, proj)
                .sort([("sold_count", -1), ("num_favorers", -1)])
                .limit(300)
            )
            ext_docs = dedupe_external_docs(occ_docs + cat_docs, target_occasion_id=camp_id)
            if not ext_docs:
                ext_data_stale = True
                occ_docs = list(
                    db()["external_market_products"]
                    .find({**ext_query, "occasion_id": camp_id}, proj)
                    .sort([("sold_count", -1), ("num_favorers", -1)])
                    .limit(200)
                )
                cat_docs = list(
                    db()["external_market_products"]
                    .find(ext_query, proj)
                    .sort([("sold_count", -1), ("num_favorers", -1)])
                    .limit(300)
                )
                ext_docs = dedupe_external_docs(occ_docs + cat_docs, target_occasion_id=camp_id)
            cache_set_json(ext_cache_key, {"docs": ext_docs, "stale": ext_data_stale}, ttl_seconds=1800)
        except Exception as exc:
            log.warning("seasonal: %s: %s", type(exc).__name__, exc)
            ext_docs = []

    # Bổ sung tín hiệu từ `market_listings` (crawler F42 Etsy + Tiki) — lọc độ tươi 30 ngày
    f42_cache_key = f"seasonal:opp_f42_market:{hom_nay.isoformat()}:v2"
    f42_listings = cache_get_json(f42_cache_key)
    if not isinstance(f42_listings, list):
        f42_listings = []
        try:
            f42_listings = list(
                db()["market_listings"]
                .find(
                    {"is_valid": True, "fetched_at": {"$gte": fresh_since_dt}},
                    {"_id": 1, "source": 1, "keyword": 1, "title": 1, "price": 1, "sold": 1, "review_count": 1},
                )
                .limit(600)
            )
            cache_set_json(f42_cache_key, f42_listings, ttl_seconds=1800)
        except Exception as exc:
            log.warning("seasonal: market_listings unavailable: %s", exc)
            f42_listings = []

    kw_stats: Dict[str, Dict[str, Any]] = {}
    seen_ext_ids_per_kw: Dict[str, set] = {}

    for doc in ext_docs:
        raw_kw = (doc.get("trend_keyword") or doc.get("sub_category") or "").strip().lower()
        if not raw_kw or len(raw_kw) < 3:
            continue
        ext_id = str(doc.get("external_id") or "")
        seen_set = seen_ext_ids_per_kw.setdefault(raw_kw, set())
        if ext_id and ext_id in seen_set:
            continue
        if ext_id:
            seen_set.add(ext_id)

        entry = kw_stats.setdefault(
            raw_kw,
            {
                "sold_sum": 0,
                "etsy_favorers": 0,
                "etsy_views": 0,
                "etsy_listings": 0,
                "prices": [],
                "sellers": set(),
                "platforms": set(),
                "platform_counts": {},
                "listing_count": 0,
                "occasion_hits": 0,
                "customizable": False,
                "customizable_count": 0,
                "listing_type": "physical",
                "pod_count": 0,
            },
        )
        plat = str(doc.get("platform") or "Tiki").strip()
        plat_low = plat.lower()
        entry["platforms"].add(plat)
        entry["platform_counts"][plat] = entry["platform_counts"].get(plat, 0) + 1

        if plat_low == "etsy":
            fav = int(doc.get("num_favorers") or doc.get("review_count") or 0)
            entry["etsy_favorers"] += fav
            entry["etsy_views"] += int(doc.get("views") or 0)
            entry["etsy_listings"] += 1
        else:
            entry["sold_sum"] += int(doc.get("sold_count") or 0)

        pv = int(doc.get("price_vnd") or 0)
        if pv > 0:
            entry["prices"].append(pv)

        s_key = canonical_seller_key(doc.get("seller_id"), doc.get("seller_name"), plat)
        if s_key:
            entry["sellers"].add(s_key)

        entry["listing_count"] += 1
        if (doc.get("occasion_id") or "").lower() == camp_id:
            entry["occasion_hits"] += 1
        if doc.get("customizable"):
            entry["customizable"] = True
            entry["customizable_count"] += 1
        ltype = (doc.get("listing_type") or "").lower()
        if ltype in ("pod", "pod_blank", "custom"):
            entry["listing_type"] = "pod" if ltype == "pod_blank" else ltype
        if ltype in ("pod", "pod_blank") or plat_low == "printify":
            entry["pod_count"] += 1

    # Đọc danh sách sản phẩm live VietCraft (kèm lượt bán thật trong cửa sổ 90 ngày gần nhất)
    plat_cache_key = f"seasonal:plat_prods:{hom_nay.isoformat()}:v3"
    platform_prods = cache_get_json(plat_cache_key)
    if not isinstance(platform_prods, list):
        platform_prods = []
        try:
            raw_prods = list(
                db_live()["products"]
                .find(
                    {"status": {"$ne": "DELETED"}, "is_hidden": {"$ne": True}},
                    {"_id": 1, "title": 1, "tags": 1, "shop_id": 1, "original_price": 1, "price": 1, "retail_price": 1},
                )
                .limit(1500)
            )
            vc_sold_map = load_vietcraft_real_sold_map(window_days=VC_ORDER_WINDOW_DAYS, as_of=hom_nay)
            for pp in raw_prods:
                pid_str = str(pp.get("_id") or "")
                platform_prods.append(
                    {
                        "pid": pid_str,
                        "title": pp.get("title") or "",
                        "tags": pp.get("tags") or [],
                        "shop_id": str(pp.get("shop_id") or ""),
                        "sold_count": vc_sold_map.get(pid_str, 0),
                        "price": int(pp.get("original_price") or pp.get("price") or pp.get("retail_price") or 0),
                    }
                )
            cache_set_json(plat_cache_key, platform_prods, ttl_seconds=1800)
        except Exception as exc:
            log.warning("seasonal: %s: %s", type(exc).__name__, exc)
            platform_prods = []

    # 2. Ưu tiên từ khóa khớp ĐÚNG DỊP + NGÀNH HÀNG trước, sau đó bổ sung seed dịp và từ khóa bán chạy ngành
    occasion_kw_items = [
        k
        for k, _ in sorted(
            ((k, v) for k, v in kw_stats.items() if v["occasion_hits"] > 0),
            key=lambda kv: (kv[1]["occasion_hits"], kv[1]["sold_sum"] + kv[1]["etsy_favorers"]),
            reverse=True,
        )
    ]
    general_kw_items = [
        k
        for k, _ in sorted(
            ((k, v) for k, v in kw_stats.items() if v["occasion_hits"] == 0),
            key=lambda kv: (kv[1]["sold_sum"] + kv[1]["etsy_favorers"]),
            reverse=True,
        )
    ]

    occasion_seeds: List[str] = []
    cat_kw_str = (
        CAT_OCCASION_KEYWORDS.get(cat_slug, {}).get(camp_id)
        or CAT_OCCASION_KEYWORDS.get("tong-hop", {}).get(camp_id)
        or ""
    )
    for part in cat_kw_str.split(","):
        s = part.strip().lower()
        if s and s not in occasion_kw_items and s not in occasion_seeds:
            occasion_seeds.append(s)
    for skw in active_camp.get("search_keywords", []):
        s = (skw or "").strip().lower()
        if s and s not in occasion_kw_items and s not in occasion_seeds:
            occasion_seeds.append(s)

    candidate_tags: List[str] = []
    for k in occasion_kw_items + occasion_seeds + general_kw_items:
        if k not in candidate_tags:
            candidate_tags.append(k)
        if len(candidate_tags) >= 10:
            break

    # 3. Thu thập đặc trưng thô đã khử trùng cho từng từ khóa ứng viên
    raw_rows: List[Dict[str, Any]] = []
    for idx, tag in enumerate(candidate_tags[:10]):
        st = kw_stats.get(tag)
        s_obj, matched_key, match_kind = tra_cuu_trend(tag)
        pts = [(d.strftime("%Y-%m-%d"), float(v)) for d, v in s_obj.items()] if s_obj is not None else []
        trend_vals = [float(p[1]) for p in pts[-52:] if len(p) >= 2] if pts else []

        all_sellers: set = set(st["sellers"]) if st else set()
        seen_ext_pids = seen_ext_ids_per_kw.get(tag, set())
        plat_sold = 0
        plat_prices: List[int] = []
        plat_hits = 0
        t_low = tag.lower()
        t_toks = [x for x in t_low.split() if len(x) > 1]
        for pp in platform_prods:
            txt = f"{pp.get('title') or ''} {' '.join(pp.get('tags') or [])}".lower()
            if t_low in txt or (t_toks and sum(1 for x in t_toks if x in txt) / len(t_toks) >= 0.75):
                vc_ext_id = f"vietcraft_{pp.get('pid')}"
                s_key = canonical_seller_key(pp.get("shop_id"), None, "VietCraft")
                if s_key:
                    all_sellers.add(s_key)
                if vc_ext_id in seen_ext_pids:
                    continue
                plat_hits += 1
                plat_sold += int(pp.get("sold_count") or 0)
                pv = int(pp.get("price") or 0)
                if pv > 0:
                    plat_prices.append(pv)

        f42_etsy_fav = 0
        f42_etsy_hits = 0
        f42_prices: List[int] = []
        for ml in f42_listings:
            if str(ml.get("source") or "").lower() != "etsy":
                continue
            ml_id = str(ml.get("_id") or "")
            if ml_id and ml_id in seen_ext_pids:
                continue
            ml_kw = str(ml.get("keyword") or "").strip().lower()
            ml_title = str(ml.get("title") or "").lower()
            if ml_kw == t_low or (len(t_low) >= 4 and t_low in ml_title):
                f42_etsy_hits += 1
                f42_etsy_fav += int(ml.get("review_count") or 0)
                mp = int(ml.get("price") or 0)
                if mp > 0:
                    f42_prices.append(mp)

        n_obs = (st["listing_count"] if st else 0) + plat_hits + f42_etsy_hits
        sold_real = (int(st["sold_sum"]) if st else 0) + plat_sold
        etsy_favorers = (int(st["etsy_favorers"]) if st else 0) + f42_etsy_fav
        etsy_listings = (int(st["etsy_listings"]) if st else 0) + f42_etsy_hits
        sellers_real = len(all_sellers)
        all_prices = (st["prices"] if st else []) + plat_prices + f42_prices
        avg_price = int(round(sum(all_prices) / len(all_prices), -3)) if all_prices else None
        l_type = st["listing_type"] if st else "physical"
        custom = bool(st["customizable"]) if st else False
        plats_in_kw = set(st["platforms"]) if st else set()
        platform_counts: Dict[str, int] = dict(st["platform_counts"]) if st else {}
        if plat_hits > 0:
            plats_in_kw.add("VietCraft")
            platform_counts["VietCraft"] = platform_counts.get("VietCraft", 0) + plat_hits
        if f42_etsy_hits > 0:
            plats_in_kw.add("Etsy")
            platform_counts["Etsy"] = platform_counts.get("Etsy", 0) + f42_etsy_hits
        pod_count = int(st["pod_count"]) if st else 0
        customizable_count = int(st["customizable_count"]) if st else 0

        raw_rows.append(
            {
                "idx": idx,
                "tag": tag,
                "sold_real": sold_real,
                "sellers_real": sellers_real,
                "etsy_favorers": etsy_favorers,
                "etsy_listings": etsy_listings,
                "n_obs": n_obs,
                "avg_price": avg_price,
                "l_type": l_type,
                "custom": custom,
                "platforms": sorted(plats_in_kw),
                "platform_counts": platform_counts,
                "pod_count": pod_count,
                "customizable_count": customizable_count,
                "trend_match": match_kind,
                "matched_key": matched_key if match_kind == "exact" else None,
                "trend_vals": trend_vals if match_kind == "exact" else [],
                "trend_points": pts if match_kind == "exact" else [],
                "plat_hits": plat_hits,
                "has_ext": bool(st),
            }
        )

    # 4. Chấm điểm thống nhất: 50% Sức cầu + 50% Dư địa/Shop
    scored_list = score_opportunity_keywords(raw_rows, as_of=hom_nay)

    opportunity_keywords: List[Dict[str, Any]] = []
    for row, sc in zip(raw_rows, scored_list):
        idx = row["idx"]
        tag = row["tag"]
        sold_real = row["sold_real"]
        sellers_real = row["sellers_real"]
        etsy_favorers = row["etsy_favorers"]
        etsy_listings = row["etsy_listings"]
        n_obs = row["n_obs"]
        match_kind = row["trend_match"]
        matched_key = row["matched_key"]
        score = sc["keyword_score"]
        score_basis = sc["score_basis"]
        effective_demand = sc["effective_demand"]
        sales_per_shop = sc["sales_per_shop"]
        trend_norm = sc["trend_index_norm"]
        trend_raw = sc["trend_index_raw"]
        wow = sc["search_wow_pct"]
        trend_stale_days = sc.get("trend_stale_days")
        is_trend_stale = bool(sc.get("is_trend_stale"))
        breakdown = sc["score_breakdown"]

        has_exact_trend = match_kind == "exact" and trend_norm is not None

        sources: List[str] = []
        if "Tiki" in row["platforms"]:
            sources.append("Tiki (listing hoạt động thu thập ≤ 30 ngày)")
        if "Etsy" in row["platforms"] or etsy_listings > 0:
            sources.append("Etsy Open API v3 (num_favorers, views, tags; lọc tin mới ≤ 180 ngày)")
        if "VietCraft" in row["platforms"] or row["plat_hits"] > 0:
            sources.append(f"VietCraft Live (đơn hoàn tất thật {VC_ORDER_WINDOW_DAYS} ngày gần nhất)")
        if has_exact_trend:
            sources.append("Google Trends Việt Nam (52 tuần đến hiện tại, khớp chính xác)")
        if not sources:
            sources.append("Từ khóa chuẩn ngành hàng theo dịp")

        if n_obs > 0:
            etsy_part = f", {etsy_favorers:,} lượt thích trên Etsy ({etsy_listings} mẫu)" if etsy_favorers > 0 else ""
            stale_part = f" [Cảnh báo: dữ liệu thị trường cũ hơn {EXTERNAL_FRESHNESS_DAYS} ngày]" if ext_data_stale else ""
            how_obtained = (
                f"Tổng hợp & khử trùng từ {n_obs} listing ({sellers_real} shop duy nhất trên "
                f"{', '.join(row['platforms']) or 'đa sàn'}, {sold_real:,} lượt bán{etsy_part}).{stale_part}"
            )
        elif has_exact_trend:
            how_obtained = f"Đo từ chuỗi Google Trends VN 52 tuần khớp chính xác «{matched_key}»; chưa có listing đối soát trong DB."
        else:
            how_obtained = "Chưa có listing bán thật, tín hiệu Etsy hay chuỗi Google Trends khớp chính xác cho từ khóa này."

        if sold_real > 0:
            display_vol = sold_real
            volume_basis = "listing_sales"
            vol_level = "high" if sold_real >= 500 else ("medium" if sold_real >= 100 else "low")
        elif etsy_favorers > 0:
            display_vol = etsy_favorers
            volume_basis = "etsy_engagement"
            vol_level = "high" if etsy_favorers >= 200 else ("medium" if etsy_favorers >= 40 else "low")
        elif has_exact_trend and trend_norm is not None:
            display_vol = int(round(trend_norm))
            volume_basis = "trends_index"
            vol_level = "high" if trend_norm >= 60 else ("medium" if trend_norm >= 30 else "low")
        else:
            display_vol = 0
            volume_basis = "insufficient"
            vol_level = "low"

        display_comp = sellers_real
        comp_level = "low" if display_comp <= 5 else ("medium" if display_comp <= 15 else "high")

        if score is None:
            conf = "preliminary"
        elif sold_real >= 50 and n_obs >= 8 and not ext_data_stale:
            conf = "high"
        elif n_obs >= 3 or etsy_favorers >= 30:
            conf = "fair"
        else:
            conf = "preliminary"

        if has_exact_trend and is_trend_stale:
            trend_note = (
                f"Google Trends khớp «{matched_key}» nhưng dữ liệu mới nhất trễ {trend_stale_days} ngày "
                f"(> {TREND_MAX_STALE_DAYS} ngày) nên không dùng đà 4 tuần vào điểm."
            )
        elif has_exact_trend:
            trend_note = f"Google Trends khớp chính xác «{matched_key}» (chuẩn hóa {trend_norm}/100, gốc {trend_raw})."
        else:
            trend_note = "Chưa có chuỗi Google Trends riêng khớp chính xác (không dùng chuỗi gần đúng/thay thế vào điểm)."

        sps_note = f", bình quân ~{sales_per_shop:g} cầu/shop" if sales_per_shop is not None else ""
        conf_reason = (
            f"Đo từ {n_obs} listing đã khử trùng ({sellers_real} shop duy nhất, sức cầu quy đổi {effective_demand:g}{sps_note}). {trend_note}"
            if n_obs >= 1
            else f"Chưa có listing đối thủ trong DB. {trend_note}"
        )

        caveats = [
            "Quy đổi thống nhất: 1 lượt bán (Tiki/VietCraft) = 1 cầu; 10 lượt thích Etsy = 1 cầu (Etsy API công khai không trả lượt bán từng sản phẩm).",
            "Chưa bao gồm đối thủ ngoài tập listing đã thu thập.",
        ]
        if ext_data_stale:
            caveats.insert(0, f"Dữ liệu listing thị trường cũ hơn {EXTERNAL_FRESHNESS_DAYS} ngày — cần chạy lại bộ thu thập.")
        if is_trend_stale and trend_stale_days is not None:
            caveats.insert(0, f"Chuỗi Google Trends tham khảo trễ {trend_stale_days} ngày so với hôm nay.")

        cov = keyword_shop_coverage(tag, shop_products or [])
        if cov["gap"] and shop_products:
            kw_action = {
                "type": "create_listing",
                "label": "Shop chưa có sản phẩm này — tạo listing",
                "priority": "high" if (score is not None and score >= 60) else "normal",
            }
        elif cov["matching"] > 0:
            kw_action = {"type": "optimize_tags", "label": f"Gắn tag cho {cov['matching']} sản phẩm đã có", "priority": "normal"}
        else:
            kw_action = {"type": "copy_tag", "label": "Sao chép tag", "priority": "normal"}

        platform_counts_row: Dict[str, int] = row.get("platform_counts") or {}
        pod_count_row = int(row.get("pod_count") or 0)
        custom_count_row = int(row.get("customizable_count") or 0)
        source_breakdown = {
            "total_listings": n_obs,
            "pod_count": pod_count_row,
            "pod_pct": round((pod_count_row / n_obs) * 100.0, 1) if n_obs > 0 else 0.0,
            "customizable_count": custom_count_row,
            "customizable_pct": round((custom_count_row / n_obs) * 100.0, 1) if n_obs > 0 else 0.0,
            "by_platform": [
                {
                    "platform": p,
                    "count": c,
                    "pct": round((c / n_obs) * 100.0, 1) if n_obs > 0 else 0.0,
                }
                for p, c in sorted(platform_counts_row.items(), key=lambda x: (-x[1], x[0]))
            ],
        }

        opportunity_keywords.append(
            {
                "id": f"kw_{camp_id}_{idx}",
                "tag": tag,
                "volume": display_vol,
                "sold_count_real": sold_real,
                "etsy_favorers": etsy_favorers,
                "etsy_listings": etsy_listings,
                "effective_demand": effective_demand,
                "sales_per_shop": sales_per_shop,
                "trend_index": trend_norm,
                "trend_index_raw": trend_raw,
                "trend_stale_days": trend_stale_days,
                "volume_level": vol_level,
                "competition": display_comp,
                "competition_level": comp_level,
                "keyword_score": score,
                "score_basis": score_basis,
                "score_breakdown": breakdown,
                "listing_type": row["l_type"],
                "customizable": row["custom"],
                "source_breakdown": source_breakdown,
                "when_made": "2024–2026",
                "avg_price_vnd": row["avg_price"],
                "conversion_rate_pct": None,
                "is_starred": bool(score is not None and score >= 70),
                "search_wow_pct": wow,
                "trend_match": match_kind,
                "trend_series_used": matched_key,
                "volume_basis": volume_basis,
                "platforms": row["platforms"],
                "shop_coverage": cov,
                "action": kw_action,
                "evidence": {
                    "id": f"ev_kw_{camp_id}_{idx}",
                    "definition": f"Điểm cơ hội cho từ khóa '{tag}' (ngành {cat_slug}) theo 1 công thức thống nhất: 50% Sức cầu + 50% Dư địa/Shop.",
                    "sources": sources,
                    "howObtained": how_obtained,
                    "period": [
                        f"Listing ≤ {EXTERNAL_FRESHNESS_DAYS}d · Đơn VC {VC_ORDER_WINDOW_DAYS}d",
                        hom_nay.strftime("%Y-%m-%d"),
                    ],
                    "n": n_obs,
                    "formula": breakdown["formula_text"],
                    "confidence": conf,
                    "confidenceReason": conf_reason,
                    "mayBeWrongBecause": caveats,
                    "updatedAt": hom_nay.strftime("%Y-%m-%d"),
                },
            }
        )

    opportunity_keywords.sort(
        key=lambda x: (
            x["keyword_score"] is not None,
            x["keyword_score"] if x["keyword_score"] is not None else -1,
            x["sold_count_real"],
            x["etsy_favorers"],
        ),
        reverse=True,
    )
    return opportunity_keywords

