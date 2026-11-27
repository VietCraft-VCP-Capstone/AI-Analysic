from datetime import date, datetime, timedelta
from typing import Any, Dict, List
from zoneinfo import ZoneInfo

from app.core.category_groups import GROUP_LABELS
from app.core.order_validity import VALID_ORDER_FILTER, is_valid_demand_order  # noqa: F401

TZ_VN = ZoneInfo("Asia/Ho_Chi_Minh")
MART = "seasonal_profile"
LUI_SAN_XUAT = 18  # BR-209: lùi thời gian in ấn (4 ngày p90) + vận chuyển (4 ngày p90) + vùng đệm (2 ngày)
EXTERNAL_FRESHNESS_DAYS = 30
VC_ORDER_WINDOW_DAYS = 90

# Nhãn nhóm ngành: một bộ mã duy nhất ở app.core.category_groups
CAT_LABELS: Dict[str, str] = GROUP_LABELS

# Danh mục sản phẩm mẫu và phôi POD phân loại NGHIÊM NGẶT theo ngành hàng của shop (fallback khi DB trống)
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
        ],
    },
    "trang-tri": {
        "noel": [
            {"title": "Tranh Canvas Cây Thông Giáng Sinh Phong Cách Bắc Âu", "category": "Trang trí nhà cửa", "keyword": "trang trí noel", "price": 220000, "cost": 85000},
            {"title": "Đèn Ngủ Gỗ Khắc Hình Ngôi Làng Tuyết Phát Sáng", "category": "Đèn decor", "keyword": "đèn giáng sinh", "price": 195000, "cost": 78000},
        ],
        "tet": [
            {"title": "Khung Tranh Chữ Thư Pháp Mạ Vàng An Khang Thịnh Vượng", "category": "Trang trí nhà cửa", "keyword": "tranh tết", "price": 250000, "cost": 95000},
        ],
    },
    "phu-kien": {
        "noel": [
            {"title": "Túi Tote Canvas Dày Có Khóa Kéo Họa Tiết Mùa Đông", "category": "Phụ kiện túi", "keyword": "túi tote", "price": 145000, "cost": 55000},
            {"title": "Ví Mini Cầm Tay Vải Tweed Phối Ren Cúc Kim Loại", "category": "Phụ kiện", "keyword": "ví mini", "price": 125000, "cost": 48000},
        ],
    },
}


# Mẫu dự phòng lưu theo mã cũ của catalog; quy về nhóm ngành chuẩn
_BLUEPRINT_KEY_FOR_GROUP: Dict[str, str] = {"nha-cua-doi-song": "gia-dung", "thu-cong-qua-tang": "trang-tri"}


def blueprints_for_group(group: str) -> Dict[str, List[Dict[str, Any]]]:
    """Mẫu ý tưởng dự phòng {dịp: [...]} của đúng nhóm ngành; nhóm không có mẫu thì {} (không mượn ngành khác)."""
    return CATEGORY_OCCASION_BLUEPRINTS.get(_BLUEPRINT_KEY_FOR_GROUP.get(group, group), {})


CAT_OCCASION_KEYWORDS: Dict[str, Dict[str, str]] = {
    "thoi-trang": {
        "20/11": "khăn choàng quà tặng",
        "12/12": "áo ấm mùa đông",
        "noel": "áo len giáng sinh",
        "tet": "áo dài cách tân",
        "valentine": "áo đôi hoodie",
        "8/3": "váy đầm thời trang",
        "20/10": "áo khoác thu đông",
    },
    "sac-dep": {
        "20/11": "set dưỡng da tri ân",
        "12/12": "son môi chính hãng",
        "noel": "nước hoa mùa đông",
        "tet": "mỹ phẩm trang điểm tết",
        "valentine": "son thỏi quà tặng",
        "8/3": "hộp quà mỹ phẩm",
        "20/10": "serum chống lão hóa",
    },
    "dien-tu": {
        "20/11": "bút trình chiếu trợ giảng",
        "12/12": "tai nghe bluetooth săn sale",
        "noel": "loa bluetooth mini",
        "tet": "điện thoại phụ kiện tết",
        "valentine": "tai nghe đôi",
        "8/3": "máy sấy tóc ion âm",
        "20/10": "đồng hồ thông minh",
    },
    "nha-cua-doi-song": {
        "20/11": "bình giữ nhiệt cao cấp",
        "12/12": "đồ gia dụng thông minh",
        "noel": "cây thông đèn led trang trí",
        "tet": "khay mứt bộ bát đĩa tết",
        "valentine": "nến thơm phòng ngủ",
        "8/3": "bình hoa trang trí",
        "20/10": "chăn ga gối nệm",
    },
    "me-be": {
        "20/11": "thiệp quà tặng bé tự làm",
        "12/12": "bỉm tã sữa cho bé",
        "noel": "đồ chơi giáng sinh cho bé",
        "tet": "quần áo tết trẻ em",
        "valentine": "đồ đôi mẹ và bé",
        "8/3": "quà tặng mẹ bầu",
        "20/10": "xe đẩy bình sữa",
    },
    "bach-hoa": {
        "20/11": "hộp trà hạt dinh dưỡng",
        "12/12": "bánh kẹo ăn vặt",
        "noel": "socola giáng sinh",
        "tet": "giỏ quà tết bánh mứt hạt",
        "valentine": "hộp socola tươi",
        "8/3": "trà thảo mộc hoa cúc",
        "20/10": "yến sào dinh dưỡng",
    },
    "the-thao": {
        "20/11": "bình nước giữ nhiệt thể thao",
        "12/12": "quần áo tập gym yoga",
        "noel": "áo gió thể thao mùa đông",
        "tet": "giày chạy bộ du xuân",
        "valentine": "đồ tập đôi",
        "8/3": "thảm tập yoga",
        "20/10": "vợt cầu lông chính hãng",
    },
    "van-phong-pham": {
        "20/11": "bút ký sổ da cao cấp",
        "12/12": "sách kinh tế văn học",
        "noel": "sổ tay planner năm mới",
        "tet": "lịch để bàn bao lì xì",
        "valentine": "bookmark thiệp tình yêu",
        "8/3": "bút gel sổ tay hoa cỏ",
        "20/10": "bộ bút màu họa cụ",
    },
    "phu-kien": {
        "20/11": "cài áo mạ vàng thanh lịch",
        "12/12": "kính râm thắt lưng da",
        "noel": "khăn len mũ len noel",
        "tet": "túi xách ví cầm tay tết",
        "valentine": "nhẫn đôi lắc tay bạc",
        "8/3": "dây chuyền bạc nữ",
        "20/10": "khuyên tai bạc ngọc trai",
    },
    "thu-cong-qua-tang": {
        "20/11": "bút gỗ khắc tên tri ân",
        "12/12": "set quà tặng handmade",
        "noel": "hộp quà giáng sinh thủ công",
        "tet": "khay mứt gỗ gốm sứ tết",
        "valentine": "thiệp 3d hoa hồng handmade",
        "8/3": "nến thơm thủ công hoa khô",
        "20/10": "khung ảnh gỗ handmade",
    },
    "tong-hop": {
        "20/11": "quà tặng tri ân thầy cô",
        "12/12": "siêu sale mua sắm cuối năm",
        "noel": "đồ giáng sinh mùa lễ hội",
        "tet": "sắm tết nguyên đán",
        "valentine": "quà tặng lễ tình nhân",
        "8/3": "quà tặng ngày phụ nữ",
        "20/10": "quà tặng ngày phụ nữ việt nam",
    },
}


def cutoff_utc_dt(hom_nay: date, days_back: int) -> datetime:
    """Trả về mốc datetime bắt đầu cửa sổ `days_back` ngày tính lùi từ `hom_nay`."""
    return datetime.combine(hom_nay - timedelta(days=days_back), datetime.min.time())

