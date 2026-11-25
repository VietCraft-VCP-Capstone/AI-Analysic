import logging
import math
from datetime import date, timedelta
from typing import Any, Callable, Dict, List, Optional

from app.api.v1._live import db_live
from app.api.v1._mart import db
from app.core import calendar_vn
from app.core.listing_intel.trend_store import weekly_series
from app.core.redis_cache import cache_get_json, cache_set_json
from app.core.seasonal_dl.forecaster import calibrate_shop_uplift, event_demand_uplift, method_info
from app.core.seasonal_intel import compare_shop_vs_industry_summary
from app.core.seasonal_opportunity import canonical_seller_key, dedupe_external_docs
from app.services.f38.f38_constants import EXTERNAL_FRESHNESS_DAYS, cutoff_utc_dt

log = logging.getLogger("f38_seasonal")


def fmt_trait(key: str, v: Optional[float]) -> str:
    if v is None:
        return "—"
    if key == "lead_days":
        return f"{v:.0f} ngày"
    if key in ("orders_growth", "aov_growth"):
        return f"{v:+.0f}%"
    return f"{v:.0f}%"


def loi_khuyen_trait(key: str, c: Dict[str, Any]) -> str:
    sv, iv = c["shop"]["value"], c["industry"]["value"]
    if c["basis"] == "insufficient":
        return "Chưa đủ đơn ở các dịp trước để đo (cần ≥ 15 đơn trong cửa sổ dịp). Hệ thống sẽ tự cập nhật khi shop có thêm đơn."
    if sv is None:
        if c["basis"] == "model_forecast":
            return f"Chưa có lịch sử đơn của shop. Mô hình dự báo cầu thị trường tăng khoảng {c['model_value']:+.0f}% so với nền."
        return f"Chưa có lịch sử đơn riêng của shop; mặt bằng ngành là {fmt_trait(key, iv)}."
    if iv is None:
        return f"Shop đạt {fmt_trait(key, sv)}; chưa đủ dữ liệu ngành để so sánh."
    hi = (sv - iv) > 0
    tpl = {
        "orders_growth": (
            "Đơn dịp của shop tăng mạnh hơn ngành — đảm bảo tồn kho và nhân lực đóng gói.",
            "Shop tăng chậm hơn ngành — còn dư địa: đăng sớm, gắn tag dịp, chạy voucher đầu mùa.",
        ),
        "aov_growth": (
            "Giá trị đơn tăng tốt hơn ngành — tiếp tục bán combo/quà đóng hộp.",
            "Giá trị đơn tăng kém ngành — thêm combo, bán kèm để nâng giỏ.",
        ),
        "lead_days": (
            "Khách của shop đặt sớm hơn ngành — chốt tồn và mốc giao sớm hơn.",
            "Khách của shop đặt sát ngày hơn ngành — ưu tiên giao nhanh và nhắc đặt sớm.",
        ),
        "peak_clump": (
            "Đơn dồn vào vài ngày hơn ngành — chuẩn bị năng lực xử lý đỉnh.",
            "Đơn của shop trải đều hơn ngành — ít rủi ro nghẽn đỉnh.",
        ),
        "combo_pct": (
            "Tỷ lệ mua combo cao hơn ngành — giữ chiến lược set quà.",
            "Tỷ lệ mua combo thấp hơn ngành — thử bundle 2–3 món.",
        ),
        "voucher_pct": (
            "Khách shop dùng voucher nhiều hơn ngành — cân nhắc lợi nhuận sau giảm giá.",
            "Khách shop dùng voucher ít hơn ngành — voucher có thể chưa là đòn bẩy.",
        ),
    }[key]
    return f"Shop {fmt_trait(key, sv)} vs ngành {fmt_trait(key, iv)}. " + (tpl[0] if hi else tpl[1])


def ap_dung_so_sanh(
    t: Dict[str, Any],
    c: Dict[str, Any],
    meta: Dict[str, Any],
    today: date,
    plat_fallback: Optional[float] = None,
    shop_recent: Optional[float] = None,
    shop_recent_n: int = 0,
    industry_scale: Optional[Dict[str, Any]] = None,
) -> None:
    """Ghi đè một trait bằng số đo thật (shop vs toàn ngành đa sàn)."""
    key = {
        "ordersGrowth": "orders_growth",
        "higherSpending": "aov_growth",
        "earlyOrder": "lead_days",
        "peakClustering": "peak_clump",
        "comboPurchase": "combo_pct",
        "voucherSensitivity": "voucher_pct",
    }[t["key"]]
    sv, iv = c["shop"]["value"], c["industry"]["value"]
    used_plat_fallback = False
    used_shop_recent = False
    if iv is None and plat_fallback is not None:
        iv = round(float(plat_fallback), 1)
        used_plat_fallback = True
    if sv is None and shop_recent is not None:
        sv = round(float(shop_recent), 1)
        used_shop_recent = True

    t["shopValue"] = sv
    t["industryValue"] = iv
    t["baselineValue"] = iv
    t["occasionValue"] = sv if sv is not None else c.get("model_value")

    max_scale = {
        "orders_growth": 100.0,
        "aov_growth": 60.0,
        "lead_days": 30.0,
        "peak_clump": 80.0,
        "combo_pct": 80.0,
        "voucher_pct": 85.0,
    }.get(key, 100.0)
    t["industryScore"] = round(max(0.0, min(100.0, (abs(float(iv)) / max_scale) * 100.0))) if iv is not None else 0
    t["shopScore"] = round(max(0.0, min(100.0, (abs(float(sv)) / max_scale) * 100.0))) if sv is not None else 0
    t["percentileRank"] = c["shop_percentile"] if c["shop_percentile"] is not None else None

    t["comparison_basis"] = (
        c["basis"]
        if not (used_plat_fallback or used_shop_recent)
        else ("shop_recent_vs_platform" if used_shop_recent else "platform_benchmark")
    )
    t["comparison"] = c
    t["valueUnit"] = {"lead_days": "ngày"}.get(key, "%")
    if sv is not None and iv is not None:
        diff_val = round(sv - iv, 1)
        sign = "+" if diff_val > 0 else ""
        t["diffText"] = f"{sign}{diff_val:g}{t['valueUnit']} vs toàn ngành"
    elif iv is not None:
        if key in ("orders_growth", "aov_growth"):
            t["diffText"] = f"{fmt_trait(key, iv)} so với ngày thường"
        else:
            t["diffText"] = f"Toàn ngành {fmt_trait(key, iv)}"
    elif c["basis"] == "model_forecast":
        t["diffText"] = f"Dự báo {c['model_value']:+.0f}%"
    else:
        t["diffText"] = "Chưa đủ dữ liệu"

    t["confidence"] = (
        "high"
        if (c["basis"] == "measured_shop" and c["shop"]["cycles"] >= 2 and c["shop"]["n"] >= 60)
        else ("fair" if (sv is not None and iv is not None) else "preliminary")
    )
    if sv is not None and iv is not None and (used_shop_recent or used_plat_fallback):
        c_tmp = {"basis": "measured_shop", "shop": {"value": sv}, "industry": {"value": iv}}
        t["actionableAdvice"] = loi_khuyen_trait(key, c_tmp)
    else:
        t["actionableAdvice"] = loi_khuyen_trait(key, c)

    ev = t.get("evidence") or {}
    ev.pop("interval", None)
    n_used = (
        (shop_recent_n if used_shop_recent else c["shop"]["n"])
        if sv is not None
        else (c["industry"]["n_orders"] if iv is not None else 0)
    )
    plats_used = (industry_scale or {}).get("platforms") or ["Tiki", "Etsy", "Printify", "VietCraft"]
    plats_str = ", ".join(plats_used)
    etsy_fav_note = (
        f", {int(industry_scale['etsyFavorersTotal']):,} lượt yêu thích Etsy"
        if industry_scale and int(industry_scale.get("etsyFavorersTotal") or 0) > 0
        else ""
    )
    scale_desc = (
        f"{industry_scale['productsCount']:,} sản phẩm từ {industry_scale['sellersCount']:,} gian hàng "
        f"({plats_str}, {industry_scale['totalSold']:,} lượt bán{etsy_fav_note})"
        if industry_scale and industry_scale.get("productsCount")
        else "dữ liệu toàn ngành TMĐT & Google Trends VN"
    )
    ev.update(
        {
            "n": max(n_used, int((industry_scale or {}).get("productsCount") or 0)),
            "sources": [*plats_used, "Google Trends VN 5 năm"],
            "confidence": t["confidence"],
            "howObtained": (
                f"Shop: đo từ {shop_recent_n} đơn thực tế gần nhất; Toàn ngành: tổng hợp từ {scale_desc}."
                if used_shop_recent
                else f"Tổng hợp từ {scale_desc}."
            ),
            "formula": f"Shop {fmt_trait(key, sv)} · Toàn ngành {fmt_trait(key, iv)}",
            "confidenceReason": (
                "Đo trực tiếp từ đơn hoàn tất cùng kỳ."
                if c["basis"] == "measured_shop"
                else (
                    f"Đo từ đơn thực tế của shop đối chiếu với mẫu toàn ngành đa sàn ({plats_str})."
                    if used_shop_recent
                    else f"Tổng hợp từ dữ liệu đa sàn TMĐT ({plats_str}) và mô hình Google Trends STL 5 năm."
                )
            ),
            "comparison": f"So với mặt bằng toàn ngành ({fmt_trait(key, iv)}).",
            "modelVersion": "seasonal_intel.compare_shop_vs_industry v4",
            "updatedAt": today.isoformat(),
        }
    )
    t["industryScale"] = industry_scale
    t["evidence"] = ev


def compute_industry_scale(cat_slug: str, active_camp: Dict[str, Any], hom_nay: date) -> Dict[str, Any]:
    """Tổng hợp chỉ số & độ lớn toàn ngành từ dữ liệu đa sàn TMĐT (lọc độ tươi <= 30 ngày)."""
    fresh_since_dt = cutoff_utc_dt(hom_nay, EXTERNAL_FRESHNESS_DAYS)
    ind_scale_key = f"seasonal:ind_scale:{cat_slug or 'all'}:{active_camp['id']}:{hom_nay.isoformat()}:v4"
    ind_scale = cache_get_json(ind_scale_key)
    if isinstance(ind_scale, dict) and ind_scale.get("productsCount"):
        return ind_scale

    try:
        ext_q: Dict[str, Any] = {"is_active": True}
        if cat_slug and cat_slug != "tong-hop":
            ext_q["category_slug"] = cat_slug
        scale_proj = {
            "_id": 0,
            "external_id": 1,
            "occasion_id": 1,
            "title": 1,
            "price_vnd": 1,
            "original_price_vnd": 1,
            "sold_count": 1,
            "num_favorers": 1,
            "customizable": 1,
            "seller_name": 1,
            "seller_id": 1,
            "platform": 1,
            "collected_at": 1,
        }
        scale_is_stale = False
        raw_ext_rows = list(db()["external_market_products"].find({**ext_q, "collected_at": {"$gte": fresh_since_dt}}, scale_proj))
        if len(raw_ext_rows) < 20:
            raw_ext_rows = list(
                db()["external_market_products"].find({"is_active": True, "collected_at": {"$gte": fresh_since_dt}}, scale_proj)
            )
        if not raw_ext_rows:
            scale_is_stale = True
            raw_ext_rows = list(db()["external_market_products"].find(ext_q, scale_proj))
            if len(raw_ext_rows) < 20:
                raw_ext_rows = list(db()["external_market_products"].find({"is_active": True}, scale_proj))

        ext_rows = dedupe_external_docs(raw_ext_rows, target_occasion_id=active_camp["id"])
        n_ext = len(ext_rows)
        ext_seller_keys = {
            canonical_seller_key(x.get("seller_id"), x.get("seller_name"), x.get("platform"))
            for x in ext_rows
            if x.get("seller_id") or x.get("seller_name")
        }
        ext_seller_keys.discard(None)
        ext_sellers = len(ext_seller_keys)
        ext_sold = sum(int(x.get("sold_count") or 0) for x in ext_rows)
        etsy_rows = [x for x in ext_rows if str(x.get("platform") or "").lower() == "etsy"]
        etsy_fav_total = sum(int(x.get("num_favorers") or 0) for x in etsy_rows)
        ext_plats = sorted({str(x.get("platform")) for x in ext_rows if x.get("platform")}) or [
            "Tiki",
            "Etsy",
            "Printify",
            "VietCraft",
        ]

        occ_rows = [x for x in ext_rows if str(x.get("occasion_id") or "").lower() == str(active_camp["id"]).lower()]
        meas_rows = occ_rows if len(occ_rows) >= 6 else ext_rows
        n_meas = len(meas_rows)
        combo_tokens = (
            "combo",
            "set ",
            "bộ ",
            "đôi",
            "túi quà",
            "hộp quà",
            "gift box",
            "gift set",
            "bundle",
            "matching",
            "couple",
            "pack",
        )
        combo_hits = sum(1 for x in meas_rows if any(kw in (x.get("title") or "").lower() for kw in combo_tokens))
        custom_hits = sum(
            1
            for x in meas_rows
            if x.get("customizable")
            or any(kw in (x.get("title") or "").lower() for kw in ("custom", "personalized", "khắc tên", "in tên"))
        )
        disc_eligible = [x for x in meas_rows if str(x.get("platform") or "").lower() != "etsy"] or meas_rows
        disc_rows = [x for x in disc_eligible if int(x.get("original_price_vnd") or 0) > int(x.get("price_vnd") or 0) > 0]
        ext_combo_pct = round((combo_hits / max(1, n_meas)) * 100.0, 1)
        ext_custom_pct = round((custom_hits / max(1, n_meas)) * 100.0, 1)
        ext_disc_pct = round((len(disc_rows) / max(1, len(disc_eligible))) * 100.0, 1)

        all_prices = [int(x.get("price_vnd") or 0) for x in ext_rows if int(x.get("price_vnd") or 0) > 0]
        occ_prices = [int(x.get("price_vnd") or 0) for x in occ_rows if int(x.get("price_vnd") or 0) > 0]
        occ_aov_premium = None
        if len(occ_prices) >= 6 and all_prices:
            avg_all_p = sum(all_prices) / len(all_prices)
            avg_occ_p = sum(occ_prices) / len(occ_prices)
            raw_prem = ((avg_occ_p - avg_all_p) / max(1.0, avg_all_p)) * 100.0
            if raw_prem > 3:
                occ_aov_premium = round(max(8.0, min(60.0, raw_prem)), 1)

        ind_scale = {
            "productsCount": n_ext,
            "sellersCount": ext_sellers,
            "totalSold": ext_sold,
            "etsyProductsCount": len(etsy_rows),
            "etsyFavorersTotal": etsy_fav_total,
            "platforms": ext_plats,
            "occasionProductsCount": len(occ_rows),
            "extComboPct": ext_combo_pct,
            "extCustomPct": ext_custom_pct,
            "extDiscPct": ext_disc_pct,
            "occAovPremium": occ_aov_premium,
            "isStale": scale_is_stale,
        }
        cache_set_json(ind_scale_key, ind_scale, ttl_seconds=1800)
        return ind_scale
    except Exception as exc:
        log.warning("seasonal: %s: %s", type(exc).__name__, exc)
        return {
            "productsCount": 0,
            "sellersCount": 0,
            "totalSold": 0,
            "etsyProductsCount": 0,
            "etsyFavorersTotal": 0,
            "platforms": ["Tiki", "Etsy", "Printify", "VietCraft"],
        }


def build_occasion_traits(
    *,
    shop_id: str,
    cat_slug: str,
    active_camp: Dict[str, Any],
    ev_info: Dict[str, Any],
    target_ev_d: date,
    hom_nay: date,
    primary_kw: str,
    stl: Dict[str, Any],
    all_competitors: List[Dict[str, Any]],
    shop_orders_hist: List[Dict[str, Any]],
    ind_summary: Dict[str, Any],
    past_ev: Dict[int, date],
    ind_win_days: int,
    compute_rates_fn: Callable[[str, Optional[str], str], Dict[str, Any]],
) -> Dict[str, Any]:
    """Xây dựng 6 Trục Đặc Điểm Mua Sắm Của Dịp, radar biểu đồ và so sánh shop vs toàn ngành."""
    method_meta = method_info()
    uplift_res = None
    all_series_map = weekly_series()
    target_s = None
    if primary_kw in all_series_map:
        target_s = all_series_map[primary_kw]
    else:
        for k, s_candidate in all_series_map.items():
            if primary_kw.lower() in k.lower() or k.lower() in primary_kw.lower():
                target_s = s_candidate
                break
        if target_s is None and "quà tặng" in all_series_map:
            target_s = all_series_map["quà tặng"]
        elif target_s is None and len(all_series_map) > 0:
            target_s = next(iter(all_series_map.values()))

    event_dates_by_year: Dict[int, date] = {}
    for yr in range(2021, hom_nay.year + 2):
        temp_win = calendar_vn.calculate_occasion_window(ev_info, date(yr, 6, 1))
        if temp_win and temp_win.get("event_date"):
            event_dates_by_year[yr] = date.fromisoformat(temp_win["event_date"])

    if target_s is not None:
        try:
            uplift_res = event_demand_uplift(
                series=target_s,
                event_dates=event_dates_by_year,
                event_date=target_ev_d,
                window_days=30,
                today=hom_nay,
            )
            if uplift_res:
                try:
                    shop_wk_map = cache_get_json("seasonal:plat_orders_wk_map:v2")
                    if not isinstance(shop_wk_map, dict):
                        shop_wk_map = {}
                        for o in (
                            db_live()["orders"]
                            .find(
                                {"is_simulated": {"$ne": True}, "seed_ref": {"$exists": False}},
                                {"created_at": 1},
                            )
                            .limit(1500)
                        ):
                            ca = o.get("created_at")
                            if hasattr(ca, "isocalendar"):
                                y_wk = f"{ca.isocalendar()[0]}-W{ca.isocalendar()[1]:02d}"
                                shop_wk_map[y_wk] = shop_wk_map.get(y_wk, 0) + 1
                        cache_set_json("seasonal:plat_orders_wk_map:v2", shop_wk_map, ttl_seconds=1800)
                    if len(shop_wk_map) >= 12:
                        sorted_wks = sorted(shop_wk_map.keys())[-26:]
                        shop_vals = [float(shop_wk_map[k]) for k in sorted_wks]
                        trend_tail = [float(v) for v in target_s.values[-len(shop_vals) :]]
                        uplift_res = calibrate_shop_uplift(uplift_res, shop_vals, trend_tail)
                except Exception as exc:
                    log.warning("seasonal: %s: %s", type(exc).__name__, exc)
        except Exception as exc:
            log.warning("seasonal: %s: %s", type(exc).__name__, exc)
            uplift_res = None

    if uplift_res and uplift_res.get("uplift_p50"):
        p50_up = float(uplift_res["uplift_p50"])
        orders_growth_pct = round((p50_up - 1.0) * 100)
    elif stl.get("seasonal"):
        peak_seasonal = max(stl["seasonal"])
        avg_seasonal = sum(stl["seasonal"]) / max(1, len(stl["seasonal"]))
        orders_growth_pct = max(18, min(85, round(((peak_seasonal - avg_seasonal) / max(1.0, avg_seasonal)) * 100)))
    else:
        orders_growth_pct = round(stl.get("amplitude", 0.35) * 100)

    competitor_prices = [p.get("price_vnd", 0) for p in all_competitors if p.get("price_vnd")]
    avg_cat_price = int(sum(competitor_prices) / len(competitor_prices)) if competitor_prices else 0
    baseline_spending = avg_cat_price if avg_cat_price > 0 else 200000
    spending_growth_pct: int = 0
    occasion_spending = baseline_spending

    start_d = date.fromisoformat(active_camp["launch_window"]["start"]) if active_camp.get("launch_window") else hom_nay
    peak_d = (
        date.fromisoformat(active_camp["launch_window"]["peak_date"])
        if active_camp.get("launch_window")
        else hom_nay + timedelta(days=30)
    )
    lead_time_days = max(7, (peak_d - start_d).days)
    early_order_days: Optional[int] = None

    peak_clump_pct: Optional[float] = None
    if target_s is not None and event_dates_by_year:
        try:
            ratios = []
            for _yr, _evd in event_dates_by_year.items():
                if _evd >= hom_nay:
                    continue
                ws_t = _evd - timedelta(days=28)
                we_t = _evd + timedelta(days=7)
                win_vals = [float(v) for dt, v in target_s.items() if ws_t <= dt.date() <= we_t]
                if len(win_vals) >= 4 and sum(win_vals) > 0:
                    ratios.append(max(win_vals) / sum(win_vals))
            if ratios:
                avg_wk_share = sum(ratios) / len(ratios)
                peak_clump_pct = round(avg_wk_share * 100.0, 1)
        except Exception as exc:
            log.warning("peak_clump_pct calculation failed: %s", exc)
            peak_clump_pct = None

    order_rates = compute_rates_fn(shop_id, cat_slug, active_camp["id"])
    combo_pct: Optional[float] = order_rates.get("raw_combo_rate")
    voucher_pct: Optional[float] = order_rates.get("raw_voucher_rate")

    period_1y = [(hom_nay - timedelta(days=365)).strftime("%Y-%m-%d"), hom_nay.strftime("%Y-%m-%d")]
    occasion_traits = [
        {
            "key": "ordersGrowth",
            "name": "Đơn hàng mỗi ngày cao điểm",
            "question": "Số đơn mỗi ngày cao điểm tăng bao nhiêu so với ngày thường?",
            "baselineValue": None,
            "occasionValue": None,
            "diffText": "Chưa đủ dữ liệu",
            "unit": "%",
            "percentileRank": None,
            "confidence": "preliminary",
            "actionableAdvice": "Chưa đủ dữ liệu đơn hàng lịch sử để kết luận mức tăng trưởng.",
            "evidence": {
                "id": "ev_orders_growth",
                "definition": "Tỷ lệ tăng trưởng số đơn hàng trung bình mỗi ngày trong dịp so với 8 tuần ngày thường trước đó.",
                "excluded": "Đã loại trừ đơn hàng bị hủy, trả hàng, giao không thành công.",
                "period": period_1y,
                "mayBeWrongBecause": [
                    "Nhu cầu thị trường chung có thể sụt giảm do yếu tố vĩ mô bất ngờ.",
                    "Sản phẩm mới đăng chưa kịp tích lũy đánh giá và thứ hạng tìm kiếm trên sàn.",
                ],
                "rawDataUrl": "",
            },
        },
        {
            "key": "higherSpending",
            "name": "Giá trị mỗi đơn",
            "question": "Giá trị trung bình mỗi đơn tăng bao nhiêu so với ngày thường?",
            "baselineValue": None,
            "occasionValue": None,
            "diffText": "Chưa đủ dữ liệu",
            "unit": "%",
            "percentileRank": None,
            "confidence": "preliminary",
            "actionableAdvice": "Chưa đủ dữ liệu hóa đơn để so sánh giá trị đơn hàng.",
            "evidence": {
                "id": "ev_higher_spending",
                "definition": "Mức chênh lệch giá trị đơn hàng trung bình (AOV) sau giảm giá trong dịp so với ngày thường.",
                "excluded": "Bỏ các đơn hàng quà tặng nội bộ sàn hoặc đơn thử nghiệm.",
                "period": period_1y,
                "mayBeWrongBecause": ["Seller áp dụng giảm giá quá sâu làm giảm giá trị đơn trung bình."],
            },
        },
        {
            "key": "earlyOrder",
            "name": "Khách đặt trước sự kiện",
            "question": "Khách thường đặt trước ngày sự kiện bao nhiêu ngày?",
            "baselineValue": None,
            "occasionValue": None,
            "diffText": "Chưa đủ dữ liệu",
            "unit": "ngày",
            "percentileRank": None,
            "confidence": "preliminary",
            "actionableAdvice": "Chưa đủ dữ liệu đơn hàng cùng kỳ để đo số ngày đặt sớm.",
            "evidence": {
                "id": "ev_early_order",
                "definition": "Số ngày phổ biến từ lúc khách đặt mua đến ngày diễn ra dịp lễ (trung vị thời gian đặt hàng).",
                "excluded": "Bỏ đơn đặt sau ngày lễ kết thúc.",
                "period": period_1y,
                "mayBeWrongBecause": ["Đơn vị vận chuyển có chương trình siêu tốc giao trong 24h làm thay đổi thói quen đặt sớm."],
            },
        },
        {
            "key": "peakClustering",
            "name": "Đơn rơi vào 3 ngày cao điểm",
            "question": "Tỷ lệ đơn tập trung vào 3 ngày cao điểm nhất?",
            "baselineValue": None,
            "occasionValue": None,
            "diffText": "Chưa đủ dữ liệu",
            "unit": "%",
            "percentileRank": None,
            "confidence": "preliminary",
            "actionableAdvice": "Chưa đủ dữ liệu đơn hàng cùng kỳ để đo độ tập trung 3 ngày đỉnh.",
            "evidence": {
                "id": "ev_peak_clustering",
                "definition": "Mức độ tập trung đơn hàng: Tỷ lệ tổng số đơn hàng rơi vào 3 ngày cao điểm nhất của dịp.",
                "excluded": "Không.",
                "period": period_1y,
                "mayBeWrongBecause": ["Shop bị nghẽn vận hành hoặc hết bao bì đóng gói vào ngày đỉnh."],
            },
        },
        {
            "key": "comboPurchase",
            "name": "Đơn mua theo bộ (combo)",
            "question": "Tỷ lệ đơn mua từ 2 món trở lên hoặc theo set?",
            "baselineValue": None,
            "occasionValue": None,
            "diffText": "Chưa đủ dữ liệu",
            "unit": "%",
            "percentileRank": None,
            "confidence": "preliminary",
            "actionableAdvice": "Chưa đủ dữ liệu giỏ hàng để đo tỷ lệ mua combo.",
            "evidence": {
                "id": "ev_combo_purchase",
                "definition": "Tỷ lệ đơn hàng có từ 2 sản phẩm trở lên hoặc khách mua theo set/combo trong cùng một lần thanh toán.",
                "excluded": "Bỏ các đơn hủy trước khi giao.",
                "period": period_1y,
                "mayBeWrongBecause": ["Shop chỉ bán một sản phẩm đơn lẻ không có lựa chọn mua kèm combo."],
            },
        },
        {
            "key": "voucherSensitivity",
            "name": "Đơn có dùng mã giảm giá",
            "question": "Tỷ lệ đơn có áp dụng mã giảm giá?",
            "baselineValue": None,
            "occasionValue": None,
            "diffText": "Chưa đủ dữ liệu",
            "unit": "%",
            "percentileRank": None,
            "confidence": "preliminary",
            "actionableAdvice": "Chưa đủ dữ liệu đơn hàng để đo tỷ lệ dùng mã giảm giá.",
            "evidence": {
                "id": "ev_voucher_sensitivity",
                "definition": "Tỷ lệ đơn hàng người mua áp dụng voucher sàn hoặc voucher giảm giá riêng của shop.",
                "excluded": "Đơn không áp mã giảm giá.",
                "period": period_1y,
                "mayBeWrongBecause": ["Shop không tạo mã giảm giá khiến khách rời đi mua của đối thủ."],
            },
        },
    ]

    traits_cmp = compare_shop_vs_industry_summary(
        shop_orders_hist,
        ind_summary,
        past_ev,
        ind_win_days,
        hom_nay,
        model_uplift_pct=float(orders_growth_pct) if uplift_res else None,
        model_label=method_meta.get("method", ""),
    )
    key_to_cmp = {
        "ordersGrowth": "orders_growth",
        "higherSpending": "aov_growth",
        "earlyOrder": "lead_days",
        "peakClustering": "peak_clump",
        "comboPurchase": "combo_pct",
        "voucherSensitivity": "voucher_pct",
    }

    done_shop_orders = [
        o for o in shop_orders_hist if str(o.get("order_status") or "").upper() in ("DELIVERED", "COMPLETED", "PAID", "")
    ] or shop_orders_hist
    shop_recent_n = len(done_shop_orders)
    shop_recent_map: Dict[str, Optional[float]] = {}
    if shop_recent_n >= 3:
        s_combo = sum(1 for o in done_shop_orders if len(o.get("items") or []) >= 2)
        s_voucher = sum(1 for o in done_shop_orders if o.get("coupon_code"))
        s_by_day: Dict[str, int] = {}
        s_amts: List[float] = []
        for o in done_shop_orders:
            ca = o.get("created_at")
            if hasattr(ca, "strftime"):
                dk = ca.strftime("%Y-%m-%d")
                s_by_day[dk] = s_by_day.get(dk, 0) + 1
            amt = float(o.get("order_amount") or 0)
            if amt > 0:
                s_amts.append(amt)
        top3_days = sum(sorted(s_by_day.values(), reverse=True)[:3])
        s_aov = sum(s_amts) / len(s_amts) if s_amts else 0.0
        shop_recent_map = {
            "comboPurchase": round((s_combo / shop_recent_n) * 100.0, 1),
            "voucherSensitivity": round((s_voucher / shop_recent_n) * 100.0, 1),
            "peakClustering": round((top3_days / shop_recent_n) * 100.0, 1) if s_by_day else None,
            "higherSpending": round(((s_aov - baseline_spending) / max(1.0, float(baseline_spending))) * 100.0, 1)
            if s_aov > 0
            else None,
        }

    ind_scale = compute_industry_scale(cat_slug, active_camp, hom_nay)
    measured_lead_ind = (traits_cmp.get("lead_days") or {}).get("industry", {}).get("value")
    if measured_lead_ind is not None:
        early_order_days = int(round(float(measured_lead_ind)))

    measured_aov_ind = (traits_cmp.get("aov_growth") or {}).get("industry", {}).get("value")
    if measured_aov_ind is not None:
        spending_growth_pct = int(round(float(measured_aov_ind)))
    elif ind_scale.get("occAovPremium") is not None:
        spending_growth_pct = int(round(float(ind_scale["occAovPremium"])))
    occasion_spending = int(baseline_spending * (1 + spending_growth_pct / 100))

    # Ưu tiên số đo thật từ đơn VietCraft (>= 10 đơn); chỉ dùng tỷ lệ từ listing đa sàn khi chưa đủ đơn thật
    ind_combo_blend: Optional[float] = (
        float(combo_pct)
        if combo_pct is not None
        else (
            float(ind_scale["extComboPct"])
            if ind_scale.get("productsCount") and ind_scale.get("extComboPct") is not None
            else None
        )
    )
    ind_voucher_blend: Optional[float] = (
        float(voucher_pct)
        if voucher_pct is not None
        else (
            float(ind_scale["extDiscPct"])
            if ind_scale.get("productsCount") and ind_scale.get("extDiscPct") is not None
            else None
        )
    )

    plat_fallback_map: Dict[str, Optional[float]] = {
        "ordersGrowth": float(orders_growth_pct) if uplift_res else None,
        "higherSpending": float(ind_scale["occAovPremium"]) if ind_scale.get("occAovPremium") is not None else None,
        "earlyOrder": None,
        "peakClustering": float(peak_clump_pct) if peak_clump_pct is not None else None,
        "comboPurchase": ind_combo_blend,
        "voucherSensitivity": ind_voucher_blend,
    }

    for trait in occasion_traits:
        ap_dung_so_sanh(
            trait,
            traits_cmp[key_to_cmp[trait["key"]]],
            traits_cmp["_meta"],
            hom_nay,
            plat_fallback=plat_fallback_map.get(trait["key"]),
            shop_recent=shop_recent_map.get(trait["key"]),
            shop_recent_n=shop_recent_n,
            industry_scale=ind_scale,
        )

    campaign_radar = {
        "axes": [t["name"] for t in occasion_traits[:5]],
        "current_values": [(t["percentileRank"] or 0) for t in occasion_traits[:5]],
        "benchmark_values": [50, 50, 50, 50, 50],
        "overall_score": (
            round(
                sum(t["percentileRank"] for t in occasion_traits if t["percentileRank"] is not None)
                / max(1, sum(1 for t in occasion_traits if t["percentileRank"] is not None))
            )
            if any(t["percentileRank"] is not None for t in occasion_traits)
            else None
        ),
        "takeaways": [t["actionableAdvice"] for t in occasion_traits[:3]],
        "data_provenance": [
            {
                "axis": t["name"],
                "score": t["percentileRank"] or 0,
                "benchmark": 50,
                "source": t["evidence"]["sources"][0],
                "evidence": t["evidence"]["definition"],
                "formula": t["evidence"]["formula"],
            }
            for t in occasion_traits
        ],
    }

    return {
        "occasion_traits": occasion_traits,
        "traits_cmp": traits_cmp,
        "ind_scale": ind_scale,
        "method_meta": method_meta,
        "uplift_res": uplift_res,
        "orders_growth_pct": orders_growth_pct,
        "spending_growth_pct": spending_growth_pct,
        "baseline_spending": baseline_spending,
        "occasion_spending": occasion_spending,
        "lead_time_days": lead_time_days,
        "early_order_days": early_order_days,
        "peak_clump_pct": peak_clump_pct,
        "ind_combo_blend": ind_combo_blend,
        "ind_voucher_blend": ind_voucher_blend,
        "campaign_radar": campaign_radar,
    }

