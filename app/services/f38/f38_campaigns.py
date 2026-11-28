import logging
from datetime import date, datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.core import calendar_vn
from app.core.seasonal_uplift import expected_orders_range, order_uplift_from_history
from app.core.redis_cache import cache_get_json, cache_set_json
from app.core.seasonal_intel import _dt as _si_dt
from app.services.f38.f38_constants import CAT_LABELS, CAT_OCCASION_KEYWORDS

log = logging.getLogger("f38_seasonal")


def tao_khuyen_nghi_hanh_dong(ev: dict, win: dict, hom_nay: date, cat_slug: str) -> dict:
    """Tạo khuyến nghị hành động thực tế, ngắn gọn và riêng biệt cho từng dịp."""
    ev_d = date.fromisoformat(win["event_date"])
    cut_off_d = date.fromisoformat(win["cut_off_date"])
    peak_d = date.fromisoformat(win["peak_start"])
    traction_d = date.fromisoformat(win["traction_start"])
    rd_d = date.fromisoformat(win["rd_start"])

    days_to_cutoff = win["days_to_cut_off"]
    ev_name = ev["name"]
    ev_key = ev.get("key", "").lower()

    kw = (
        CAT_OCCASION_KEYWORDS.get(cat_slug, {}).get(ev_key)
        or (ev.get("default_search_keywords") or ["sản phẩm quà tặng"])[0]
    )

    trac_str = traction_d.strftime("%d/%m")
    cut_str = cut_off_d.strftime("%d/%m")
    ev_str = ev_d.strftime("%d/%m")

    occasion_profiles = {
        "12/12": {
            "prep_title": "Lên combo & Sẵn hàng Siêu Sale 12/12",
            "prep_advice": f'Chuẩn bị sẵn hàng "{kw}", thiết lập mã ưu đãi và combo mua kèm trước ngày mở bán ({trac_str}).',
            "traction_title": f'Bật Flash Sale & Đẩy từ khóa "{kw}"',
            "traction_advice": "Nhu cầu tăng tốc. Đăng ký sản phẩm vào sự kiện sàn và gắn đủ 5 thẻ tag ngách trước cao điểm.",
        },
        "noel": {
            "prep_title": "Lên mẫu BST Giáng Sinh & Quà tặng",
            "prep_advice": f'Hoàn thiện mẫu chủ đạo "{kw}", chụp ảnh concept Noel ấm áp trước ngày mở bán ({trac_str}).',
            "traction_title": f'Đẩy mạnh hiển thị nhóm "{kw}"',
            "traction_advice": "Khách tìm mua quà tặng sớm. Hoàn thiện ảnh thật và chạy chương trình quà tặng kèm.",
        },
        "tet": {
            "prep_title": "Đón sức mua lớn nhất năm — Tết Nguyên Đán",
            "prep_advice": f'Chốt mẫu "{kw}", chuẩn bị sẵn hộp quà sang trọng & thiệp mừng trước ngày mở bán ({trac_str}).',
            "traction_title": "Mở bán sớm & Gom đơn Tết",
            "traction_advice": f'Nhu cầu sắm Tết bắt đầu tăng. Lên bài sớm để sàn kịp index từ khóa "{kw}".',
        },
        "valentine": {
            "prep_title": "Chuẩn bị set quà đôi Valentine",
            "prep_advice": f'Lên mẫu cặp đôi/khắc tên theo nhóm "{kw}", hoàn thiện ảnh mẫu trước ngày ({trac_str}).',
            "traction_title": f'Đẩy từ khóa quà tặng tình nhân "{kw}"',
            "traction_advice": "Tối ưu hộp quà & dịch vụ viết thiệp tay để tăng tỷ lệ chốt đơn dịp Valentine.",
        },
        "8/3": {
            "prep_title": "Chuẩn bị set quà tặng phái đẹp 8/3",
            "prep_advice": f'Thiết kế set quà tri ân "{kw}", đóng gói sẵn hộp quà đẹp mắt trước ngày ({trac_str}).',
            "traction_title": "Đón sóng quà tặng doanh nghiệp & cá nhân 8/3",
            "traction_advice": f'Tạo gói combo quà tặng kèm ưu đãi mua nhiều món và gắn tag ngách "{kw}" để kéo khách vào shop.',
        },
        "20/10": {
            "prep_title": "Chuẩn bị quà tặng 20/10",
            "prep_advice": f'Lên mẫu quà tặng hoa & thiệp nhóm "{kw}", chuẩn bị sẵn bao bì trước ngày ({trac_str}).',
            "traction_title": "Đẩy mạnh hiển thị quà tặng 20/10",
            "traction_advice": "Nhu cầu tăng mạnh. Hoàn thiện ảnh concept và sẵn sàng giao hỏa tốc.",
        },
        "20/11": {
            "prep_title": "Chuẩn bị quà tri ân thầy cô 20/11",
            "prep_advice": f'Lên mẫu mang thông điệp tri ân "{kw}", chuẩn bị hộp quà trang trọng trước ngày ({trac_str}).',
            "traction_title": "Đón sức mua quà tặng tri ân 20/11",
            "traction_advice": "Gắn tag từ khóa quà tặng thầy cô và đẩy mạnh ưu đãi combo mua nhiều món.",
        },
    }

    prof = occasion_profiles.get(
        ev_key,
        {
            "prep_title": f"Chuẩn bị sản phẩm đón {ev_name}",
            "prep_advice": f'Chuẩn bị nguồn hàng nhóm "{kw}", sẵn sàng mở bán trước ngày ({trac_str}).',
            "traction_title": f'Tối ưu hiển thị từ khóa "{kw}"',
            "traction_advice": f'Nhu cầu tìm kiếm tăng tốc. Hoàn thiện ảnh thật và gắn từ khóa "{kw}" để đón đơn sớm.',
        },
    )

    lead_days = int(win.get("lead_time_days") or ev.get("lead_time_days") or 14)
    cutoff_basis = f"Hạn chốt {cut_str} = Ngày lễ ({ev_str}) − {lead_days} ngày (thời gian làm hàng và giao hàng)."
    phase = win.get("current_phase")

    if phase == "post_event":
        return {
            "action_type": "post_event_review",
            "badge_text": f"Đã qua lễ {win.get('days_since_event', 0)} ngày",
            "badge_variant": "blue",
            "title": f"Xem kết quả {ev_name} và rút kinh nghiệm",
            "advice": "So số đơn thực tế với mục tiêu, ghi lại sản phẩm bán tốt/bán chậm và đánh giá dịp này để kế hoạch năm sau chính xác hơn.",
            "calculation_basis": f"Giữ dịp ở pha sau lễ tới {win.get('post_event_end', '')} để seller kịp đánh giá.",
            "cta_label": "Xem kết quả dịp",
            "target_tab": "performance",
            "is_urgent": False,
        }

    if phase == "last_call":
        days_to_event = int(win.get("days_to_event") or 0)
        return {
            "action_type": "last_call",
            "badge_text": f"Còn {days_to_event} ngày tới lễ",
            "badge_variant": "amber",
            "title": f"Sát lễ {ev_name}: chỉ bán hàng có sẵn",
            "advice": (
                f"Đã qua hạn chốt đơn thường ({cut_str}). Ngừng nhận mẫu làm theo yêu cầu; chỉ mở bán hàng có sẵn, "
                f"bật giao nhanh/hỏa tốc và ghi rõ thời gian giao để khách nhận trước {ev_str}."
            ),
            "calculation_basis": cutoff_basis,
            "cta_label": "Xem sản phẩm shop & tồn kho",
            "target_tab": "readiness",
            "is_urgent": True,
        }

    if days_to_cutoff <= 3 or hom_nay >= peak_d:
        if days_to_cutoff <= 1:
            badge_text = f"Hạn chốt {days_to_cutoff} ngày" if days_to_cutoff > 0 else "Hạn chốt hôm nay"
        else:
            badge_text = f"Hạn chốt còn {days_to_cutoff} ngày"

        return {
            "action_type": "close_orders",
            "badge_text": badge_text,
            "badge_variant": "amber",
            "title": f"Chốt đơn & Giao hàng kịp {ev_name}",
            "advice": f"Hạn chốt còn {days_to_cutoff} ngày ({cut_str}). Ngừng nhận mẫu đặt trước, tập trung đóng gói hàng sẵn có để kịp giao trước {ev_str}.",
            "calculation_basis": cutoff_basis,
            "cta_label": "Xem sản phẩm shop & tồn kho",
            "target_tab": "readiness",
            "is_urgent": True,
        }

    if hom_nay >= traction_d:
        return {
            "action_type": "boost_traffic",
            "badge_text": "Mở bán & gom đơn",
            "badge_variant": "blue",
            "title": prof["traction_title"],
            "advice": prof["traction_advice"],
            "calculation_basis": f"Bắt đầu mở bán {trac_str}, trước hạn chốt đơn ({cut_str}) {(cut_off_d - traction_d).days} ngày để sàn kịp index từ khóa và gom đánh giá.",
            "cta_label": "Xem xu hướng & sức mua",
            "target_tab": "traits",
            "is_urgent": False,
        }

    days_to_prep = max(0, (rd_d - hom_nay).days)
    is_in_prep = hom_nay >= rd_d
    badge_text = "Chuẩn bị nguồn hàng & mẫu" if is_in_prep else f"Chuẩn bị sau {days_to_prep} ngày"

    return {
        "action_type": "prepare_inventory",
        "badge_text": badge_text,
        "badge_variant": "emerald",
        "title": prof["prep_title"],
        "advice": prof["prep_advice"],
        "calculation_basis": f"Bắt đầu chuẩn bị {rd_d.strftime('%d/%m')} = Hạn chốt đơn ({cut_str}) − {int(ev.get('prep_days', 30))} ngày chuẩn bị của dịp.",
        "cta_label": "Xem gợi ý sản phẩm đón dịp",
        "target_tab": "potential",
        "is_urgent": False,
    }


def build_all_campaigns(
    hom_nay: date,
    cat_slug: str,
    target_camp_id: Optional[str],
    shop_lead_days: Optional[int] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Xây dựng danh sách toàn bộ dịp mua sắm trong năm và chọn chiến dịch đang xem.

    `shop_lead_days`: lead time đo từ đơn thật của shop (p90 + dự phòng); None = dùng mặc định của dịp.
    """
    all_campaigns: List[Dict[str, Any]] = []
    weekday_names = ["Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ nhật"]

    for ev in calendar_vn.SHOPPING_EVENTS:
        win = calendar_vn.calculate_occasion_window(ev, hom_nay, shop_lead_days=shop_lead_days)
        if not win:
            continue

        occasion_win = {
            "event_id": ev["key"],
            "event_key": ev["key"],
            "name": ev["name"],
            "event_name": ev["name"],
            "peak_date": win["event_date"],
            "event_date": win["event_date"],
            "lead_time_days": win["lead_time_days"],
            "rd_start": win["rd_start"],
            "traction_start": win["traction_start"],
            "peak_start": win["peak_start"],
            "cut_off_date": win["cut_off_date"],
            "current_phase": win["current_phase"],
            "days_to_peak": win["days_to_event"],
            "days_to_cutoff": win["days_to_cut_off"],
            "status": win["status"],
            "is_safe_to_launch": win["days_to_cut_off"] >= 0,
            "timing_warning": (
                None if win["days_to_cut_off"] >= 0
                else "Đã qua lễ, dịp này đang ở pha xem kết quả" if win["current_phase"] == "post_event"
                else "Đã qua hạn chốt đơn thường: chỉ nhận hàng có sẵn và giao nhanh"
            ),
            "days_since_event": win.get("days_since_event", 0),
            "cut_off_note": win.get("cut_off_note"),
            "lead_time_source": win.get("lead_time_source"),
            "default_lead_time_days": win.get("default_lead_time_days"),
            "post_event_end": win.get("post_event_end"),
            "cut_off_formula": win["cut_off_formula"],
        }

        ev_d = date.fromisoformat(win["event_date"])
        cut_off_d = date.fromisoformat(win["cut_off_date"])
        peak_d = date.fromisoformat(win["peak_start"])
        traction_d = date.fromisoformat(win["traction_start"])
        rd_d = date.fromisoformat(win["rd_start"])

        if hom_nay < rd_d:
            next_deadline_title = f"Bắt đầu chuẩn bị {rd_d.strftime('%d/%m')}"
            next_deadline_date_text = rd_d.strftime("%d/%m")
            next_deadline_days_left = (rd_d - hom_nay).days
            next_deadline_is_urgent = next_deadline_days_left <= 14
        elif hom_nay < traction_d:
            next_deadline_title = f"Bắt đầu đăng bán {traction_d.strftime('%d/%m')}"
            next_deadline_date_text = traction_d.strftime("%d/%m")
            next_deadline_days_left = (traction_d - hom_nay).days
            next_deadline_is_urgent = next_deadline_days_left <= 7
        elif hom_nay < cut_off_d:
            next_deadline_title = f"Hạn chốt đơn {cut_off_d.strftime('%d/%m')}"
            next_deadline_date_text = cut_off_d.strftime("%d/%m")
            next_deadline_days_left = (cut_off_d - hom_nay).days
            next_deadline_is_urgent = next_deadline_days_left <= 14
        elif hom_nay <= ev_d:
            next_deadline_title = f"Ngày sự kiện {ev_d.strftime('%d/%m')}"
            next_deadline_date_text = ev_d.strftime("%d/%m")
            next_deadline_days_left = (ev_d - hom_nay).days
            next_deadline_is_urgent = False
        else:
            pe_d = date.fromisoformat(win["post_event_end"])
            next_deadline_title = f"Đánh giá kết quả trước {pe_d.strftime('%d/%m')}"
            next_deadline_date_text = pe_d.strftime("%d/%m")
            next_deadline_days_left = max(0, (pe_d - hom_nay).days)
            next_deadline_is_urgent = False

        if ev_d.year != hom_nay.year:
            weekday_text = f"{weekday_names[ev_d.weekday()]}, {ev_d.strftime('%d/%m/%Y')}"
        else:
            weekday_text = f"{weekday_names[ev_d.weekday()]}, {ev_d.strftime('%d/%m')}"

        days_to_peak = win["days_to_event"]
        if days_to_peak > 60:
            conf_level, conf_text, conf_dots, is_dashed = "preliminary", "Sơ bộ", 1, True
            conf_reason = f"Dịp còn xa ({days_to_peak} ngày), ước tính sơ bộ theo ngành."
        elif ev["key"] in ("tet", "11/11", "12/12", "noel") or win["days_to_cut_off"] <= 14:
            conf_level, conf_text, conf_dots, is_dashed = "high", "Cao", 4, False
            conf_reason = "Xếp theo quy tắc khoảng cách ngày (dịp lớn hoặc sắp tới hạn chốt), chưa đối chiếu số liệu đơn thực tế."
        else:
            conf_level, conf_text, conf_dots, is_dashed = "fair", "Khá", 3, False
            conf_reason = "Xếp theo quy tắc khoảng cách ngày, chưa đối chiếu số liệu đơn thực tế."

        all_campaigns.append(
            {
                "id": ev["key"],
                "name": ev["name"],
                "icon": ev.get("icon", "calendar"),
                "badge": ev.get("badge", ""),
                "months": sorted(list({rd_d.month, ev_d.month})),
                "prep_days": ev.get("prep_days", 30),
                "lead_time_days": ev.get("lead_time_days", 14),
                "category_summary": ev.get("category_focus", ""),
                "search_keywords": ev.get("default_search_keywords", []),
                "occasion_window": occasion_win,
                "launch_window": {
                    "start": win["rd_start"],
                    "end": win["cut_off_date"],
                    "peak_date": win["event_date"],
                    "traction_start": win["traction_start"],
                    "peak_start": win["peak_start"],
                    "basis": win["cut_off_formula"],
                },
                "timing": {
                    "status": win["status"],
                    "label": win["phase_label"],
                    "badge_tone": win["badge_tone"],
                    "current_phase": win["current_phase"],
                    "days_diff": win["days_to_cut_off"],
                    "days_to_event": win["days_to_event"],
                    "days_until_peak": win["days_to_event"],
                    "is_current": win["status"] == "active",
                },
                "confidence": {
                    "level": conf_level,
                    "text": conf_text,
                    "dots": conf_dots,
                    "reason": conf_reason,
                },
                "confidence_text": conf_text,
                "confidence_dots": conf_dots,
                "expected_orders": None,
                "weekday_text": weekday_text,
                "next_deadline": {
                    "title": next_deadline_title,
                    "date_text": next_deadline_date_text,
                    "days_left": next_deadline_days_left,
                    "is_urgent": next_deadline_is_urgent,
                },
                "stages": {
                    "prep_start_days": max(0, (rd_d - hom_nay).days),
                    "traction_start_days": max(0, (traction_d - hom_nay).days),
                    "peak_days": max(0, (peak_d - hom_nay).days),
                    "cutoff_days": max(0, (cut_off_d - hom_nay).days),
                    "end_days": max(0, (ev_d - hom_nay).days),
                },
                "is_dashed_curve": is_dashed,
                "action_recommendation": tao_khuyen_nghi_hanh_dong(ev, win, hom_nay, cat_slug),
            }
        )

    all_campaigns.sort(key=lambda c: c["launch_window"]["peak_date"])

    active_camp = None
    if target_camp_id:
        active_camp = next((c for c in all_campaigns if c["id"] == target_camp_id), None)
    if not active_camp:
        actives = [c for c in all_campaigns if c["timing"]["status"] == "active"]
        if actives:
            actives.sort(key=lambda c: c["timing"]["days_diff"])
            active_camp = actives[0]
        else:
            upcomings = [c for c in all_campaigns if c["timing"]["status"] == "upcoming"]
            upcomings.sort(key=lambda c: c["timing"]["days_diff"])
            active_camp = upcomings[0] if upcomings else all_campaigns[0]

    return all_campaigns, active_camp


EXPECTED_RATE_DAYS = 60
EXPECTED_MIN_ORDERS = 5          # dưới mức này vẫn tính nhưng gắn cờ độ tin cậy thấp
EXPECTED_MIN_COVERAGE_DAYS = 7   # dưới 7 ngày lịch sử thì chưa tính được
EXPECTED_CONFIDENT_DAYS = 14


UPLIFT_SOURCE_LABELS = {
    "shop_orders": "đơn của shop ở dịp này các năm trước",
    "platform_orders": "đơn toàn sàn ở dịp này các năm trước",
    "market_sold": "tốc độ bán thật trên Tiki trong kỳ dịp so với trước dịp",
}
PLATFORM_MIN_PRE_ORDERS = 50


def attach_expected_orders(
    all_campaigns: List[Dict[str, Any]],
    shop_orders_hist: List[Dict[str, Any]],
    hom_nay: date,
    platform_orders: Optional[List[Dict[str, Any]]] = None,
    market_uplift: Optional[Callable[[Dict[str, Any], date, date], Optional[Dict[str, Any]]]] = None,
) -> None:
    """
    Đơn dự kiến của từng dịp = mức bán ngày thường (nhịp đơn 60 ngày × số ngày kỳ dịp) × mức tăng đơn
    ĐO TỪ DỮ LIỆU BÁN THẬT: đơn của shop các mùa trước → đơn toàn sàn các mùa trước → tốc độ bán trên Tiki.
    Không dùng lượt tìm kiếm. Chưa đo được mức tăng thì giữ mức ngày thường và ghi rõ.
    """
    times = [t for t in (_si_dt(o.get("created_at")) for o in shop_orders_hist) if t]
    first = min(times, default=None)

    def rate_until(end: datetime) -> Optional[Tuple[float, int, int]]:
        """Nhịp đơn tối đa 60 ngày trước `end` (cùng quy tắc với BE baselineDailyRate). None khi < 7 ngày lịch sử."""
        if first is None or first >= end:
            return None
        start = max(end - timedelta(days=EXPECTED_RATE_DAYS), first)
        coverage = max(1, int(-(-(end - start).total_seconds() // 86400)))
        if coverage < EXPECTED_MIN_COVERAGE_DAYS:
            return None
        n = sum(1 for t in times if start <= t < end)
        return n / float(coverage), n, coverage

    recent = rate_until(datetime.combine(hom_nay + timedelta(days=1), datetime.min.time()))
    for camp in all_campaigns:
        try:
            ow = camp.get("occasion_window") or {}
            lw = camp.get("launch_window") or {}
            st_str = ow.get("traction_start") or lw.get("start")
            ev_str = ow.get("event_date") or lw.get("peak_date")
            if not st_str or not ev_str:
                continue
            st_d, ev_d = date.fromisoformat(st_str), date.fromisoformat(ev_str)
            days = max(7, (ev_d - st_d).days + 1)  # tính cả ngày mở bán và ngày lễ (khớp kỳ đo của phễu)
            # Dịp đã mở bán: nhịp nền TRƯỚC ngày mở bán (khớp phễu), để đơn của chính mùa không bị tính là "ngày thường"
            started = st_d <= hom_nay
            base = rate_until(datetime.combine(st_d, datetime.min.time())) if started else recent
            rate_label = "trước ngày mở bán" if started else "gần nhất"
            if base is None:
                camp["expected_orders"] = None
                camp["expected_uplift"] = None
                camp["expected_low_confidence"] = True
                camp["expected_orders_basis"] = "Shop có dưới 7 ngày lịch sử đơn nên chưa tính được mức ngày thường."
                continue
            rate, n_base, coverage = base
            low_conf = n_base < EXPECTED_MIN_ORDERS or coverage < EXPECTED_CONFIDENT_DAYS
            camp["expected_low_confidence"] = low_conf
            ev_info = next((e for e in calendar_vn.SHOPPING_EVENTS if e["key"] == camp.get("id")), None)
            past = sorted(d for d in calendar_vn.event_dates_by_year(ev_info, range(2021, hom_nay.year + 1)).values()
                          if d < hom_nay and d != ev_d) if ev_info else []
            uplift, source = order_uplift_from_history(shop_orders_hist, past, days), "shop_orders"
            if uplift is None and platform_orders:
                uplift, source = order_uplift_from_history(platform_orders, past, days, min_pre_orders=PLATFORM_MIN_PRE_ORDERS), "platform_orders"
            if uplift is None and market_uplift is not None:
                uplift, source = market_uplift(camp, st_d, ev_d), "market_sold"
            r = expected_orders_range(rate, days, uplift)
            camp["expected_orders"] = f"{r['p10']}" if r["p10"] == r["p90"] else f"{r['p10']}–{r['p90']}"
            camp["expected_uplift"] = {**uplift, "source": source} if uplift else None
            base_txt = f"{rate:.2f} đơn/ngày ({n_base} đơn trong {coverage} ngày {rate_label}) × {days} ngày kỳ dịp"
            if uplift:
                spread = f"x{uplift['mid']:g}" if uplift["low"] == uplift["high"] else f"x{uplift['mid']:g} (x{uplift['low']:g}–x{uplift['high']:g})"
                camp["expected_orders_basis"] = f"{base_txt} × mức tăng {spread} đo từ {UPLIFT_SOURCE_LABELS[source]}; khoảng 80%."
            else:
                camp["expected_orders_basis"] = (
                    f"{base_txt}, khoảng 80%. Chưa đo được mức tăng đơn của dịp này (chưa có đơn mùa trước "
                    "hay đủ lịch sử bán trên Tiki) nên đang là mức ngày thường."
                )
            if low_conf:
                camp["expected_orders_basis"] += " Độ tin cậy thấp: còn ít đơn hoặc lịch sử ngắn."
        except Exception as exc:  # noqa: BLE001
            log.warning("seasonal: %s: %s", type(exc).__name__, exc)


def build_milestone_actions(active_camp: Dict[str, Any], cat_slug: str) -> List[Dict[str, str]]:
    """Lộ trình 3 mốc hành động cá nhân hóa theo ngành hàng và dịp."""
    camp_clean_name = active_camp["name"].replace("Lễ Hội ", "").replace("Mùa ", "")
    cat_display_name = CAT_LABELS.get(cat_slug, "Toàn ngành hàng TMĐT")
    lw = active_camp.get("launch_window") or {}
    first_kw = active_camp["search_keywords"][0] if active_camp.get("search_keywords") else camp_clean_name
    return [
        {
            "title": f"Trước ngày dịp 6 tuần · {lw.get('start') or 'Bắt đầu chuẩn bị'}",
            "desc": f"Lấy mẫu thử, chụp ảnh concept theo chủ đề {camp_clean_name} cho ngành {cat_display_name}, đăng listing sớm để sàn kịp index.",
        },
        {
            "title": f"Trước ngày dịp 3 tuần · {lw.get('end') or 'Hạn chót đăng bán'}",
            "desc": f"Hoàn tất niêm yết, tối ưu từ khóa ngách #{first_kw} và gom 3-5 lượt mua đầu tiên.",
        },
        {
            "title": f"Tuần cao điểm & Hạn chốt nhận đơn · {lw.get('peak_date') or 'Đỉnh cao điểm'}",
            "desc": f"Đỉnh mua sắm {camp_clean_name}: kích hoạt combo quà tặng và áp voucher shop để nâng giá trị trung bình giỏ hàng.",
        },
    ]

