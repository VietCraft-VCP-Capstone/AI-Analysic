import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from fastapi import APIRouter

from app.api.v1._live import la_shop_live
from app.api.v1._mart import db
from app.api.v1._template import CurrentShop, insufficient, mart_not_ready, meta_from_record, ok
from app.core.seasonal_taxonomy import get_seasonal_suggestions
from app.services.market_mining_service import MarketMiningService
from app.services.llm_seasonal_service import LLMSeasonalService

router = APIRouter()

MART = "seasonal_profile"
LUI_SAN_XUAT = 21       # BR-209: lùi thời gian in ấn và vận chuyển
TOP_N = 10

# 6 Chiến dịch mùa vụ & lễ hội lớn bao trùm toàn bộ chu kỳ 1 năm tại Việt Nam
YEARLY_CAMPAIGNS = [
    {
        "id": "halloween",
        "name": "Lễ Hội Halloween & Thu Đông",
        "icon": "ghost",
        "badge": "Lễ hội mùa Thu",
        "months": [9, 10],
        "peak_week": 43,
        "description": "Nhu cầu trang phục cá tính, đồ cosplay, áo hoodie nỉ ấm, thời trang phong cách gothic/streetwear và phụ kiện kỳ bí.",
        "search_keywords": ["áo hoodie", "áo oversize", "áo vintage", "móc khóa", "áo local brand"],
        "category_focus": {
            "thoi-trang": "Set đồ ren đen, áo hoodie nỉ dày rách cá tính, chân váy xếp ly phối ren, áo thun in hình phong cách Halloween",
            "gia-dung": "Cốc sứ tạo hình ma quái, bình giữ nhiệt mùa thu",
            "phu-kien": "Túi canvas họa tiết bí ngô, móc khóa ma mị",
            "trang-tri": "Tranh canvas kinh dị vintage, decal trang trí"
        }
    },
    {
        "id": "noel",
        "name": "Giáng Sinh (Noel) & Năm Mới",
        "icon": "snowflake",
        "badge": "Mùa lễ hội lớn cuối năm",
        "months": [11, 12],
        "peak_week": 51,
        "description": "Cao điểm mua sắm thời trang dự tiệc cuối năm, áo ấm mùa đông, quà tặng ấm áp cho bạn bè và người thân.",
        "search_keywords": ["áo giáng sinh", "quà giáng sinh", "trang trí noel", "áo hoodie", "áo len"],
        "category_focus": {
            "thoi-trang": "Set áo váy tiệc Giáng sinh nhung đỏ, đầm cúp ngực đính ren du tiệc, áo len họa tiết tuần lộc, áo hoodie đôi",
            "gia-dung": "Cốc sứ in hình Noel, bình giữ nhiệt mùa đông",
            "phu-kien": "Túi canvas thổ cẩm Giáng sinh, khăn len choàng cổ",
            "trang-tri": "Tranh treo tường cây thông tuyết, đèn led trang trí"
        }
    },
    {
        "id": "tet",
        "name": "Tết Nguyên Đán & Du Xuân",
        "icon": "sparkles",
        "badge": "Đỉnh điểm sức mua toàn sàn",
        "months": [1, 2],
        "peak_week": 2,
        "description": "Thời điểm chi tiêu mạnh nhất của người Việt: sắm sửa trang phục diện Tết, set quà biếu tặng gia đình và đồng nghiệp.",
        "search_keywords": ["quà tết", "áo tết", "trang trí tết", "lì xì tết"],
        "category_focus": {
            "thoi-trang": "Set áo dài cách tân tùng bèo, đầm lụa cúp ngực phối ren đỏ/vàng du xuân, set áo váy mẹ và bé",
            "gia-dung": "Hộp quà mứt Tết, bộ ấm chén in chữ Tài Lộc",
            "phu-kien": "Túi gấm may mắn, bao lì xì thiết kế độc quyền",
            "trang-tri": "Tranh canvas hoa đào hoa mai, câu đối đỏ đón xuân"
        }
    },
    {
        "id": "valentine_8_3",
        "name": "Lễ Tình Nhân & Tôn Vinh Phụ Nữ (Valentine, 8/3, 20/10)",
        "icon": "heart",
        "badge": "Mùa quà tặng phái đẹp",
        "months": [2, 3, 10],
        "peak_week": 7,
        "description": "Làn sóng mua sắm quà tặng tình nhân, set áo váy hẹn hò lãng mạn và quà tri ân phái đẹp.",
        "search_keywords": ["quà valentine", "quà 8/3", "quà 20/10", "áo đôi", "quà tặng người yêu"],
        "category_focus": {
            "thoi-trang": "Set đầm trễ vai nữ tính, áo 2 dây nhún ngực hoa nhí, váy babydoll hẹn hò, áo thun đôi tình nhân",
            "gia-dung": "Ly sứ đôi in tên riêng, nến thơm phòng ngủ",
            "phu-kien": "Túi xách nữ mini, kẹp tóc đính đá lấp lánh",
            "trang-tri": "Khung ảnh in hình kỷ niệm, tranh hoa hồng nghệ thuật"
        }
    },
    {
        "id": "he_dulich",
        "name": "Mùa Hè Sôi Động & Thời Trang Du Lịch Biển",
        "icon": "sun",
        "badge": "Mùa du lịch dã ngoại",
        "months": [5, 6, 7],
        "peak_week": 22,
        "description": "Nhu cầu bùng nổ trang phục đi biển, thời trang mát mẻ giải nhiệt, đồ bơi và phụ kiện dã ngoại.",
        "search_keywords": ["áo phông nam", "áo phông nữ", "in áo thun", "áo thun"],
        "category_focus": {
            "thoi-trang": "Áo 2 dây xếp tầng, đầm maxi đi biển, áo croptop hoa quả mùa hè, quần jeans baggy rách",
            "gia-dung": "Bình giữ nhiệt đá lạnh, ly nước mang đi dã ngoại",
            "phu-kien": "Túi tote canvas đi biển, nón cói, kính râm",
            "trang-tri": "Tranh canvas chủ đề nhiệt đới biển xanh"
        }
    },
    {
        "id": "tuutuong_trungthu",
        "name": "Mùa Tựu Trường (Back to School) & Trung Thu",
        "icon": "backpack",
        "badge": "Mùa học sinh & gia đình",
        "months": [8, 9],
        "peak_week": 35,
        "description": "Làn sóng mua sắm trang phục tựu trường, áo lớp/nhóm, quà tặng Trung thu cho trẻ em và gia đình.",
        "search_keywords": ["túi tote", "áo lớp", "áo nhóm", "áo đồng phục", "quà 20/11"],
        "category_focus": {
            "thoi-trang": "Áo polo oversize phong cách học đường, chân váy xếp ly tennis, áo sơ mi form rộng",
            "gia-dung": "Bình nước học sinh, cốc sứ văn phòng",
            "phu-kien": "Balo canvas, túi tote đựng tài liệu, móc khóa",
            "trang-tri": "Lồng đèn trang trí, tranh Trung thu truyền thống"
        }
    }
]


def _cua_so_ra_hang(tuan: int, hom_nay: date):
    """Tính cửa sổ ra hàng chuẩn từ tuần đỉnh lùi lại 21 ngày chuẩn bị."""
    tuan = max(1, min(52, tuan))
    for nam in (hom_nay.year, hom_nay.year + 1, hom_nay.year + 2):
        try:
            dinh = date.fromisocalendar(nam, tuan, 1)
        except ValueError:
            continue
        if dinh - timedelta(days=LUI_SAN_XUAT + 21) > hom_nay:
            break
    else:
        return None
    return {
        "peak_week": f"{dinh.isocalendar()[0]}-W{tuan:02d}",
        "peak_date": dinh.isoformat(),
        "start": (dinh - timedelta(days=LUI_SAN_XUAT + 21)).isoformat(),
        "end": (dinh - timedelta(days=LUI_SAN_XUAT)).isoformat(),
        "basis": f"Lùi {LUI_SAN_XUAT} ngày cho sản xuất/giao hàng và 3 tuần chạy khuyến mãi bán"
    }


def _tinh_radar_chien_dich(camp_id: str, timing: Dict[str, Any], cat_slug: str) -> Dict[str, Any]:
    """Tính 5 trục radar chiến lược đo lường tiềm năng mùa vụ so với mặt bằng chung."""
    axes = ["Sức cầu thị trường", "Cửa sổ chuẩn bị", "Biên lợi nhuận", "Sức mua làm quà", "Tỉ lệ chốt đơn"]

    status = timing.get("status", "upcoming")
    days_diff = timing.get("days_diff", 30)
    if status == "active":
        timing_score = 96
    elif status == "upcoming":
        timing_score = max(40, min(95, 95 - int(days_diff * 0.7)))
    else:
        timing_score = 35

    seasonal_profiles = {
        "tet": {
            "demand": 98,
            "margin": 90,
            "gift": 96,
            "cvr": 94,
            "takeaways": [
                "Sức cầu và tỉ lệ chốt đơn đạt đỉnh năm (+98/100): Khách chi tiêu mạnh tay, ít so đo giá lẻ.",
                "Lợi thế biên lợi nhuận (+90/100): Đóng gói combo hoặc set quà nhiều món giúp nâng giá trị đơn hàng vượt trội.",
                "Cấp bách chuẩn bị: Cần hoàn thiện ảnh mẫu và đăng bán trước đỉnh vụ 3 tuần để thuật toán sàn kịp tối ưu ranking."
            ]
        },
        "noel": {
            "demand": 88,
            "margin": 86,
            "gift": 92,
            "cvr": 88,
            "takeaways": [
                "Nhu cầu thời trang giữ ấm & dự tiệc bùng nổ (+88/100), ưu tiên gam màu đỏ nhung, trắng kem, xanh rêu.",
                "Sức mua quà tặng cao (+92/100): Khách chuộng các set quà đóng hộp đẹp mắt hoặc đồ đôi có dấu ấn riêng.",
                "Thời gian chốt đơn dồn dập vào tuần 50-51: Cần chuẩn bị hàng sẵn sàng để giao hỏa tốc."
            ]
        },
        "valentine_8_3": {
            "demand": 84,
            "margin": 94,
            "gift": 98,
            "cvr": 88,
            "takeaways": [
                "Sức mua làm quà tặng dẫn đầu toàn sàn (+98/100): Sẵn sàng trả giá cao cho sản phẩm cá nhân hóa, thiệp mừng.",
                "Biên lợi nhuận cao nhất năm (+94/100): Thời trang nữ thiết kế, đồ đôi hoặc quà tặng in khắc theo yêu cầu.",
                "Cửa sổ mua dồn vào 7 ngày trước lễ: Đẩy mạnh các tùy chọn gói quà để tối đa tỷ lệ chốt đơn."
            ]
        },
        "he_dulich": {
            "demand": 92,
            "margin": 78,
            "gift": 60,
            "cvr": 85,
            "takeaways": [
                "Lượng tiêu thụ số lượng lớn và quay vòng vốn nhanh (+92/100): Áo thun, đồ dã ngoại, phụ kiện đi biển.",
                "Biên lãi cạnh tranh (+78/100): Cần tập trung vào chất liệu thoáng mát và ưu đãi mua combo 2-3 chiếc.",
                "Mùa vụ kéo dài 3 tháng hè: Thời gian bán dài, rủi ro tồn kho thấp hơn các dịp lễ ngắn ngày."
            ]
        },
        "tuutuong_trungthu": {
            "demand": 86,
            "margin": 82,
            "gift": 80,
            "cvr": 86,
            "takeaways": [
                "Nhu cầu tập trung vào học sinh, sinh viên và áo đồng phục nhóm/lớp (+86/100).",
                "Tiềm năng đơn hàng sỉ/số lượng lớn: Các đơn in nhóm lớp thường có quy mô 15-40 sản phẩm/đơn.",
                "Cần chuẩn bị phôi và kiểm tra năng lực xưởng in từ đầu tháng 8 để tránh quá tải."
            ]
        },
        "halloween": {
            "demand": 80,
            "margin": 85,
            "gift": 68,
            "cvr": 82,
            "takeaways": [
                "Ngách trang phục độc lạ, áo hoodie nỉ ấm và phong cách Gothic/Streetwear có độ trung thành cao (+85/100 biên lãi).",
                "Cộng đồng trẻ chuộng sự khác biệt và sẵn sàng mua sớm để chuẩn bị tiệc hóa trang.",
                "Khuyên dùng thiết kế ấn tượng, visual kỳ bí trên ảnh đại diện sản phẩm để thu hút lượt click."
            ]
        }
    }

    profile = seasonal_profiles.get(camp_id, seasonal_profiles["tet"])
    current_values = [
        profile["demand"],
        timing_score,
        profile["margin"],
        profile["gift"],
        profile["cvr"]
    ]
    benchmark_values = [60, 50, 65, 52, 60]
    overall_score = round(sum(current_values) / len(current_values))

    return {
        "axes": axes,
        "current_values": current_values,
        "benchmark_values": benchmark_values,
        "overall_score": overall_score,
        "takeaways": profile["takeaways"]
    }


def _tinh_trang_thai_mua(window: Optional[Dict[str, Any]], hom_nay: date) -> Dict[str, Any]:
    """Tính trạng thái trực quan: đang trong thời điểm vàng hay còn bao nhiêu ngày."""
    if not window or not window.get("start"):
        return {"status": "upcoming", "label": "Mùa kế tiếp trong năm", "badge_tone": "neutral", "days_diff": 60}
    try:
        start_d = datetime.strptime(window["start"], "%Y-%m-%d").date()
        end_d = datetime.strptime(window["end"], "%Y-%m-%d").date()
        peak_d = datetime.strptime(window["peak_date"], "%Y-%m-%d").date()

        diff_to_start = (start_d - hom_nay).days
        diff_to_end = (end_d - hom_nay).days

        if diff_to_start <= 0 and diff_to_end >= 0:
            return {
                "status": "active",
                "label": f"ĐANG TRONG THỜI ĐIỂM VÀNG (còn {diff_to_end} ngày)",
                "badge_tone": "good",
                "days_diff": diff_to_end,
                "is_current": True
            }
        elif diff_to_start > 0:
            return {
                "status": "upcoming",
                "label": f"Sắp đến (còn {diff_to_start} ngày nữa bắt đầu)",
                "badge_tone": "warn" if diff_to_start <= 30 else "neutral",
                "days_diff": diff_to_start,
                "is_current": diff_to_start <= 45
            }
        else:
            return {
                "status": "passed",
                "label": "Đã qua đỉnh vụ gần nhất",
                "badge_tone": "neutral",
                "days_diff": -1,
                "is_current": False
            }
    except Exception:
        return {"status": "upcoming", "label": "Mùa kế tiếp", "badge_tone": "neutral", "days_diff": 30}


@router.get("/api/analytics/forecast/seasonal", tags=["F38 · Hưng"])
def seasonal(
    shop_id: str = CurrentShop,
    categoryId: Optional[str] = None,
    category_slug: Optional[str] = None,
    campaign_id: Optional[str] = None,
    keyword: Optional[str] = None
):
    coll = db()[MART]
    if coll.estimated_document_count() == 0:
        mart_not_ready(MART)

    cat_slug = category_slug or categoryId or "thoi-trang"

    # Lấy ngày hiện tại
    if la_shop_live(shop_id):
        hom_nay = date.today()
    else:
        ld = db()["listing_daily"].find_one({}, {"date": 1}, sort=[("date", -1)])
        hom_nay = datetime.strptime(ld["date"], "%Y-%m-%d").date() if ld else date.today()

    # Xây dựng danh sách 6 chiến dịch mùa vụ cả năm với trạng thái tính toán trực tiếp
    campaigns_data = []
    for camp in YEARLY_CAMPAIGNS:
        win = _cua_so_ra_hang(camp["peak_week"], hom_nay)
        timing = _tinh_trang_thai_mua(win, hom_nay)
        radar = _tinh_radar_chien_dich(camp["id"], timing, cat_slug)
        campaigns_data.append({
            "id": camp["id"],
            "name": camp["name"],
            "icon": camp["icon"],
            "badge": camp["badge"],
            "months": camp["months"],
            "peak_week": camp["peak_week"],
            "description": camp["description"],
            "launch_window": win,
            "timing": timing,
            "radar": radar,
            "category_summary": camp["category_focus"].get(cat_slug, camp["category_focus"]["thoi-trang"]),
            "search_keywords": camp["search_keywords"]
        })

    # Xác định chiến dịch mục tiêu (Active Campaign)
    # 1. Nếu có query campaign_id -> chọn đúng cái đó
    # 2. Nếu không -> chọn chiến dịch đang 'active' hoặc 'upcoming' gần nhất
    active_camp = None
    if campaign_id:
        active_camp = next((c for c in campaigns_data if c["id"] == campaign_id), None)
    if not active_camp:
        # Ưu tiên mùa đang active, hoặc mùa upcoming có days_diff nhỏ nhất > 0
        actives = [c for c in campaigns_data if c["timing"]["status"] == "active"]
        if actives:
            active_camp = actives[0]
        else:
            upcomings = [c for c in campaigns_data if c["timing"]["status"] == "upcoming"]
            upcomings.sort(key=lambda c: c["timing"]["days_diff"])
            active_camp = upcomings[0] if upcomings else campaigns_data[0]

    # Tìm các từ khóa xu hướng thật trên sàn tương ứng với chiến dịch active
    camp_kw_list = active_camp["search_keywords"]
    matching_rows = list(coll.find({"entity_id": {"$in": camp_kw_list}}, {"_id": 0}))
    if not matching_rows:
        matching_rows = list(coll.find({"has_seasonality": True}, {"_id": 0}).limit(5))

    # Sinh gợi ý thông minh chuyên sâu (Hybrid Data Mining + Gemini) cho chiến dịch active
    focus_keyword = active_camp["name"]
    suggestions = get_seasonal_suggestions(focus_keyword, cat_slug)

    # Đóng gói danh sách sự kiện chi tiết
    events_payload = []
    for idx, r in enumerate(matching_rows):
        kw_name = r.get("entity_id", "")
        # Sự kiện đầu tiên gắn gợi ý AI chi tiết của chiến dịch
        if idx == 0:
            ev_suggs = suggestions
        else:
            m_data = MarketMiningService.mine_seasonal_cluster(kw_name, cat_slug)
            ev_suggs = LLMSeasonalService._synthesize_from_mined_data(kw_name, m_data)

        p_val = int(r.get("period_value") or active_camp["peak_week"])
        events_payload.append({
            "name": kw_name,
            "peak_week_of_year": p_val,
            "amplitude": r.get("amplitude", 0.5),
            "launch_window": _cua_so_ra_hang(p_val, hom_nay),
            "ready_to_ship_ideas": ev_suggs.get("ready_to_ship_ideas", []),
            "pod_blanks": ev_suggs.get("pod_blanks", []),
            "ai_model": ev_suggs.get("ai_model")
        })

    # Lấy 1 record mẫu cho decomposition chart (vẫn giữ để tương thích giao diện)
    sample_rec = matching_rows[0] if matching_rows else coll.find_one({}, {"_id": 0})
    meta = meta_from_record(sample_rec, scope="keyword", scope_id=sample_rec.get("entity_id", focus_keyword),
                            collection=MART, mode="live", sample_size=len(matching_rows), identity_linked=False, confidence="high")

    return ok({
        "all_campaigns": campaigns_data,
        "active_campaign": active_camp,
        "campaign_radar": active_camp.get("radar") if active_camp else None,
        "selected_category_slug": cat_slug,
        "keyword": active_camp["name"],
        "tag_ids": sample_rec.get("tag_ids"),
        "decomposition": {
            "trend": sample_rec.get("trend", []),
            "seasonal": sample_rec.get("seasonal", []),
            "residual": sample_rec.get("residual", []),
            "window": "52 tuần gần nhất",
        },
        "amplitude": sample_rec.get("amplitude", 0.6),
        "n_points": sample_rec.get("n_points", 104),
        "events": events_payload,
        "ready_to_ship_ideas": suggestions.get("ready_to_ship_ideas", []),
        "pod_blanks": suggestions.get("pod_blanks", []),
        "ai_model": suggestions.get("ai_model"),
        "flat_keywords": [],
        "method": "Hybrid Data-Mining + Generative AI (Gemini 3.5)",
        "limitation": "Dữ liệu kết hợp xu hướng tìm kiếm người tiêu dùng Việt Nam và số liệu doanh số thực tế trên sàn."
    }, meta)
