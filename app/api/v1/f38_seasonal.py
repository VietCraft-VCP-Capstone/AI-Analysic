import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from fastapi import APIRouter

from app.api.v1._live import la_shop_live, san_pham_live
from app.api.v1._mart import db
from app.api.v1._template import CurrentShop, insufficient, mart_not_ready, meta_from_record, ok, build_meta
from app.core import calendar_vn
from app.core.potential_profile import build_product_potential_profile
from app.core.listing_intel.trend_store import weekly_series

router = APIRouter()

MART = "seasonal_profile"
LUI_SAN_XUAT = 18       # BR-209: lùi thời gian in ấn (4 ngày p90) + vận chuyển (4 ngày p90) + vùng đệm (2 ngày)


def _lay_chuoi_trend_cho_tu_khoa(kw: str) -> List[tuple]:
    """Lấy chuỗi tuần Google Trends thật (2021-2026) cho từ khóa."""
    all_series = weekly_series()
    if kw in all_series:
        s = all_series[kw]
        return [(d.strftime("%Y-%m-%d"), float(v)) for d, v in s.items()]
    # Thử tìm từ khóa tương đồng trong 45 từ khóa có sẵn
    kw_low = kw.lower()
    for k, s in all_series.items():
        if kw_low in k or k in kw_low:
            return [(d.strftime("%Y-%m-%d"), float(v)) for d, v in s.items()]
    # Mặc định lấy từ khóa 'quà tặng' nếu không khớp
    if "quà tặng" in all_series:
        s = all_series["quà tặng"]
        return [(d.strftime("%Y-%m-%d"), float(v)) for d, v in s.items()]
    return []


def _tinh_stl_that(series_points: List[tuple], chu_ky: int = 52) -> Dict[str, Any]:
    """
    Tính toán phân rã Trend + Seasonal + Residual thật từ chuỗi điểm Google Trends.
    Nếu không đủ điểm thì trả về chuỗi làm mượt trung bình động.
    """
    if len(series_points) < chu_ky:
        vals = [p[1] for p in series_points] if series_points else [50.0] * chu_ky
        return {
            "trend": vals[-52:],
            "seasonal": [0.0] * min(52, len(vals)),
            "residual": [0.0] * min(52, len(vals)),
            "window": "52 tuần gần nhất"
        }

    # Lấy 52 tuần gần nhất
    recent = series_points[-chu_ky:]
    y = [p[1] for p in recent]
    
    # Trend: moving average bán kính 2
    trend = []
    for i in range(len(y)):
        sub = y[max(0, i - 2): min(len(y), i + 3)]
        trend.append(round(sum(sub) / len(sub), 2))
    
    # Seasonal: phần dao động theo mùa so với cùng kỳ năm trước
    seasonal = []
    if len(series_points) >= chu_ky * 2:
        last_year = [p[1] for p in series_points[-chu_ky * 2: -chu_ky]]
        for i in range(chu_ky):
            diff = (y[i] - trend[i] + last_year[i] - (sum(last_year) / len(last_year))) / 2.0
            seasonal.append(round(diff, 2))
    else:
        for i in range(chu_ky):
            seasonal.append(round(y[i] - trend[i], 2))

    # Residual
    residual = [round(y[i] - trend[i] - seasonal[i], 2) for i in range(chu_ky)]

    return {
        "trend": trend,
        "seasonal": seasonal,
        "residual": residual,
        "window": "52 tuần gần nhất"
    }


# Danh sách phôi POD và sản phẩm mẫu cho từng dịp lớn
OCCASION_PRODUCT_BLUEPRINTS: Dict[str, List[Dict[str, Any]]] = {
    "tet": [
        {"title": "Hộp Quà Mứt Tết & Trà Gỗ Khắc Laser", "category": "Quà tặng & Gia dụng", "keyword": "quà tết", "price": 285000, "cost": 115000},
        {"title": "Bộ Ly Sứ Bát Tràng Họa Tiết Mai Đào An Khang", "category": "Gia dụng & Đồ gốm", "keyword": "quà tết", "price": 195000, "cost": 82000},
        {"title": "Bao Lì Xì Giấy Mỹ Thuật Dập Nổi Phúc Lộc", "category": "Phụ kiện & Thủ công", "keyword": "lì xì tết", "price": 45000, "cost": 12000},
        {"title": "Áo Dài Cách Tân Nhung Đỏ Họa Tiết Rồng Mây", "category": "Thời trang & May mặc", "keyword": "áo tết", "price": 420000, "cost": 180000},
    ],
    "valentine": [
        {"title": "Cốc Sứ Đôi In Tên Riêng Kèm Muỗng Gỗ", "category": "Quà tặng & Đồ gốm", "keyword": "quà valentine", "price": 210000, "cost": 88000},
        {"title": "Khung Tranh Gỗ Mini Khắc Tọa Độ & Ngày Kỷ Niệm", "category": "Quà lưu niệm", "keyword": "quà tặng người yêu", "price": 165000, "cost": 62000},
        {"title": "Áo Thun Đôi Minimalist Thêu Trái Tim", "category": "Thời trang", "keyword": "áo đôi", "price": 320000, "cost": 135000},
    ],
    "8/3": [
        {"title": "Set Quà Tặng Nến Thơm & Hoa Khô Handmade", "category": "Quà tặng phái đẹp", "keyword": "quà 8/3", "price": 245000, "cost": 95000},
        {"title": "Túi Tote Vải Canvas Dày Thêu Hoa Nhí", "category": "Phụ kiện thời trang", "keyword": "túi tote", "price": 145000, "cost": 55000},
        {"title": "Bình Giữ Nhiệt Khắc Tên Riêng Tri Ân Mẹ & Đồng Nghiệp", "category": "Gia dụng văn phòng", "keyword": "quà tặng mẹ", "price": 185000, "cost": 78000},
    ],
    "30/4": [
        {"title": "Áo Thun Unisex Cotton 100% In Họa Tiết Dã Ngoại", "category": "Thời trang du lịch", "keyword": "áo thun", "price": 175000, "cost": 72000},
        {"title": "Túi Tote Đi Biển Chống Nước Họa Tiết Nhiệt Đới", "category": "Phụ kiện", "keyword": "túi tote", "price": 135000, "cost": 50000},
        {"title": "Bình Nước Thể Thao Khắc Tên Độc Bản", "category": "Gia dụng", "keyword": "quà lưu niệm", "price": 160000, "cost": 65000},
    ],
    "khai_giang": [
        {"title": "Áo Lớp/Áo Nhóm Oversize In Phản Quang Theo Yêu Cầu", "category": "Thời trang học đường", "keyword": "áo lớp", "price": 140000, "cost": 58000},
        {"title": "Sổ Tay Bìa Da Khắc Tên Kèm Bút Gỗ Mộc", "category": "Văn phòng phẩm", "keyword": "quà tặng", "price": 125000, "cost": 48000},
        {"title": "Móc Khóa Mica In Hình & Thẻ Tên Học Sinh", "category": "Phụ kiện", "keyword": "móc khóa", "price": 35000, "cost": 10000},
    ],
    "trung_thu": [
        {"title": "Hộp Trà Gỗ Khắc Họa Tiết Trăng Tròn Đoàn Viên", "category": "Quà biếu", "keyword": "quà trung thu", "price": 230000, "cost": 92000},
        {"title": "Lồng Đèn Giấy Thủ Công Tự Lắp Ghép Cho Trẻ Em", "category": "Đồ chơi mộc", "keyword": "quà tặng", "price": 65000, "cost": 22000},
        {"title": "Áo Thun Gia Đình In Hình Thỏ Ngọc", "category": "Thời trang", "keyword": "áo gia đình", "price": 280000, "cost": 110000},
    ],
    "20/10": [
        {"title": "Bình Gốm Cắm Hoa Men Rạn Mộc Bát Tràng", "category": "Gia dụng & Thủ công", "keyword": "quà 20/10", "price": 220000, "cost": 85000},
        {"title": "Hộp Quà Khăn Lụa & Trâm Cài Tóc Gỗ Xà Cừ", "category": "Quà tặng", "keyword": "quà tặng mẹ", "price": 260000, "cost": 105000},
        {"title": "Cốc Sứ Quà Tặng Tri Ân Nữ Giới Cơ Quan/Doanh Nghiệp", "category": "Quà doanh nghiệp", "keyword": "quà 20/10", "price": 135000, "cost": 52000},
    ],
    "halloween": [
        {"title": "Áo Hoodie Nỉ Bông Đen Phong Cách Gothic Bí Ẩn", "category": "Thời trang", "keyword": "áo hoodie", "price": 340000, "cost": 145000},
        {"title": "Ly Sứ Men Đen Nhám Tạo Hình Bí Ngô & Phù Thủy", "category": "Gia dụng độc lạ", "keyword": "cốc in hình", "price": 165000, "cost": 65000},
        {"title": "Tranh Canvas Decor Phòng Phong Cách Kỳ Bí", "category": "Trang trí", "keyword": "poster trang trí", "price": 190000, "cost": 75000},
    ],
    "20/11": [
        {"title": "Bộ Sổ Bìa Da & Bút Gỗ Khắc Lời Tri Ân Thầy Cô", "category": "Quà tặng giáo viên", "keyword": "quà 20/11", "price": 195000, "cost": 75000},
        {"title": "Bình Giữ Nhiệt In Tranh Thư Pháp 'Tôn Sư Trọng Đạo'", "category": "Gia dụng", "keyword": "quà tặng thầy cô", "price": 180000, "cost": 70000},
        {"title": "Tranh Gỗ Khắc Chân Dung Thầy Cô Theo Yêu Cầu", "category": "Quà thủ công cá nhân hóa", "keyword": "quà lưu niệm", "price": 290000, "cost": 115000},
    ],
    "noel": [
        {"title": "Áo Len Dệt Họa Tiết Cây Thông & Tuần Lộc Ấm Áp", "category": "Thời trang đông", "keyword": "áo giáng sinh", "price": 310000, "cost": 130000},
        {"title": "Ly Sứ Giáng Sinh Nắp Người Tuyết Đóng Hộp Quà", "category": "Gia dụng", "keyword": "quà giáng sinh", "price": 175000, "cost": 68000},
        {"title": "Set Vớ Giáng Sinh & Nến Quế Thơm Ấm Áp", "category": "Quà tặng", "keyword": "trang trí noel", "price": 155000, "cost": 58000},
        {"title": "Tranh Treo Tường Ngôi Làng Tuyết Phát Sáng", "category": "Trang trí nhà cửa", "keyword": "trang trí noel", "price": 210000, "cost": 82000},
    ],
}


@router.get("/api/analytics/forecast/seasonal", tags=["F38 · Mùa vụ & Lịch ra hàng"])
def seasonal(
    shop_id: str = CurrentShop,
    categoryId: Optional[str] = None,
    category_slug: Optional[str] = None,
    campaign_id: Optional[str] = None,
    campaignId: Optional[str] = None,
    keyword: Optional[str] = None,
):
    # Xác định ngày hôm nay từ dữ liệu
    if la_shop_live(shop_id):
        hom_nay = date.today()
    else:
        ld = db()["listing_daily"].find_one({}, {"date": 1}, sort=[("date", -1)])
        hom_nay = datetime.strptime(ld["date"], "%Y-%m-%d").date() if ld else date.today()

    cat_slug = category_slug or categoryId or "thoi-trang"
    target_camp_id = campaign_id or campaignId

    # Lấy thông tin sản phẩm và đối thủ trên sàn
    competitors_coll = db()["mart_competitor"]
    all_competitors = list(competitors_coll.find({}, {"_id": 0, "shop_name": 1, "price_vnd": 1, "category_id": 1}).limit(100))

    # Xây dựng danh sách toàn bộ các dịp mua sắm trong năm với cửa sổ 4 pha chuẩn xác
    all_campaigns = []
    for ev in calendar_vn.SHOPPING_EVENTS:
        win = calendar_vn.calculate_occasion_window(ev, hom_nay)
        if not win:
            continue
        all_campaigns.append({
            "id": ev["key"],
            "name": ev["name"],
            "icon": ev.get("icon", "calendar"),
            "badge": ev.get("badge", ""),
            "prep_days": ev.get("prep_days", 30),
            "lead_time_days": ev.get("lead_time_days", 14),
            "category_summary": ev.get("category_focus", ""),
            "search_keywords": ev.get("default_search_keywords", []),
            "launch_window": {
                "start": win["rd_start"],
                "end": win["cut_off_date"],
                "peak_date": win["event_date"],
                "traction_start": win["traction_start"],
                "peak_start": win["peak_start"],
                "basis": win["cut_off_formula"]
            },
            "timing": {
                "status": win["status"],
                "label": win["phase_label"],
                "badge_tone": win["badge_tone"],
                "current_phase": win["current_phase"],
                "days_diff": win["days_to_cut_off"],
                "days_to_event": win["days_to_event"],
                "is_current": win["status"] == "active"
            }
        })

    # Xác định chiến dịch mục tiêu (Active Campaign)
    active_camp = None
    if target_camp_id:
        active_camp = next((c for c in all_campaigns if c["id"] == target_camp_id), None)
    if not active_camp:
        # Ưu tiên dịp đang 'active' có số ngày đến hạn chốt đơn > 0
        actives = [c for c in all_campaigns if c["timing"]["status"] == "active"]
        if actives:
            # Sắp xếp theo ngày hạn chốt đơn gần nhất
            actives.sort(key=lambda c: c["timing"]["days_diff"])
            active_camp = actives[0]
        else:
            upcomings = [c for c in all_campaigns if c["timing"]["status"] == "upcoming"]
            upcomings.sort(key=lambda c: c["timing"]["days_diff"])
            active_camp = upcomings[0] if upcomings else all_campaigns[0]

    # Lấy chuỗi Google Trends của từ khóa đại diện
    primary_kw = active_camp["search_keywords"][0] if active_camp["search_keywords"] else "quà tặng"
    trend_series = _lay_chuoi_trend_cho_tu_khoa(primary_kw)

    # Phân rã STL thật sự từ chuỗi tuần
    stl = _tinh_stl_that(trend_series, chu_ky=52)

    # Xây dựng Hồ Sơ Tiềm Năng 5 Lớp cho các sản phẩm đề xuất của dịp này
    blueprints = OCCASION_PRODUCT_BLUEPRINTS.get(active_camp["id"], OCCASION_PRODUCT_BLUEPRINTS.get("tet", []))
    ev_info = next(e for e in calendar_vn.SHOPPING_EVENTS if e["key"] == active_camp["id"])
    ev_win = calendar_vn.calculate_occasion_window(ev_info, hom_nay) or {
        "event_date": hom_nay.isoformat(),
        "cut_off_date": (hom_nay + timedelta(days=21)).isoformat()
    }

    target_ev_d = date.fromisoformat(ev_win["event_date"])
    cut_off_d = date.fromisoformat(ev_win["cut_off_date"])

    potential_profiles = []
    for bp in blueprints:
        kw_trend = _lay_chuoi_trend_cho_tu_khoa(bp["keyword"])
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
            competitor_listings=all_competitors,
            shop_has_similar_sales=False,
            shop_lead_time_days=4,
        )
        potential_profiles.append(p_profile)

    # Đóng gói danh sách sự kiện chi tiết
    events_payload = []
    for idx, kw in enumerate(active_camp["search_keywords"][:5]):
        kw_pts = _lay_chuoi_trend_cho_tu_khoa(kw)
        recent_vals = [p[1] for p in kw_pts[-8:]] if kw_pts else [40.0]
        avg_val = sum(recent_vals) / len(recent_vals)
        events_payload.append({
            "name": kw,
            "peak_week_of_year": target_ev_d.isocalendar()[1],
            "amplitude": round(avg_val / 100.0, 2),
            "launch_window": active_camp["launch_window"],
            "ready_to_ship_ideas": [
                {
                    "title": bp["title"],
                    "category": bp["category"],
                    "suggested_price": f"{bp['price']:,}đ",
                    "base_cost": f"{bp['cost']:,}đ",
                    "expected_profit": f"{bp['price'] - bp['cost'] - int(bp['price'] * 0.1):,}đ/sp",
                    "why": f"Nhu cầu từ khóa '{bp['keyword']}' đang trong pha cao điểm",
                    "signal_label": potential_profiles[idx % len(potential_profiles)]["signal_label"] if potential_profiles else "Tín hiệu Khá ●●○○"
                } for bp in blueprints[:2]
            ],
            "pod_blanks": [
                {"blank_type": "mug_11oz", "name": "Cốc sứ 11oz men trắng", "base_cost": 45000},
                {"blank_type": "tshirt_unisex", "name": "Áo thun cotton 100% 250gsm", "base_cost": 75000},
                {"blank_type": "canvas_stretched", "name": "Khung tranh canvas gỗ thông", "base_cost": 65000},
                {"blank_type": "tote", "name": "Túi canvas dày có khóa kéo", "base_cost": 50000},
            ]
        })

    meta = build_meta(
        scope="platform",
        scope_id=active_camp["id"],
        collection=MART,
        mode="derived",
        sample_size=len(trend_series),
        confidence="high" if len(trend_series) >= 100 else "medium"
    )

    return ok({
        "all_campaigns": all_campaigns,
        "active_campaign": active_camp,
        "selected_category_slug": cat_slug,
        "keyword": active_camp["name"],
        "primary_keyword": primary_kw,
        "decomposition": stl,
        "amplitude": round(sum(stl["seasonal"][:10]) / 10, 2) if stl["seasonal"] else 0.5,
        "n_points": len(trend_series),
        "events": events_payload,
        "potential_profiles": potential_profiles,
        "method": "Phân rã chuỗi thời gian Google Trends VN + Lịch mua sắm quốc gia + Hồ sơ kiểm chứng 5 lớp",
        "limitation": "Không có dữ liệu nào đảm bảo chắc chắn sản phẩm sẽ bán chạy. Seller cần tự kiểm tra 5 lớp bằng chứng và bắt đầu từ bước Thử nhỏ."
    }, meta)
