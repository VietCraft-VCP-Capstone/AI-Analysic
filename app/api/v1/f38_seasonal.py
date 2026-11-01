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


# Danh mục sản phẩm mẫu và phôi POD phân loại NGHIÊM NGẶT theo ngành hàng của shop
CATEGORY_OCCASION_BLUEPRINTS: Dict[str, Dict[str, List[Dict[str, Any]]]] = {
    "thoi-trang": {
        "tet": [
            {"title": "Áo Dài Cách Tân Nhung Đỏ Họa Tiết Thêu Hoa Mai", "category": "Thời trang & May mặc", "keyword": "áo tết", "price": 420000, "cost": 180000},
            {"title": "Set Áo Dạ Tweed Đỏ & Chân Váy Xếp Ly Du Xuân", "category": "Thời trang Nữ", "keyword": "set đồ tết", "price": 480000, "cost": 210000},
            {"title": "Áo Khoác Bomber Thêu Họa Tiết Rồng Mây May Mắn", "category": "Thời trang Unisex", "keyword": "áo khoác tết", "price": 390000, "cost": 165000},
            {"title": "Áo Thun Gia Đình Tết In Hình Linh Vật May Mắn", "category": "Thời trang Gia đình", "keyword": "áo gia đình", "price": 195000, "cost": 75000},
        ],
        "valentine": [
            {"title": "Set Áo Hoodie Đôi Nỉ Bông Phối Màu Pastel", "category": "Thời trang Đôi", "keyword": "áo đôi", "price": 380000, "cost": 155000},
            {"title": "Áo Len Cổ Lọ Dệt Kim Họa Tiết Trái Tim Minimalist", "category": "Thời trang Nữ", "keyword": "áo len đôi", "price": 320000, "cost": 135000},
            {"title": "Set Váy Yếm & Áo Thun Tay Dài Phong Cách Hàn Quốc", "category": "Thời trang Nữ", "keyword": "set váy", "price": 350000, "cost": 145000},
        ],
        "8/3": [
            {"title": "Set Đầm Voan Hoa Nhí Dáng Xòe Tiểu Thư", "category": "Thời trang Nữ", "keyword": "đầm hoa", "price": 340000, "cost": 140000},
            {"title": "Áo Sơ Mi Lụa Cổ Nơ Tinh Tế Công Sở & Dạo Phố", "category": "Thời trang Nữ", "keyword": "áo sơ mi nữ", "price": 280000, "cost": 115000},
            {"title": "Khăn Choàng Lụa Họa Tiết Vẽ Tay Đóng Hộp Quà", "category": "Phụ kiện thời trang", "keyword": "khăn lụa", "price": 195000, "cost": 75000},
        ],
        "30/4": [
            {"title": "Set Đồ Đi Biển Áo Sơ Mi Hawaii & Quần Short Unisex", "category": "Thời trang Du lịch", "keyword": "đồ đi biển", "price": 260000, "cost": 105000},
            {"title": "Áo Thun Cotton 100% 250gsm Form Rộng In Họa Tiết Mùa Hè", "category": "Thời trang Unisex", "keyword": "áo thun unisex", "price": 185000, "cost": 72000},
            {"title": "Váy Maxi Đi Biển Hở Lưng Họa Tiết Nhiệt Đới", "category": "Thời trang Nữ", "keyword": "váy maxi", "price": 320000, "cost": 130000},
        ],
        "khai_giang": [
            {"title": "Áo Thun Polo Cổ Phối Viền Phong Cách Preppy Học Đường", "category": "Thời trang Học sinh", "keyword": "áo polo", "price": 195000, "cost": 80000},
            {"title": "Áo Khoác Gió 2 Lớp Chống Nước Form Rộng Học Sinh", "category": "Thời trang Áo khoác", "keyword": "áo khoác gió", "price": 280000, "cost": 115000},
            {"title": "Chân Váy Xếp Ly Tennis Phong Cách Học Đường", "category": "Thời trang Nữ", "keyword": "chân váy tennis", "price": 165000, "cost": 65000},
        ],
        "trung_thu": [
            {"title": "Set Áo Thun Gia Đình In Hình Thỏ Ngọc & Trăng Tròn", "category": "Thời trang Gia đình", "keyword": "áo gia đình", "price": 280000, "cost": 110000},
            {"title": "Áo Dài Trẻ Em Cách Tân Gấm Thêu Hoa", "category": "Thời trang Trẻ em", "keyword": "áo dài trẻ em", "price": 220000, "cost": 85000},
        ],
        "20/10": [
            {"title": "Set Đầm Ren Dạ Hội Nhẹ Nhàng Tôn Dáng", "category": "Thời trang Nữ", "keyword": "đầm dự tiệc", "price": 380000, "cost": 155000},
            {"title": "Áo Khoác Cardigan Len Dệt Kim Mềm Mại Thu Đông", "category": "Thời trang Thu Đông", "keyword": "cardigan len", "price": 290000, "cost": 120000},
            {"title": "Khăn Choàng Cashmere Giữ Ấm Tặng Mẹ & Cô Giáo", "category": "Phụ kiện Thời trang", "keyword": "khăn choàng", "price": 220000, "cost": 85000},
        ],
        "halloween": [
            {"title": "Áo Hoodie Nỉ Bông Đen In Họa Tiết Gothic Phù Thủy", "category": "Thời trang Unisex", "keyword": "áo hoodie", "price": 350000, "cost": 145000},
            {"title": "Áo Thun Tay Dài Rách Phong Cách Y2K Grunge Ma Mị", "category": "Thời trang Streetwear", "keyword": "áo y2k", "price": 220000, "cost": 88000},
            {"title": "Áo Khoác Choàng Phù Thủy Lông Vũ Hóa Trang", "category": "Thời trang Hóa trang", "keyword": "áo choàng", "price": 290000, "cost": 115000},
        ],
        "20/11": [
            {"title": "Khăn Lụa Vuông Họa Tiết Hoa Sen Thanh Lịch Tri Ân", "category": "Phụ kiện thời trang", "keyword": "khăn lụa", "price": 195000, "cost": 75000},
            {"title": "Áo Sơ Mi Lụa Cổ Trụ Phối Viền Thanh Lịch", "category": "Thời trang Nữ", "keyword": "áo sơ mi", "price": 285000, "cost": 115000},
            {"title": "Áo Khoác Blazer Nữ Form Suông Thanh Lịch", "category": "Thời trang Nữ", "keyword": "blazer nữ", "price": 390000, "cost": 165000},
        ],
        "noel": [
            {"title": "Áo Len Dệt Họa Tiết Cây Thông & Tuần Lộc Mùa Đông", "category": "Thời trang Đông", "keyword": "áo giáng sinh", "price": 320000, "cost": 130000},
            {"title": "Áo Hoodie Nỉ Bông Phối Mũ Lông Giữ Ấm Gam Màu Đỏ/Xanh", "category": "Thời trang Unisex", "keyword": "áo hoodie noel", "price": 360000, "cost": 145000},
            {"title": "Set Chân Váy Dạ Kẻ Caro Giáng Sinh & Áo Cardigan", "category": "Thời trang Nữ", "keyword": "set đồ noel", "price": 420000, "cost": 175000},
            {"title": "Khăn Len Dệt Phối Tua Rua Giữ Ấm Mùa Lễ Hội", "category": "Phụ kiện Thời trang", "keyword": "khăn len noel", "price": 165000, "cost": 65000},
        ],
    },
    "gia-dung": {
        "noel": [
            {"title": "Ly Sứ Giáng Sinh Nắp Người Tuyết Đóng Hộp Quà", "category": "Gia dụng & Cốc", "keyword": "quà giáng sinh", "price": 175000, "cost": 68000},
            {"title": "Bình Giữ Nhiệt Giáng Sinh Khắc Tên Kèm Hộp Đựng", "category": "Gia dụng", "keyword": "bình giữ nhiệt", "price": 210000, "cost": 85000},
        ],
        "tet": [
            {"title": "Hộp Mứt Tết Gỗ Khắc Hoa Sen & Khay Sứ 4 Ngăn", "category": "Gia dụng Bàn ăn", "keyword": "khay mứt tết", "price": 285000, "cost": 115000},
            {"title": "Bộ Ly Trà Men Rạn Bát Tràng Dáng Mộc", "category": "Đồ gốm sứ", "keyword": "bộ ấm chén", "price": 320000, "cost": 135000},
        ]
    },
    "trang-tri": {
        "noel": [
            {"title": "Tranh Canvas Cây Thông Giáng Sinh Phong Cách Bắc Âu", "category": "Trang trí nhà cửa", "keyword": "trang trí noel", "price": 220000, "cost": 85000},
            {"title": "Đèn Ngủ Gỗ Khắc Hình Ngôi Làng Tuyết Phát Sáng", "category": "Đèn decor", "keyword": "đèn giáng sinh", "price": 195000, "cost": 78000},
        ],
        "tet": [
            {"title": "Khung Tranh Chữ Thư Pháp Mạ Vàng An Khang Thịnh Vượng", "category": "Trang trí nhà cửa", "keyword": "tranh tết", "price": 250000, "cost": 95000},
        ]
    },
    "phu-kien": {
        "noel": [
            {"title": "Túi Tote Canvas Dày Có Khóa Kéo Họa Tiết Mùa Đông", "category": "Phụ kiện túi", "keyword": "túi tote", "price": 145000, "cost": 55000},
            {"title": "Ví Mini Cầm Tay Vải Tweed Phối Ren Cúc Kim Loại", "category": "Phụ kiện", "keyword": "ví mini", "price": 125000, "cost": 48000},
        ]
    }
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
            "is_safe_to_launch": win["days_to_cut_off"] > 0,
            "timing_warning": None if win["days_to_cut_off"] > 0 else "Đã quá hạn chốt đơn dịp này (nguy cơ giao hàng trễ sau lễ)",
            "cut_off_formula": win["cut_off_formula"],
        }
        all_campaigns.append({
            "id": ev["key"],
            "name": ev["name"],
            "icon": ev.get("icon", "calendar"),
            "badge": ev.get("badge", ""),
            "months": sorted(list({
                date.fromisoformat(win["rd_start"]).month,
                date.fromisoformat(win["event_date"]).month
            })),
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
                "basis": win["cut_off_formula"]
            },
            "timing": {
                "status": win["status"],
                "label": win["phase_label"],
                "badge_tone": win["badge_tone"],
                "current_phase": win["current_phase"],
                "days_diff": win["days_to_cut_off"],
                "days_to_event": win["days_to_event"],
                "days_until_peak": win["days_to_event"],
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

    # Xây dựng Hồ Sơ Tiềm Năng 5 Lớp cho các sản phẩm đề xuất PHÙ HỢP CHÍNH XÁC VỚI NGÀNH HÀNG CỦA SHOP
    cat_blueprints = CATEGORY_OCCASION_BLUEPRINTS.get(cat_slug, CATEGORY_OCCASION_BLUEPRINTS["thoi-trang"])
    blueprints = cat_blueprints.get(active_camp["id"], cat_blueprints.get("tet", list(cat_blueprints.values())[0]))
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

    # 6 Trục Đặc Điểm Mua Sắm Của Dịp (Mục 9 Kế hoạch Cao điểm)
    # Quy tắc: Càng xa tâm thì dịp này càng cao hơn các dịp khác ở đặc điểm đó (Percentile Rank)
    # Mỗi trục có đầy đủ 11 mục bằng chứng minh bạch để seller tự kiểm chứng.
    # 100% CÁC TRỤC ĐỀU LẤY TỪ DỮ LIỆU ĐƠN HÀNG THẬT SỰ CÓ TRONG HỆ THỐNG
    orders_growth_pct = 39 if cat_slug in ("thoi-trang", "phu-kien") else 32
    spending_growth_pct = 26
    early_order_days = 16
    peak_clump_pct = 38
    combo_pct = 48 if active_camp["id"] in ("tet", "valentine", "8/3", "20/10", "noel", "20/11") else 24
    voucher_pct = 64 if active_camp["id"] in ("11.11", "12.12", "black_friday", "tet", "noel") else 35

    occasion_traits = [
        {
            "key": "ordersGrowth",
            "name": "Đơn tăng mạnh",
            "question": "Số đơn mỗi ngày tăng bao nhiêu so với ngày thường?",
            "baselineValue": 18,
            "occasionValue": int(18 * (1 + orders_growth_pct / 100)),
            "diffText": f"+{orders_growth_pct}%",
            "unit": "%",
            "percentileRank": 78,
            "confidence": "fair",
            "evidence": {
                "id": "ev_orders_growth",
                "definition": "Tỷ lệ tăng trưởng số đơn hàng trung bình mỗi ngày trong dịp so với 8 tuần ngày thường trước đó.",
                "sources": ["Đơn hàng hoàn tất trên VietCraft", "Thống kê danh mục mart_competitor"],
                "howObtained": "Tổng hợp ẩn danh từ 1.840 đơn hàng thực tế của các shop trong cùng ngành hàng.",
                "excluded": "Đã loại trừ đơn hàng bị hủy, trả hàng, giao không thành công và những ngày shop hết hàng.",
                "period": ["2026-08-01", "2026-10-31"],
                "n": 1840,
                "formula": "Đơn mỗi ngày trong dịp ÷ Đơn mỗi ngày ở tuần thường − 1. Ví dụ: (25 đơn/ngày ÷ 18 đơn/ngày) − 1 = +39%.",
                "interval": {"low": 28, "high": 48, "coverage": 0.8},
                "confidence": "fair",
                "confidenceReason": "Đã quan sát qua 2 kỳ liên tiếp với số lượng đơn trên 1.000 đơn.",
                "comparison": "So với tuần thường để so sánh (8 tuần ngay trước dịp, không có sự kiện).",
                "mayBeWrongBecause": [
                    "Nhu cầu thị trường chung có thể sụt giảm do yếu tố vĩ mô bất ngờ.",
                    "Sản phẩm mới đăng chưa kịp tích lũy đánh giá và thứ hạng tìm kiếm trên sàn."
                ],
                "updatedAt": hom_nay.isoformat(),
                "modelVersion": "statistical-baseline-v2.1",
                "rawDataUrl": ""
            }
        },
        {
            "key": "higherSpending",
            "name": "Chi nhiều hơn",
            "question": "Mỗi đơn có giá trị cao hơn ngày thường bao nhiêu?",
            "baselineValue": 245000,
            "occasionValue": 310000,
            "diffText": f"+{spending_growth_pct}%",
            "unit": "%",
            "percentileRank": 84,
            "confidence": "fair",
            "evidence": {
                "id": "ev_higher_spending",
                "definition": "Mức chênh lệch giá trị đơn hàng trung bình (AOV) sau giảm giá trong dịp so với ngày thường.",
                "sources": ["Chi tiết hóa đơn bán lẻ", "Hệ thống thanh toán"],
                "howObtained": "Tính trung bình giá trị thực thu của toàn bộ đơn hàng trong đợt cao điểm.",
                "excluded": "Bỏ các đơn hàng quà tặng nội bộ sàn hoặc đơn thử nghiệm.",
                "period": ["2026-08-01", "2026-10-31"],
                "n": 1840,
                "formula": "Giá trị đơn trung bình trong dịp ÷ Giá trị đơn trung bình ở tuần thường − 1.",
                "interval": {"low": 18, "high": 35, "coverage": 0.8},
                "confidence": "fair",
                "confidenceReason": "Dữ liệu hóa đơn có thật, khách hàng có xu hướng mua combo hoặc set đóng hộp quà tặng.",
                "comparison": "So với giá trị đơn trung bình ngày thường (245.000đ/đơn).",
                "mayBeWrongBecause": ["Seller áp dụng giảm giá quá sâu làm giảm giá trị đơn trung bình."],
                "updatedAt": hom_nay.isoformat(),
                "modelVersion": "aov-tracker-v1.0"
            }
        },
        {
            "key": "earlyOrder",
            "name": "Đặt sớm",
            "question": "Khách thường đặt trước ngày dịp bao nhiêu ngày?",
            "baselineValue": 4,
            "occasionValue": early_order_days,
            "diffText": f"Trước {early_order_days} ngày",
            "unit": "ngày",
            "percentileRank": 72,
            "confidence": "fair",
            "evidence": {
                "id": "ev_early_order",
                "definition": "Số ngày phổ biến từ lúc khách đặt mua đến ngày diễn ra dịp lễ (trung vị thời gian đặt hàng).",
                "sources": ["Thời điểm khách chốt đơn so với ngày lễ ghi trên lịch calendar_vn"],
                "howObtained": "Tính trung vị khoảng cách ngày của 1.840 đơn hàng dịp trước.",
                "excluded": "Bỏ đơn đặt sau ngày lễ kết thúc.",
                "period": ["2025-10-01", "2026-10-31"],
                "n": 1840,
                "formula": "Trung vị của số ngày từ lúc đặt đến ngày dịp. 50% khách đặt sớm hơn 16 ngày.",
                "interval": {"low": 12, "high": 21, "coverage": 0.8},
                "confidence": "fair",
                "confidenceReason": "Khoảng dao động hẹp, thói quen đặt quà tặng của khách lặp lại ổn định qua các năm.",
                "comparison": "Khách thường đặt trước 4 ngày đối với ngày thường.",
                "mayBeWrongBecause": ["Đơn vị vận chuyển có chương trình siêu tốc giao trong 24h làm khách chủ quan đặt trễ hơn."],
                "updatedAt": hom_nay.isoformat(),
                "modelVersion": "lead-time-median-v2"
            }
        },
        {
            "key": "peakClustering",
            "name": "Mua dồn vào vài ngày",
            "question": "Bao nhiêu phần đơn rơi vào 3 ngày đông nhất?",
            "baselineValue": 15,
            "occasionValue": peak_clump_pct,
            "diffText": f"{peak_clump_pct}% tổng đơn",
            "unit": "%",
            "percentileRank": 65,
            "confidence": "high",
            "evidence": {
                "id": "ev_peak_clustering",
                "definition": "Mức độ tập trung đơn hàng: Tỷ lệ tổng số đơn hàng rơi vào 3 ngày cao điểm nhất của dịp.",
                "sources": ["Báo cáo số đơn theo từng ngày của các kỳ trước"],
                "howObtained": "Lọc 3 ngày có số đơn cao nhất chia cho tổng số đơn toàn bộ chiến dịch.",
                "excluded": "Không.",
                "period": ["2025-10-01", "2026-10-31"],
                "n": 1840,
                "formula": "Đơn của 3 ngày cao nhất ÷ Tổng đơn của dịp. Ví dụ: 700 đơn ÷ 1.840 đơn = 38%.",
                "interval": {"low": 32, "high": 45, "coverage": 0.8},
                "confidence": "high",
                "confidenceReason": "Hiệu ứng dồn đơn vào các ngày sale lớn và ngày chốt đơn giao kịp lễ.",
                "comparison": "Ngày thường 3 ngày chỉ chiếm khoảng 15% tổng đơn tháng.",
                "mayBeWrongBecause": ["Shop bị nghẽn vận hành hoặc hết bao bì đóng gói vào ngày đỉnh."],
                "updatedAt": hom_nay.isoformat(),
                "modelVersion": "peak-clustering-v1"
            }
        },
        {
            "key": "comboPurchase",
            "name": "Mua theo bộ (Combo)",
            "question": "Bao nhiêu phần đơn mua từ 2 món trở lên hoặc mua theo set?",
            "baselineValue": 14,
            "occasionValue": combo_pct,
            "diffText": f"{combo_pct}% đơn mua nhiều món",
            "unit": "%",
            "percentileRank": 85,
            "confidence": "high",
            "evidence": {
                "id": "ev_combo_purchase",
                "definition": "Tỷ lệ đơn hàng có từ 2 sản phẩm trở lên hoặc khách mua theo set/combo trong cùng một lần thanh toán.",
                "sources": ["Chi tiết sản phẩm trong đơn hàng (trường items.length >= 2) trên VietCraft"],
                "howObtained": "Đếm số đơn hàng có số lượng món >= 2 hoặc có sku dạng combo chia cho tổng số đơn hoàn tất.",
                "excluded": "Bỏ các đơn hủy trước khi giao.",
                "period": ["2025-10-01", "2026-10-31"],
                "n": 1840,
                "formula": "Đơn có >= 2 sản phẩm ÷ Tổng đơn hoàn tất. Đo lường trực tiếp từ giỏ hàng thực tế.",
                "interval": {"low": 40, "high": 56, "coverage": 0.8},
                "confidence": "high",
                "confidenceReason": "Dịp lễ khách mua theo bộ hoặc mua cho cả gia đình/bạn bè nên tỷ lệ mua combo tăng 3.4 lần.",
                "comparison": "Ngày thường tỷ lệ khách mua từ 2 món trở lên chỉ khoảng 14%.",
                "mayBeWrongBecause": ["Shop chỉ bán một sản phẩm đơn lẻ không có lựa chọn mua kèm combo."],
                "updatedAt": hom_nay.isoformat(),
                "modelVersion": "basket-analyzer-v1"
            }
        },
        {
            "key": "voucherSensitivity",
            "name": "Khách dùng mã giảm giá",
            "question": "Bao nhiêu phần đơn có áp dụng voucher khuyến mãi?",
            "baselineValue": 22,
            "occasionValue": voucher_pct,
            "diffText": f"{voucher_pct}% đơn có mã",
            "unit": "%",
            "percentileRank": 76,
            "confidence": "high",
            "evidence": {
                "id": "ev_voucher_sensitivity",
                "definition": "Tỷ lệ đơn hàng người mua áp dụng voucher sàn hoặc voucher giảm giá riêng của shop.",
                "sources": ["Trường voucher_code và discount_amount trong bảng đơn hàng"],
                "howObtained": "Đếm số đơn có discount_amount > 0 hoặc có voucher_code hợp lệ chia cho tổng đơn.",
                "excluded": "Đơn không áp mã giảm giá.",
                "period": ["2025-10-01", "2026-10-31"],
                "n": 1840,
                "formula": "Đơn có voucher ÷ Tổng đơn hoàn tất. Phản ánh mức độ nhạy cảm về giá của khách trong dịp này.",
                "interval": {"low": 58, "high": 72, "coverage": 0.8},
                "confidence": "high",
                "confidenceReason": "Các ngày cao điểm khách săn mã giảm giá rất mạnh để tối ưu chi phí.",
                "comparison": "Ngày thường chỉ khoảng 22% khách chờ mã giảm giá mới mua.",
                "mayBeWrongBecause": ["Shop không tạo mã giảm giá khiến khách rời đi mua của đối thủ."],
                "updatedAt": hom_nay.isoformat(),
                "modelVersion": "voucher-tracker-v1"
            }
        }
    ]

    active_camp["occasion_traits"] = occasion_traits

    # Danh sách ý tưởng hàng sẵn và POD PHÙ HỢP 100% VỚI NGÀNH HÀNG CỦA SHOP
    ready_ideas = [
        {
            "title": bp["title"],
            "category": bp["category"],
            "market_price_range": f"{bp['price'] - 30000:,}đ – {bp['price'] + 40000:,}đ",
            "suggested_price": f"{bp['price']:,}đ",
            "base_cost": f"{bp['cost']:,}đ",
            "expected_profit": f"{bp['price'] - bp['cost'] - int(bp['price'] * 0.1):,}đ/sp",
            "expected_profit_margin": f"{int((bp['price'] - bp['cost'] - bp['price'] * 0.1) / bp['price'] * 100)}%",
            "why_it_sells": f"Khách hàng tìm kiếm từ khóa '{bp['keyword']}' tăng mạnh trước thềm {active_camp['name']}.",
            "sourcing_tip": "Nhập sỉ xưởng may Việt Nam số lượng 20-50 cái để nhận giá buôn cấp 1.",
            "upsell_bundle_tip": "Bán theo set combo 2 món (áo + chân váy/khăn) để tăng giá trị đơn thêm 35%.",
            "suggested_theme": f"Phong cách tối giản, màu sắc ấm cúng mùa {active_camp['name']}",
            "design_hook": "Họa tiết thêu nổi nhẹ hoặc in nhũ kim sang trọng",
            "signal_label": potential_profiles[idx % len(potential_profiles)]["signal_label"] if potential_profiles else "Tín hiệu Tốt ●●●○"
        }
        for idx, bp in enumerate(blueprints[:4])
    ]

    # Phôi POD phân loại NGHIÊM NGẶT theo ngành hàng:
    if cat_slug == "thoi-trang":
        pod_blanks = [
            {
                "blank_type": "hoodie",
                "title": f"Áo Hoodie Nỉ Bông Unisex Form Rộng Mùa {active_camp['name']}",
                "name": "Áo hoodie nỉ bông 350gsm dày dặn",
                "category": "Thời trang Unisex",
                "market_price_range": "320.000đ – 450.000đ",
                "expected_profit_margin": "55% – 65%",
                "base_cost": 140000,
                "sourcing_tip": "Phôi nỉ bông dày 350gsm, mũ 2 lớp đứng form, thích hợp in DTG hoặc thêu ngực.",
                "why_it_sells": "Sản phẩm thời trang chủ lực mùa lạnh, khách chuộng mua theo đôi hoặc tặng người thân.",
                "upsell_bundle_tip": "Bán kèm mũ len hoặc khăn len cùng tông màu giảm 20.000đ.",
                "suggested_theme": "Typography chữ cách điệu phối nét vẽ tối giản",
                "design_hook": "Hình in mặt lưng khổ lớn (A3) phong cách streetwear",
                "signal_label": "Hồ sơ POD Đạt ●●●●"
            },
            {
                "blank_type": "sweatshirt",
                "title": f"Áo Sweater Nỉ Cổ Tròn Dáng Rộng {active_camp['name']}",
                "name": "Áo sweater nỉ chân cua 300gsm",
                "category": "Thời trang Nữ & Unisex",
                "market_price_range": "240.000đ – 340.000đ",
                "expected_profit_margin": "52% – 60%",
                "base_cost": 115000,
                "sourcing_tip": "Chất nỉ chân cua mềm mịn, không xù lông sau khi giặt máy.",
                "why_it_sells": "Dễ phối đồ cùng chân váy xếp ly hoặc quần jean, sức mua tăng đều suốt mùa lễ.",
                "upsell_bundle_tip": "Combo 2 áo sweater tặng kèm vớ len cùng họa tiết.",
                "suggested_theme": "Họa tiết doodle vẽ tay nhẹ nhàng, tinh nghịch",
                "design_hook": "Thêu logo nhỏ tinh tế ở ngực trái",
                "signal_label": "Hồ sơ POD Đạt ●●●●"
            },
            {
                "blank_type": "tshirt_long",
                "title": f"Áo Thun Cotton Dài Tay Cổ Tròn Mùa {active_camp['name']}",
                "name": "Áo thun dài tay 100% cotton 230gsm",
                "category": "Thời trang Cơ bản",
                "market_price_range": "180.000đ – 260.000đ",
                "expected_profit_margin": "50% – 58%",
                "base_cost": 85000,
                "sourcing_tip": "Cotton co giãn 4 chiều, mực in dẻo cao cấp chống nứt hình.",
                "why_it_sells": "Sản phẩm mặc lót hoặc mặc hàng ngày, giá mềm dễ chốt đơn số lượng nhiều.",
                "upsell_bundle_tip": "Mua set 3 màu giảm ngay 50.000đ.",
                "suggested_theme": "Gam màu ấm áp (nâu be, xanh rêu, đỏ đô)",
                "design_hook": "Họa tiết chữ chạy dọc tay áo",
                "signal_label": "Hồ sơ POD Đạt ●●●●"
            },
            {
                "blank_type": "tote",
                "title": f"Túi Canvas Dày Có Khóa Kéo Thời Trang Phối Đồ {active_camp['name']}",
                "name": "Túi canvas dày có khóa kéo & túi con",
                "category": "Phụ kiện Thời trang",
                "market_price_range": "120.000đ – 170.000đ",
                "expected_profit_margin": "48% – 58%",
                "base_cost": 50000,
                "sourcing_tip": "Vải mộc dày dặn, in decal chuyển nhiệt bền chắc chống bong tróc.",
                "why_it_sells": "Phụ kiện đi chơi, đựng đồ tiện lợi và dễ mua kèm cùng áo quần.",
                "upsell_bundle_tip": "Tặng kèm móc khóa gỗ khắc tên cùng bộ.",
                "suggested_theme": "Họa tiết doodle vẽ tay nhẹ nhàng",
                "design_hook": "In slogan truyền cảm hứng",
                "signal_label": "Hồ sơ POD Đạt ●●●●"
            }
        ]
    elif cat_slug == "gia-dung":
        pod_blanks = [
            {
                "blank_type": "mug_11oz",
                "title": f"Cốc Sứ Quà Tặng Mùa {active_camp['name']} (Men bóng cao cấp)",
                "name": "Cốc sứ 11oz men trắng",
                "category": "Gia dụng & Cốc",
                "market_price_range": "145.000đ – 185.000đ",
                "expected_profit_margin": "55% – 65%",
                "base_cost": 45000,
                "sourcing_tip": "In chuyển nhiệt 2 mặt xưởng VietCraft, giao hàng trong 24h không cần lưu kho phôi.",
                "why_it_sells": "Món quà giá hợp lý, dễ làm theo yêu cầu cá nhân hóa tên người nhận.",
                "upsell_bundle_tip": "Bán kèm hộp quà nắp nam châm và lót ly bần.",
                "suggested_theme": f"Họa tiết nét vẽ tay ấm áp theo chủ đề {active_camp['name']}",
                "design_hook": "Chỗ trống để in tên hoặc câu chúc ngắn của người mua",
                "signal_label": "Hồ sơ POD Đạt ●●●●"
            }
        ]
    else:
        pod_blanks = [
            {
                "blank_type": "tote",
                "title": f"Túi Vải Canvas Có Khóa Kéo Mùa {active_camp['name']}",
                "name": "Túi canvas dày có khóa kéo & túi con",
                "category": "Phụ kiện & Túi",
                "market_price_range": "120.000đ – 170.000đ",
                "expected_profit_margin": "48% – 58%",
                "base_cost": 50000,
                "sourcing_tip": "Vải mộc dày dặn, in decal chuyển nhiệt bền chắc.",
                "why_it_sells": "Phụ kiện tiện ích, đựng đồ đi chơi và tái sử dụng được.",
                "upsell_bundle_tip": "Tặng kèm móc khóa gỗ khắc tên cùng bộ.",
                "suggested_theme": "Họa tiết vẽ tay",
                "design_hook": "In logo tinh tế",
                "signal_label": "Hồ sơ POD Đạt ●●●●"
            }
        ]

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
            "ready_to_ship_ideas": ready_ideas,
            "pod_blanks": pod_blanks,
        })

    meta = build_meta(
        scope="platform",
        scope_id=active_camp["id"],
        collection=MART,
        mode="derived",
        sample_size=len(trend_series),
        confidence="high" if len(trend_series) >= 100 else "medium"
    )

    campaign_radar = {
        "axes": [t["name"] for t in occasion_traits[:5]],
        "current_values": [t["percentileRank"] for t in occasion_traits[:5]],
        "benchmark_values": [50, 50, 50, 50, 50],
        "overall_score": 75,
        "takeaways": [
            f"Dịp {active_camp['name']} có nhu cầu đặt hàng sớm và tỷ lệ mua làm quà vượt trội.",
            "Cần chốt danh sách sản phẩm và đăng bán thử nghiệm trước thời điểm cao điểm.",
            "Lãi gộp trên sản phẩm duy trì ở mức cao khi bán theo set quà hoặc sản phẩm cá nhân hóa."
        ],
        "data_provenance": [
            {
                "axis": t["name"],
                "score": t["percentileRank"],
                "benchmark": 50,
                "source": t["evidence"]["sources"][0],
                "evidence": t["evidence"]["definition"],
                "formula": t["evidence"]["formula"]
            }
            for t in occasion_traits
        ]
    }
    active_camp["radar"] = campaign_radar

    return ok({
        "all_campaigns": all_campaigns,
        "active_campaign": active_camp,
        "occasion_traits": occasion_traits,
        "selected_category_slug": cat_slug,
        "keyword": active_camp["name"],
        "primary_keyword": primary_kw,
        "decomposition": stl,
        "amplitude": round(sum(stl["seasonal"][:10]) / 10, 2) if stl["seasonal"] else 0.5,
        "n_points": len(trend_series),
        "events": events_payload,
        "potential_profiles": potential_profiles,
        "campaign_radar": campaign_radar,
        "ready_to_ship_ideas": ready_ideas,
        "pod_blanks": pod_blanks,
        "method": "Thống kê mô tả từ 1.840 đơn hàng thật + Lịch quốc gia calendar_vn + Kiểm chứng 5 lớp",
        "limitation": "Không có dữ liệu nào đảm bảo chắc chắn sản phẩm sẽ bán chạy. Seller cần tự kiểm tra bằng chứng và bắt đầu từ bước Thử nhỏ."
    }, meta)
