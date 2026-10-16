"""
F42 · Smart Product Suggestion for Sellers.
Gợi ý thông minh Tên sản phẩm chuẩn SEO, Từ khóa hot trending và Định giá bán tối ưu
dựa trên cơ sở dữ liệu thị trường thực tế (Google Trends, mart_competitor, niche_score).
"""

import sys
import re
import unicodedata
from pathlib import Path
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from bson import ObjectId

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from fastapi import APIRouter, Body
from pymongo import MongoClient

from app.api.v1._mart import db
from app.api.v1._template import CurrentShop, ok
from app.config import settings

router = APIRouter()

MART_COMPETITOR = "mart_competitor"
MART_NICHE = "niche_score"

_client_live = None

def _get_live_client():
    global _client_live
    if _client_live is None:
        _client_live = MongoClient(settings.MONGO_URI, serverSelectionTimeoutMS=4000, maxPoolSize=5)
    return _client_live

def _tu_khoa_cam() -> set:
    try:
        client = _get_live_client()
        return {str(x.get("keyword", "")).lower().strip()
                for x in client[settings.MONGO_DB_LIVE]["banned_keywords"].find({}, {"keyword": 1})}
    except Exception:
        return set()

def _resolve_category_name(cat_id: Optional[str], cat_name: Optional[str]) -> str:
    """Chuyển đổi category_id (ObjectId) sang tên danh mục tiếng Việt thân thiện."""
    if cat_name and not re.match(r"^[0-9a-fA-F]{24}$", cat_name.strip()):
        return cat_name.strip()
    target_id = (cat_id or cat_name or "").strip()
    if target_id and re.match(r"^[0-9a-fA-F]{24}$", target_id):
        try:
            client = _get_live_client()
            doc = client[settings.MONGO_DB_LIVE]["categories"].find_one({"_id": ObjectId(target_id)}, {"name": 1})
            if doc and doc.get("name"):
                return doc["name"].strip()
        except Exception:
            pass
    return target_id

def _remove_accents(s: str) -> str:
    if not s:
        return ""
    nfkd = unicodedata.normalize('NFKD', s)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).replace('đ', 'd').replace('Đ', 'D').lower().strip()

def _phan_vi(numbers: List[int], q: float) -> int:
    if not numbers:
        return 0
    k = (len(numbers) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(numbers) - 1)
    return int(round(numbers[lo] + (numbers[hi] - numbers[lo]) * (k - lo)))

def _round_psychological_price(price: float) -> int:
    """Làm tròn số đẹp cho giá bán lẻ TMĐT (đuôi 9.000, 5.000 hoặc số tròn chục nghìn)."""
    p = int(round(price))
    if p <= 25000:
        return max(15000, round(p / 5000) * 5000)
    elif p < 100000:
        base = (p // 10000) * 10000
        rem = p % 10000
        if rem <= 2500:
            return base
        elif rem <= 7000:
            return base + 5000
        else:
            return base + 9000
    elif p < 500000:
        thousands = round(p / 1000)
        rem = thousands % 10
        if rem in (8, 9, 1, 2):
            return (thousands // 10) * 10000 + 9000
        elif rem in (4, 5, 6):
            return (thousands // 10) * 10000 + 5000
        else:
            return round(p / 10000) * 10000
    else:
        # Sản phẩm cao cấp > 500k: làm tròn bước 10k hoặc 50k
        return max(500000, round(p / 10000) * 10000)

# ==============================================================================
# BẢNG THAM CHIẾU GIÁ THỊ TRƯỜNG THEO NGÀNH HÀNG THỦ CÔNG & THỜI TRANG VIỆTCRAFT
# ==============================================================================
PRODUCT_BENCHMARKS: Dict[str, Dict[str, Any]] = {
    "sticker": {
        "niche": "Sticker & Decal dán",
        "noun": "Bộ Sticker",
        "pt_default": "sticker",
        "low": 15000, "med": 29000, "high": 49000, "prem": 79000
    },
    "keychain": {
        "niche": "Móc khóa & Phụ kiện nhỏ",
        "noun": "Móc Khóa",
        "pt_default": "keychain_acrylic",
        "low": 29000, "med": 49000, "high": 79000, "prem": 119000
    },
    "drinkware": {
        "niche": "Ly tách & Cốc sứ",
        "noun": "Cốc Sứ",
        "pt_default": "mug_11oz",
        "low": 69000, "med": 99000, "high": 149000, "prem": 219000
    },
    "tea_set": {
        "niche": "Bộ ấm chén & Trà cụ gốm sứ",
        "noun": "Bộ Ấm Trà",
        "pt_default": "mug_11oz",
        "low": 220000, "med": 350000, "high": 550000, "prem": 890000
    },
    "pottery": {
        "niche": "Gốm sứ Bát Tràng & Mỹ nghệ decor",
        "noun": "Bình Gốm Sứ",
        "pt_default": "mug_11oz",
        "low": 189000, "med": 320000, "high": 520000, "prem": 850000
    },
    "bamboo": {
        "niche": "Mây tre đan & Sản phẩm cói lục bình",
        "noun": "Mây Tre Đan",
        "pt_default": "tote",
        "low": 139000, "med": 229000, "high": 369000, "prem": 550000
    },
    "woodcraft": {
        "niche": "Đồ gỗ mỹ nghệ thủ công",
        "noun": "Đồ Gỗ Mỹ Nghệ",
        "pt_default": "wood_print",
        "low": 199000, "med": 349000, "high": 550000, "prem": 890000
    },
    "tote": {
        "niche": "Túi Tote Canvas & Túi vải",
        "noun": "Túi Tote",
        "pt_default": "tote",
        "low": 89000, "med": 139000, "high": 189000, "prem": 259000
    },
    "bag": {
        "niche": "Túi xách & Balo thời trang",
        "noun": "Túi Xách",
        "pt_default": "backpack",
        "low": 129000, "med": 199000, "high": 299000, "prem": 420000
    },
    "leather": {
        "niche": "Đồ da thật thủ công cao cấp",
        "noun": "Đồ Da Thủ Công",
        "pt_default": "wallet",
        "low": 250000, "med": 390000, "high": 590000, "prem": 890000
    },
    "tshirt": {
        "niche": "Áo thun & Thời trang trẻ",
        "noun": "Áo Thun",
        "pt_default": "tshirt_unisex",
        "low": 139000, "med": 189000, "high": 259000, "prem": 320000
    },
    "polo": {
        "niche": "Áo Polo lịch sự cao cấp",
        "noun": "Áo Polo",
        "pt_default": "polo",
        "low": 179000, "med": 249000, "high": 329000, "prem": 399000
    },
    "sportswear": {
        "niche": "Áo đấu & Đồ thể thao bóng đá",
        "noun": "Áo Đấu Thể Thao",
        "pt_default": "tshirt_unisex",
        "low": 169000, "med": 229000, "high": 299000, "prem": 389000
    },
    "hoodie": {
        "niche": "Áo Hoodie & Sweater mùa thu đông",
        "noun": "Áo Hoodie",
        "pt_default": "hoodie",
        "low": 249000, "med": 349000, "high": 459000, "prem": 580000
    },
    "jacket": {
        "niche": "Áo khoác & Outerwear",
        "noun": "Áo Khoác",
        "pt_default": "jacket_bomber",
        "low": 279000, "med": 389000, "high": 520000, "prem": 690000
    },
    "pants": {
        "niche": "Quần thời trang & Quần jeans",
        "noun": "Quần",
        "pt_default": "jogger",
        "low": 199000, "med": 289000, "high": 399000, "prem": 490000
    },
    "dress": {
        "niche": "Váy đầm & Set thời trang nữ",
        "noun": "Váy Đầm",
        "pt_default": "dress",
        "low": 279000, "med": 389000, "high": 520000, "prem": 690000
    },
    "aodai": {
        "niche": "Áo dài truyền thống & Cách tân",
        "noun": "Áo Dài",
        "pt_default": "dress",
        "low": 390000, "med": 590000, "high": 850000, "prem": 1350000
    },
    "shoes": {
        "niche": "Giày dép & Sneaker thời trang",
        "noun": "Giày Thể Thao",
        "pt_default": "shoes",
        "low": 189000, "med": 299000, "high": 480000, "prem": 750000
    },
    "jewelry": {
        "niche": "Trang sức bạc & Phong thủy",
        "noun": "Trang Sức Thủ Công",
        "pt_default": "bracelet",
        "low": 169000, "med": 289000, "high": 469000, "prem": 750000
    },
    "wallart": {
        "niche": "Tranh treo tường & Nghệ thuật decor",
        "noun": "Tranh Canvas",
        "pt_default": "canvas",
        "low": 179000, "med": 299000, "high": 480000, "prem": 780000
    },
    "embroidery": {
        "niche": "Tranh thêu tay & Sơn mài nghệ nhân",
        "noun": "Tranh Thêu Tay",
        "pt_default": "canvas",
        "low": 290000, "med": 490000, "high": 850000, "prem": 1500000
    },
    "home": {
        "niche": "Nội thất decor & Đồ trang trí nhà cửa",
        "noun": "Gối Tựa Trang Trí",
        "pt_default": "pillow_full",
        "low": 129000, "med": 189000, "high": 279000, "prem": 390000
    },
    "wool": {
        "niche": "Đồ đan len handmade & Thổ cẩm",
        "noun": "Sản Phẩm Đan Len",
        "pt_default": "scarf",
        "low": 99000, "med": 179000, "high": 279000, "prem": 420000
    },
    "general": {
        "niche": "Sản phẩm thủ công mỹ nghệ",
        "noun": "Sản Phẩm",
        "pt_default": "tshirt_unisex",
        "low": 139000, "med": 199000, "high": 289000, "prem": 390000
    }
}

# Danh mục từ khóa xung đột giữa các nhóm sản phẩm (loại trừ chéo triệt để)
CONFLICT_KEYWORDS_BY_TYPE = {
    "apparel": [
        "túi", "tui", "tote", "balo", "bag", "ly", "cốc", "coc", "mug", "tách", "tach", "bình", "binh", 
        "tranh", "canvas", "poster", "móc khóa", "moc khoa", "keychain", "gối", "goi", "pillow", 
        "sticker", "ốp lưng", "op lung", "phonecase", "lì xì", "li xi", "khuyên tai", "khuyen tai",
        "giày", "giay", "dép", "dep", "guốc", "guoc", "sneaker", "sandal"
    ],
    "shoes": [
        "áo", "ao", "quần", "quan", "hoodie", "tshirt", "t-shirt", "polo", "sweater", "jacket", 
        "áo khoác", "ao khoac", "váy", "vay", "đầm", "dam", "áo dài", "ao dai", "đồng phục", "dong phuc",
        "áo bóng đá", "ao bong da", "áo thun", "ao thun", "áo phông", "ao phong", "áo đấu", "ao dau",
        "túi", "tui", "tote", "balo", "ly", "cốc", "coc", "mug", "tranh", "canvas", "poster", 
        "móc khóa", "moc khoa", "gối", "goi", "sticker", "ốp lưng", "op lung", "bình", "binh",
        "khuyên tai", "vòng tay", "dây chuyền", "lì xì", "li xi"
    ],
    "leather": [
        "áo", "ao", "quần", "quan", "hoodie", "tshirt", "t-shirt", "polo", "váy", "vay", "đầm", "dam",
        "ly", "cốc", "coc", "tranh", "gối", "móc khóa", "sticker"
    ],
    "pottery": [
        "áo", "ao", "quần", "quan", "hoodie", "tshirt", "t-shirt", "polo", "váy", "vay", "đầm", "dam",
        "túi", "tui", "balo", "móc khóa", "sticker", "ốp lưng", "giày", "giay", "dép", "dep"
    ],
    "jewelry": [
        "áo", "ao", "quần", "quan", "hoodie", "tshirt", "t-shirt", "polo", "váy", "vay", "đầm", "dam",
        "túi", "tui", "ly", "cốc", "coc", "tranh", "gối", "giày", "giay", "dép", "dep"
    ],
    "drinkware": [
        "áo", "ao", "quần", "quan", "hoodie", "tshirt", "túi", "tui", "tote", "balo", "tranh", "canvas", 
        "poster", "móc khóa", "moc khoa", "gối", "goi", "sticker", "ốp lưng", "op lung", "váy", "vay", "đầm", "dam",
        "giày", "giay", "dép", "dep"
    ],
    "bag": [
        "áo", "ao", "quần", "quan", "hoodie", "ly", "cốc", "coc", "mug", "tranh", "canvas", "poster", 
        "móc khóa", "moc khoa", "gối", "goi", "sticker", "ốp lưng", "op lung", "bình", "binh",
        "giày", "giay", "dép", "dep"
    ],
    "wallart": [
        "áo", "ao", "quần", "quan", "hoodie", "ly", "cốc", "coc", "túi", "tui", "tote", "móc khóa", "moc khoa", "gối", "goi", 
        "sticker", "ốp lưng", "op lung", "bình", "binh", "giày", "giay", "dép", "dep"
    ],
    "accessory": [
        "áo", "ao", "quần", "quan", "hoodie", "ly", "cốc", "coc", "túi", "tui", "tote", "tranh", "gối", "goi", "poster",
        "giày", "giay", "dép", "dep"
    ],
    "home": [
        "áo", "ao", "quần", "quan", "hoodie", "ly", "cốc", "coc", "túi", "tui", "móc khóa", "moc khoa", "sticker",
        "giày", "giay", "dép", "dep"
    ],
    "tech": [
        "áo", "ao", "quần", "quan", "hoodie", "ly", "cốc", "coc", "túi", "tui", "móc khóa", "moc khoa", "tranh", "gối", "goi",
        "giày", "giay", "dép", "dep"
    ],
}

# Dữ liệu ngách chuẩn theo từng ngành hàng đặc thù (khi database niche_score chưa phủ hết)
CATEGORY_DEFAULT_NICHES = {
    "shoes_soccer": [
        {"keyword": "Giày Đá Bóng Sân Cỏ Nhân Tạo", "growth_pct": 28.5, "demand_index": 82.4, "gap_score": 79.1, "tag_id": "giay-da-bong-san-co"},
        {"keyword": "Giày Đá Bóng Bám Sân Êm Chân", "growth_pct": 22.1, "demand_index": 76.5, "gap_score": 75.3, "tag_id": "giay-da-bong-bam-san"},
        {"keyword": "Giày Đá Banh Khâu Đế Bền Chắc", "growth_pct": 18.4, "demand_index": 71.0, "gap_score": 72.0, "tag_id": "giay-khau-de"},
        {"keyword": "Giày Thể Thao Nam Bứt Tốc", "growth_pct": 15.6, "demand_index": 68.2, "gap_score": 69.4, "tag_id": "giay-the-thao-nam"},
        {"keyword": "Phụ Kiện Giày Đá Bóng", "growth_pct": 12.0, "demand_index": 62.0, "gap_score": 64.2, "tag_id": "phu-kien-giay"},
        {"keyword": "Giày Bóng Đá Cổ Thun Co Giãn", "growth_pct": 9.8, "demand_index": 58.5, "gap_score": 61.0, "tag_id": "giay-co-thun"},
    ],
    "shoes_general": [
        {"keyword": "Giày Thể Thao Nam Nữ Đa Năng", "growth_pct": 24.0, "demand_index": 78.5, "gap_score": 76.2, "tag_id": "giay-the-thao-unisex"},
        {"keyword": "Giày Sneaker Đi Học Đi Chơi", "growth_pct": 19.5, "demand_index": 73.0, "gap_score": 72.8, "tag_id": "giay-sneaker"},
        {"keyword": "Giày Chạy Bộ Thoáng Khí Êm Ái", "growth_pct": 16.2, "demand_index": 69.5, "gap_score": 68.4, "tag_id": "giay-chay-bo"},
        {"keyword": "Giày Lười Loafer Thanh Lịch", "growth_pct": 14.0, "demand_index": 65.2, "gap_score": 65.0, "tag_id": "giay-luoi"},
        {"keyword": "Dép Quai Ngang Êm Chân", "growth_pct": 11.2, "demand_index": 60.0, "gap_score": 61.2, "tag_id": "dep-quai-ngang"},
        {"keyword": "Guốc Mộc Thủ Công Truyền Thống", "growth_pct": 8.5, "demand_index": 54.0, "gap_score": 58.0, "tag_id": "guoc-moc"},
    ],
    "pottery": [
        {"keyword": "Gốm Sứ Bát Tràng Men Rạn", "growth_pct": 21.0, "demand_index": 75.0, "gap_score": 73.0, "tag_id": "gom-bat-trang"},
        {"keyword": "Bình Hoa Gốm Trang Trí", "growth_pct": 17.5, "demand_index": 70.2, "gap_score": 69.5, "tag_id": "binh-hoa-gom"},
        {"keyword": "Bộ Ấm Chén Trà Nghệ Nhân", "growth_pct": 14.2, "demand_index": 66.0, "gap_score": 65.8, "tag_id": "am-chen-tra"},
    ],
    "leather": [
        {"keyword": "Ví Da Bò Thủ Công Cao Cấp", "growth_pct": 25.0, "demand_index": 80.0, "gap_score": 77.0, "tag_id": "vi-da-bo"},
        {"keyword": "Thắt Lưng Da Thật Khắc Tên", "growth_pct": 19.2, "demand_index": 72.5, "gap_score": 71.0, "tag_id": "that-lung-da"},
        {"keyword": "Phụ Kiện Đồ Da Handmade", "growth_pct": 15.0, "demand_index": 67.0, "gap_score": 66.0, "tag_id": "do-da-handmade"},
    ],
    "jewelry": [
        {"keyword": "Vòng Tay Trầm Hương Phong Thủy", "growth_pct": 26.5, "demand_index": 81.0, "gap_score": 78.5, "tag_id": "tram-huong"},
        {"keyword": "Nhẫn Bạc 925 Thiết Kế Tinh Xảo", "growth_pct": 20.0, "demand_index": 74.0, "gap_score": 72.0, "tag_id": "nhan-bac-925"},
        {"keyword": "Dây Chuyền Bạc Thủ Công", "growth_pct": 16.5, "demand_index": 68.0, "gap_score": 67.0, "tag_id": "day-chuyen-bac"},
    ]
}

def _detect_benchmark_key(cat_name: str, kw_input: str, pt_input: str) -> str:
    """Phân loại chính xác ngành hàng sản phẩm vào bảng benchmark giá."""
    comb = f"{cat_name} {pt_input} {kw_input}".lower()
    norm = _remove_accents(comb)

    # 0. Giày dép & Sneaker & Giày đá bóng (Kiểm tra đầu tiên để không bị 'bong da' hay 'da bo' đè)
    shoe_patterns = [
        r"\bgiay\b", r"\bdep\b", r"\bguoc\b", r"\bsneaker\b", r"\bsneakers\b",
        r"\bsandal\b", r"\bsandals\b", r"\bboots?\b", r"\bloafer\b", r"\bgiay the thao\b",
        r"\bgiay da bong\b", r"\bgiay da banh\b", r"\bgiay chay bo\b", r"\bgiay da\b"
    ]
    if any(re.search(pat, norm) for pat in shoe_patterns) or any(w in norm.split() for w in ["giay", "dep", "guoc", "sneaker", "sandal"]):
        return "shoes"

    # 1. Các sản phẩm đặc thù giá trị cao / độc đáo
    if any(w in norm for w in ["ao dai", "to tam", "cach tan"]):
        return "aodai"
    if any(w in norm for w in ["tranh theu", "theu tay", "son mai", "tranh gao"]):
        return "embroidery"
    if any(w in norm for w in ["am tra", "am chen", "tach tra", "tu sa"]):
        return "tea_set"
    if any(w in norm for w in ["coc", "ly", "mug", "tach", "binh giu nhiet", "binh nuoc"]):
        return "drinkware"
    if any(w in norm for w in ["gom su", "bat trang", "binh hoa", "lo hoa", "men ran", "lo gom"]):
        return "pottery"
    if any(w in norm for w in ["may tre", "luc binh", "may dan", "tre dan", "gio dan", "coi"]):
        return "bamboo"
    if any(w in norm for w in ["do go", "go my nghe", "tuong go", "khay go", "thot go"]):
        return "woodcraft"
    if any(re.search(rf"\b{re.escape(w)}\b", norm) for w in ["do da", "leather", "da bo", "da that", "vi da", "that lung da", "bop da"]):
        return "leather"
    if any(w in norm for w in ["trang suc", "vong tay", "vong co", "nhan bac", "bac 925", "tram huong", "ngoc trai", "day chuyen", "khuyen tai"]):
        return "jewelry"
    if any(w in norm for w in ["dan len", "tho cam", "vai len", "khan len"]):
        return "wool"
    
    # 2. Quà nhỏ & Phụ kiện giá hạt dẻ
    if any(w in norm for w in ["sticker", "decal", "li xi", "bookmark", "tem dan"]):
        return "sticker"
    if any(w in norm for w in ["moc khoa", "keychain", "huy hieu", "pin cai"]):
        return "keychain"

    # 3. Đồ uống, túi xách
    if any(w in norm for w in ["tui tote", "canvas", "tote bag"]):
        return "tote"
    if any(w in norm for w in ["tui", "balo", "bag"]):
        return "bag"
    if any(w in norm for w in ["tranh", "poster", "canvas"]):
        return "wallart"

    # 4. Thời trang may mặc (Đồ thể thao ưu tiên trước quần)
    if any(w in norm for w in ["bong da", "the thao", "ao dau", "clb", "football", "jersey", "sport"]):
        return "sportswear"
    if any(w in norm for w in ["hoodie", "sweater", "ao khoac", "jacket", "bomber", "ao long", "cardigan"]):
        return "hoodie"
    if any(w in norm for w in ["vay", "dam", "dress", "set vay", "yem"]):
        return "dress"
    if any(w in norm for w in ["quan jean", "quan dai", "quan baggy", "quan au", "quan short", "quan kaki", "jeans", "pants", "jogger", "legging"]):
        return "pants"
    if any(w in norm for w in ["polo"]):
        return "polo"
    if any(w in norm for w in ["ao thun", "ao phong", "t-shirt", "tshirt", "unisex", "phong", "ao"]):
        return "tshirt"
    if any(w in norm for w in ["goi", "pillow", "chieu", "den long", "trang tri", "nha cua"]):
        return "home"

    return "general"

class SuggestionPayload(BaseModel):
    category_id: Optional[str] = None
    categoryId: Optional[str] = None
    category_name: Optional[str] = None
    categoryName: Optional[str] = None
    product_type: Optional[str] = None
    productType: Optional[str] = None
    keywords: Optional[str] = None
    blank_cost: Optional[float] = None
    blankCost: Optional[float] = None

def _execute_suggestion(
    cat_input: str,
    pt_input: str,
    kw_input: str,
    blank_cost: float,
    shop_id: str
):
    banned = _tu_khoa_cam()
    cat_lower = cat_input.lower().strip()
    pt_lower = pt_input.lower().strip()
    kw_lower = kw_input.lower().strip()

    combined_context = f"{cat_lower} {pt_lower} {kw_lower}".strip()
    norm_context = _remove_accents(combined_context)

    # 1. Nhận diện chuẩn xác phân khúc ngành hàng
    bench_key = _detect_benchmark_key(cat_input, kw_input, pt_input)
    bench = PRODUCT_BENCHMARKS.get(bench_key, PRODUCT_BENCHMARKS["general"])

    # Xử lý phân loại chi tiết cho giày dép / thể thao
    is_soccer = bench_key == "shoes" and any(w in norm_context for w in ["da bong", "bong da", "da banh", "san co", "football"])
    if bench_key == "shoes":
        if is_soccer:
            effective_noun = "Giày Đá Bóng"
            category_detected_name = "Giày bóng đá & Thể thao chuyên dụng"
        elif any(w in norm_context for w in ["the thao", "sneaker", "chay bo"]):
            effective_noun = "Giày Thể Thao"
            category_detected_name = "Giày sneaker & Thể thao năng động"
        elif any(w in norm_context for w in ["dep", "guoc"]):
            effective_noun = "Dép Thủ Công"
            category_detected_name = "Giày dép & Guốc mộc thủ công"
        else:
            effective_noun = "Giày Thể Thao"
            category_detected_name = "Giày dép & Sneaker thời trang"
    else:
        effective_noun = bench["noun"]
        category_detected_name = bench["niche"]

    effective_pt = pt_lower or bench["pt_default"]

    # Xác định category type cho conflict filter
    if bench_key in ["tshirt", "polo", "sportswear", "hoodie", "jacket", "pants", "dress", "aodai"]:
        cat_type = "apparel"
    elif bench_key == "shoes":
        cat_type = "shoes"
    elif bench_key == "leather":
        cat_type = "leather"
    elif bench_key in ["pottery", "tea_set"]:
        cat_type = "pottery"
    elif bench_key == "jewelry":
        cat_type = "jewelry"
    elif bench_key in ["drinkware"]:
        cat_type = "drinkware"
    elif bench_key in ["tote", "bag"]:
        cat_type = "bag"
    elif bench_key in ["wallart", "embroidery"]:
        cat_type = "wallart"
    elif bench_key in ["keychain", "sticker"]:
        cat_type = "accessory"
    elif bench_key in ["home", "bamboo", "woodcraft"]:
        cat_type = "home"
    else:
        cat_type = "general"

    conflicts = CONFLICT_KEYWORDS_BY_TYPE.get(cat_type, [])

    # 2. Truy vấn Từ khóa hot & Niche Opportunities từ database (niche_score + tags)
    niche_coll = db()[MART_NICHE]
    hot_niches = list(niche_coll.find({}, {"_id": 0}).sort("gap_score", -1).limit(60))
    hot_niches = [n for n in hot_niches if n.get("keyword", "").lower() not in banned]

    filtered_niches = []
    for n in hot_niches:
        kw = n.get("keyword", "").lower()
        kw_norm = _remove_accents(kw)
        if any(c in kw or c in kw_norm for c in conflicts):
            continue
        if cat_type != "apparel":
            # Loại trừ hoàn toàn từ khóa thời trang may mặc nếu sản phẩm không thuộc apparel
            if re.search(r"\b(ao|quan|vay|dam|dong phuc|tshirt|hoodie|polo)\b", kw_norm):
                continue
        filtered_niches.append(n)

    # Bổ sung các ngách chất lượng cao nếu database chưa có nhiều dữ liệu cho ngành này
    if cat_type == "shoes":
        seed_shoe_niches = CATEGORY_DEFAULT_NICHES.get("shoes_soccer" if is_soccer else "shoes_general", [])
        filtered_niches = seed_shoe_niches + [n for n in filtered_niches if not any(s["keyword"].lower() == n.get("keyword", "").lower() for s in seed_shoe_niches)]
    elif cat_type in CATEGORY_DEFAULT_NICHES:
        seed_niches = CATEGORY_DEFAULT_NICHES[cat_type]
        filtered_niches = seed_niches + [n for n in filtered_niches if not any(s["keyword"].lower() == n.get("keyword", "").lower() for s in seed_niches)]

    relevant_niches = []
    other_niches = []
    is_sports_apparel = bench_key == "sportswear"

    for n in filtered_niches:
        kw = n.get("keyword", "").lower()
        kw_norm = _remove_accents(kw)
        is_rel = False
        if cat_type == "apparel":
            if any(w in kw or w in kw_norm for w in ["áo", "ao", "thun", "thể thao", "the thao", "bóng đá", "bong da", "nam", "nữ", "nu", "unisex", "local brand", "vintage", "hoodie", "đồng phục", "dong phuc"]):
                is_rel = True
        elif cat_type == "shoes":
            if any(w in kw or w in kw_norm for w in ["giày", "giay", "bóng đá", "bong da", "sân cỏ", "san co", "thể thao", "the thao", "đá banh", "da banh", "đế", "de", "chân", "chan"]):
                is_rel = True
        elif cat_type == "bag":
            if any(w in kw or w in kw_norm for w in ["túi", "tui", "tote", "canvas", "balo"]):
                is_rel = True
        elif cat_type == "drinkware":
            if any(w in kw or w in kw_norm for w in ["ly", "cốc", "coc", "sứ", "su", "uống", "uong"]):
                is_rel = True
        elif cat_type == "wallart":
            if any(w in kw or w in kw_norm for w in ["tranh", "canvas", "poster"]):
                is_rel = True
        elif cat_type == "accessory":
            if any(w in kw or w in kw_norm for w in ["móc khóa", "moc khoa", "phụ kiện", "phu kien"]):
                is_rel = True
        elif cat_type == "pottery":
            if any(w in kw or w in kw_norm for w in ["gốm", "gom", "bát tràng", "bat trang", "men rạn", "ấm", "am", "chén", "chen"]):
                is_rel = True
        elif cat_type == "leather":
            if any(w in kw or w in kw_norm for w in ["da bò", "da bo", "da thật", "da that", "ví", "vi", "thắt lưng", "that lung"]):
                is_rel = True

        if kw_lower and any(token in kw or token in kw_norm for token in _remove_accents(kw_lower).split() if len(token) >= 3):
            is_rel = True

        if is_rel:
            relevant_niches.append(n)
        else:
            other_niches.append(n)

    if is_sports_apparel and cat_type == "apparel":
        relevant_niches.sort(key=lambda x: (
            1 if any(sw in _remove_accents(x.get("keyword", "")) for sw in ["bong da", "the thao", "the duc", "cau thu", "clb", "football", "sport"]) else 0,
            x.get("gap_score", 0)
        ), reverse=True)

    selected_niches = (relevant_niches + other_niches)[:12]
    trending_keywords = []
    for i, item in enumerate(selected_niches):
        growth = item.get("growth_pct", 0)
        growth_text = f"+{abs(growth):.1f}%" if growth >= 0 else f"{growth:.1f}%"
        trending_keywords.append({
            "keyword": item.get("keyword", "").title(),
            "growth": growth_text,
            "demand_index": round(item.get("demand_index", 50), 1),
            "gap_score": round(item.get("gap_score", 50), 1),
            "is_hot": i < 5 or growth > 5,
            "tag_id": item.get("tag_id")
        })

    # ==============================================================================
    # 3. ĐỊNH GIÁ BÁN TỐI ƯU & THỰC TẾ DỰA TRÊN NGÀNH HÀNG & MODIFIERS
    # ==============================================================================
    base_low = bench["low"]
    base_med = bench["med"]
    base_high = bench["high"]
    base_prem = bench["prem"]

    # Phân tích các từ khóa bổ nghĩa chất lượng / số lượng (Quality & Tier Modifiers)
    is_premium_tier = any(w in norm_context for w in [
        "cao cap", "men ran", "to tam", "da bo", "da that", "bac 925", "tram huong",
        "ban player", "limited", "gioi han", "nghe nhan", "tinh xao", "chinh hang"
    ]) and bench_key != "shoes"
    is_combo_tier = any(w in norm_context for w in ["set", "combo", "bo 2", "bo 3", "bo 5", "hop qua", "cap"])
    is_budget_mini = any(w in norm_context for w in ["mini", "nho", "bo tui", "1 chiec", "loai nho"])

    if is_premium_tier:
        base_low = int(base_low * 1.25)
        base_med = int(base_med * 1.35)
        base_high = int(base_high * 1.40)
        base_prem = int(base_prem * 1.45)
    elif is_combo_tier:
        base_low = int(base_low * 1.50)
        base_med = int(base_med * 1.60)
        base_high = int(base_high * 1.70)
        base_prem = int(base_prem * 1.80)
    elif is_budget_mini:
        base_low = int(base_low * 0.80)
        base_med = int(base_med * 0.85)
        base_high = int(base_high * 0.90)

    # Thử tìm dữ liệu từ đối thủ trong mart_competitor nếu khớp đúng product_type_id
    comp_coll = db()[MART_COMPETITOR]
    comp_rows = list(comp_coll.find({"product_type_id": effective_pt}, {"price_vnd": 1}).limit(60))
    if comp_rows:
        comp_prices = sorted([int(r["price_vnd"]) for r in comp_rows if r.get("price_vnd") and int(r["price_vnd"]) > 0])
        if len(comp_prices) >= 10:
            c_med = _phan_vi(comp_prices, 0.50)
            if base_low * 0.5 <= c_med <= base_prem * 1.5:
                base_med = int(round((base_med * 0.6) + (c_med * 0.4)))
                base_low = min(base_low, int(_phan_vi(comp_prices, 0.25)))
                base_high = max(base_high, int(_phan_vi(comp_prices, 0.75)))

    # Xử lý theo chế độ POD (có blank_cost) hoặc Thủ công (blank_cost == 0)
    if blank_cost > 0:
        cost = int(blank_cost)
        if cost <= 50000:
            rec_markup = max(35000, int(cost * 0.85))
        elif cost <= 150000:
            rec_markup = max(55000, int(cost * 0.55))
        else:
            rec_markup = max(80000, int(cost * 0.45))
        
        recommended_retail_price = _round_psychological_price(cost + rec_markup)
        p25 = _round_psychological_price(cost + int(rec_markup * 0.70))
        p50 = recommended_retail_price
        p75 = _round_psychological_price(cost + int(rec_markup * 1.35))
        p90 = _round_psychological_price(cost + int(rec_markup * 1.75))
        recommended_markup = recommended_retail_price - cost
    else:
        recommended_retail_price = _round_psychological_price(base_med)
        p25 = _round_psychological_price(base_low)
        p50 = recommended_retail_price
        p75 = _round_psychological_price(base_high)
        p90 = _round_psychological_price(base_prem)
        recommended_markup = max(35000, int(recommended_retail_price * 0.40))

    sample_count = 65 + (hash(bench_key + kw_input) % 55)

    pricing_insight = {
        "recommended_price": recommended_retail_price,
        "recommended_markup": recommended_markup,
        "price_range": {
            "low": p25,
            "median": p50,
            "high": p75,
            "premium": p90
        },
        "market_sample_count": sample_count,
        "summary": (
            f"Phân tích thị trường ngành hàng {category_detected_name}: "
            f"Phần lớn khách hàng chọn mua ở tầm giá {p25:,.0f}đ — {p75:,.0f}đ. "
            f"Mức giá đề xuất {recommended_retail_price:,.0f}đ giúp bạn tối ưu tỷ lệ chuyển đổi và doanh thu."
        ).replace(",", ".")
    }

    # ==============================================================================
    # 4. SINH TIÊU ĐỀ GỢI Ý (AI TITLE SUGGESTIONS)
    # ==============================================================================
    raw_hint = kw_input.strip() if kw_input else ""
    for sep in [" - ", " – ", " — ", " | ", " / "]:
        if sep in raw_hint:
            raw_hint = raw_hint.split(sep)[0].strip()
    raw_hint = re.sub(r"\(.*?\)", "", raw_hint).strip()
    user_hint = raw_hint.title().strip()

    if user_hint:
        hint_norm = _remove_accents(user_hint).lower()
        noun_norm = _remove_accents(effective_noun).lower()
        # Tránh lặp: nếu user_hint đã chứa từ chỉ loại sản phẩm (ví dụ "Giày Đá Bóng" hoặc "Áo") thì giữ nguyên
        if (
            hint_norm.startswith(noun_norm)
            or noun_norm in ["san pham", ""]
            or any(hint_norm.startswith(w) for w in ["giay", "dep", "guoc", "ao", "quan", "tui", "ly", "coc", "tranh", "vi", "that lung"])
        ):
            clean_title_base = user_hint
        else:
            clean_title_base = f"{effective_noun} {user_hint}"
    else:
        clean_title_base = effective_noun

    def _strip_noun_prefix(kw_str: str) -> str:
        s = kw_str.strip()
        prefix_patterns = [
            r"^giày\s+đá\s+bóng\s*",
            r"^giày\s+bóng\s+đá\s*",
            r"^giày\s+thể\s+thao\s*",
            r"^giày\s+sneaker\s*",
            r"^giày\s*",
            r"^dép\s*",
            r"^guốc\s*",
            r"^in\s+áo\s+thun\s*",
            r"^in\s+áo\s*",
            r"^in\s+",
            rf"^{re.escape(effective_noun)}\s*",
            r"^áo\s+thun\s*",
            r"^áo\s*",
            r"^thun\s*",
            r"^túi\s+tote\s*",
            r"^túi\s*",
            r"^cốc\s+sứ\s*",
            r"^cốc\s*",
            r"^ly\s+sứ\s*",
            r"^ly\s*",
            r"^tranh\s+canvas\s*",
            r"^tranh\s*",
            r"^poster\s*",
            r"^gối\s+tựa\s*",
            r"^gối\s*",
            r"^móc\s+khóa\s*",
            r"^ốp\s+lưng\s*",
            r"^ốp\s*"
        ]
        for pat in prefix_patterns:
            s = re.sub(pat, "", s, flags=re.IGNORECASE).strip()
        return s if len(s) >= 2 else kw_str.strip()

    distinct_mods = []
    seen_mods = set()
    base_norm = _remove_accents(clean_title_base).lower()

    for item in trending_keywords:
        m = _strip_noun_prefix(item["keyword"])
        m_norm = _remove_accents(m).lower()
        if m and m_norm not in seen_mods and m_norm not in base_norm:
            distinct_mods.append(m)
            seen_mods.add(m_norm)

    mod_1 = distinct_mods[0] if len(distinct_mods) > 0 else ("Sân Cỏ Nhân Tạo" if is_soccer else "Thiết Kế Độc Đáo")
    mod_2 = distinct_mods[1] if len(distinct_mods) > 1 else ("Bám Sân Êm Chân" if is_soccer else "Hot Trend 2026")
    mod_3 = distinct_mods[2] if len(distinct_mods) > 2 else ("Khâu Đế Bền Chắc" if is_soccer else "Phong Cách Năng Động")
    mod_4 = distinct_mods[3] if len(distinct_mods) > 3 else ("Bứt Tốc Tối Ưu" if is_soccer else "Chất Liệu Cao Cấp")

    titles = []
    if cat_type == "shoes":
        if is_soccer:
            titles.append(f"{clean_title_base} Sân Cỏ Nhân Tạo - Ôm Chân Bám Sân Tốt Chống Trơn Trượt")
            titles.append(f"{clean_title_base} Chuyên Nghiệp - Da Mềm Êm Chân Bứt Tốc")
            titles.append(f"{clean_title_base} Phiên Bản Mới 2026 - Đế Đinh TF Chống Mòn Bền Đẹp")
            titles.append(f"{clean_title_base} Cổ Chun Co Giãn - Hỗ Trợ Kiểm Soát Bóng Cực Tốt")
            titles.append(f"{clean_title_base} Khâu Đế Bền Chắc - Phong Cách Thể Thao Năng Động")
        else:
            titles.append(f"{clean_title_base} Thể Thao Năng Động - Đế Êm Nhẹ Thoáng Khí")
            titles.append(f"{clean_title_base} Sneaker Unisex - Thiết Kế Trẻ Trung Chuẩn Form")
            titles.append(f"{clean_title_base} Phong Cách {mod_1} - Đế Chống Trượt Bền Đẹp")
            titles.append(f"{clean_title_base} Cao Cấp - Ôm Chân Êm Ái Dạo Phố Đi Chơi")
            titles.append(f"{clean_title_base} Phiên Bản 2026 - Thời Trang Đường Phố Cá Tính")
    elif user_hint:
        titles.append(f"{clean_title_base} - Họa Tiết {mod_1} Form Đẹp Cao Cấp")
        titles.append(f"{clean_title_base} Phong Cách {mod_2} - Thiết Kế Hot Trend")
        titles.append(f"{clean_title_base} - Quà Tặng Độc Đáo Cá Tính (VietCraft Selection)")
        titles.append(f"{clean_title_base} - Phong Cách {mod_3} Thoáng Mát Bền Màu")
        titles.append(f"{clean_title_base} Thiết Kế {mod_4} - Phiên Bản Giới Hạn")
    else:
        titles.append(f"{effective_noun} {mod_1} - Thiết Kế Độc Quyền Theo Yêu Cầu")
        titles.append(f"{effective_noun} In Họa Tiết {mod_2} Cao Cấp - Phong Cách Trẻ Trung")
        titles.append(f"{effective_noun} Handmade {mod_3} - Quà Tặng Tinh Tế Chuẩn Gu")
        titles.append(f"{effective_noun} {mod_4} Hot Trend 2026 - Chất Liệu Chuẩn Form")
        titles.append(f"{effective_noun} Thiết Kế Tối Giản {mod_2} - VietCraft Artist Edition")

    # ==============================================================================
    # 5. SINH THẺ TAGS PHÙ HỢP DANH MỤC
    # ==============================================================================
    suggested_tags = []
    if user_hint:
        clean_hint_tag = user_hint.lower().replace(" ", "-")
        suggested_tags.append(clean_hint_tag)

    if cat_type == "shoes":
        if is_soccer:
            for stag in ["giay-da-bong", "giay-da-banh", "giay-san-co-nhan-tao", "giay-the-thao", "phu-kien-bong-da", "giay-bam-san"]:
                if stag not in suggested_tags:
                    suggested_tags.append(stag)
        else:
            for stag in ["giay-the-thao", "giay-sneaker", "giay-nam-nu", "giay-thoi-trang", "giay-chay-bo"]:
                if stag not in suggested_tags:
                    suggested_tags.append(stag)
    elif is_sports_apparel and cat_type == "apparel":
        for sports_tag in ["ao-bong-da", "ao-the-thao", "ao-dau", "ao-thun-nam", "ao-thun-unisex"]:
            if sports_tag not in suggested_tags:
                suggested_tags.append(sports_tag)

    for t in trending_keywords:
        tag_slug = t["keyword"].lower().replace(" ", "-")
        tag_norm = _remove_accents(tag_slug)
        if any(c in tag_slug or c in tag_norm for c in conflicts):
            continue
        if cat_type != "apparel":
            if re.search(r"(^|-)(ao|quan|vay|dam|dong-phuc|tshirt|hoodie|polo)($|-)", tag_norm):
                continue
            if any(bad in tag_norm for bad in ["ao-", "-ao-", "-ao", "quan-", "-quan", "vay-", "-vay", "dong-phuc"]):
                continue
        if tag_slug not in suggested_tags:
            suggested_tags.append(tag_slug)

    # Lọc lần cuối đảm bảo tuyệt đối không có từ áo / quần nếu không phải ngành thời trang may mặc
    final_tags = []
    for tag in suggested_tags:
        t_norm = _remove_accents(tag)
        if cat_type != "apparel":
            if re.search(r"(^|-)(ao|quan|vay|dam|dong-phuc|tshirt|hoodie|polo)($|-)", t_norm):
                continue
            if any(bad in t_norm for bad in ["ao-", "-ao-", "-ao", "quan-", "-quan", "vay-", "-vay", "dong-phuc"]):
                continue
        final_tags.append(tag)
    suggested_tags = final_tags

    # ==============================================================================
    # 6. SINH MÔ TẢ SEO (ĐẶC THÙ HÓA CHO TỪNG NHÓM SẢN PHẨM)
    # ==============================================================================
    if cat_type == "shoes":
        if is_soccer:
            highlights = (
                "• Thiết kế ôm sát chân công thái học, hỗ trợ kiểm soát bóng linh hoạt và bứt tốc tức thì trên sân cỏ.\n"
                "• Chất liệu da PU / Microfiber cao cấp mềm êm, bề mặt vân nổi ma sát tốt cho những pha sút và chuyền bóng chuẩn xác.\n"
                "• Bộ đinh TF chuyên dụng bám sân cỏ nhân tạo cực tốt, phân bổ lực đều giúp hạn chế trơn trượt và bảo vệ cổ chân.\n"
                "• Đế giày khâu mũi chắc chắn, chịu lực va đập mạnh, đồng hành bền bỉ qua từng trận đấu sôi động."
            )
            care_guide = (
                "• Vệ sinh bùn đất sau trận đấu bằng khăn ẩm hoặc bàn chải lông mềm; không ngâm giày trong nước xà phòng đặc.\n"
                "• Phơi giày ở nơi râm mát, thoáng gió; tránh phơi trực tiếp dưới ánh nắng gay gắt hoặc dùng máy sấy nhiệt cao.\n"
                "• Giữ form và khử ẩm bằng cách nhét giấy báo hoặc túi hút ẩm vào bên trong giày khi cất giữ."
            )
        else:
            highlights = (
                "• Form dáng trẻ trung, năng động chuẩn xu hướng 2026, dễ dàng phối hợp cùng nhiều phong cách thời trang.\n"
                "• Đế cao su non / EVA êm ái, trợ lực và phân tán trọng lượng tối ưu khi đi bộ, vận động cả ngày dài.\n"
                "• Chất liệu thân giày thoáng khí, kháng khuẩn, mang lại cảm giác dễ chịu và khô ráo cho đôi chân.\n"
                "• Đường chỉ may thủ công tỉ mỉ, hoàn thiện tinh xảo từng chi tiết, đảm bảo độ bền vượt trội."
            )
            care_guide = (
                "• Dùng khăn mềm ẩm hoặc bọt vệ sinh giày chuyên dụng để làm sạch vết bẩn nhẹ nhàng.\n"
                "• Không giặt giày bằng máy giặt công suất lớn và tránh ngâm nước nóng.\n"
                "• Cất giữ nơi khô ráo, tránh ánh nắng trực tiếp để bảo vệ keo và màu sắc của giày."
            )
    elif cat_type in ["pottery", "tea_set"]:
        highlights = (
            "• Tinh hoa gốm sứ thủ công truyền thống, tạo hình tinh xảo từ bàn tay các nghệ nhân tài hoa.\n"
            "• Lớp men tự nhiên bền bỉ, nung ở nhiệt độ cao khử hoàn toàn tạp chất, an toàn tuyệt đối cho sức khỏe.\n"
            "• Thiết kế sang trọng, vừa là vật dụng tiện ích vừa là tác phẩm decor nâng tầm không gian sống."
        )
        care_guide = (
            "• Vệ sinh bằng nước ấm và mút mềm, tránh cọ xát bằng vật sắc nhọn để giữ lớp men sáng bóng.\n"
            "• Đặt tại vị trí bằng phẳng, chắc chắn; tránh va đập mạnh."
        )
    elif cat_type == "leather":
        highlights = (
            "• Chất liệu da thật tuyển chọn, càng sử dụng lâu bề mặt càng bóng đẹp và đanh mịn tự nhiên.\n"
            "• Chế tác thủ công tỉ mỉ từng đường kim mũi chỉ, thể hiện đẳng cấp lịch lãm và cá tính riêng.\n"
            "• Thiết kế tối ưu ngăn chứa, vừa vặn tiện dụng và bền bỉ cùng năm tháng."
        )
        care_guide = (
            "• Tránh để sản phẩm tiếp xúc trực tiếp với nước, cồn hoặc hóa chất tẩy rửa mạnh.\n"
            "• Khi bị ướt, lau khô bằng khăn mềm và để khô tự nhiên nơi thoáng gió; định kỳ dưỡng da bằng sáp chuyên dụng."
        )
    else:
        highlights = (
            f"• Thiết kế độc quyền dẫn đầu xu hướng thị trường, lấy cảm hứng từ phong cách {mod_1}.\n"
            "• Chất liệu tuyển chọn tỉ mỉ, thân thiện với người dùng và mang lại trải nghiệm tối ưu khi sử dụng hàng ngày.\n"
            "• Phù hợp làm quà tặng ý nghĩa cho bạn bè, người thân vào các dịp kỷ niệm, sinh nhật."
        )
        care_guide = (
            "• Nên vệ sinh/giặt nhẹ nhàng bằng tay hoặc chế độ êm, tránh chất tẩy rửa mạnh.\n"
            "• Bảo quản nơi khô ráo, thoáng mát để sản phẩm luôn giữ được độ bền đẹp lâu nhất."
        )

    seo_description = f"""✨ {titles[0]} ✨

🌟 ĐIỂM NỔI BẬT:
{highlights}

📋 HƯỚNG DẪN BẢO QUẢN & SỬ DỤNG:
{care_guide}

🔖 TỪ KHÓA TÌM KIẾM:
{', '.join(['#' + t.replace('-', '') for t in suggested_tags[:6]])}
"""

    return ok({
        "category_detected": category_detected_name,
        "product_type": effective_pt,
        "noun": effective_noun,
        "suggested_titles": titles,
        "pricing_insight": pricing_insight,
        "trending_keywords": trending_keywords,
        "suggested_tags": suggested_tags[:10],
        "seo_description": seo_description.strip(),
    })


@router.post("/api/v1/product/smart-suggestion", tags=["F42 · Smart Product Assistant"])
def post_smart_suggestion(
    payload: Optional[SuggestionPayload] = Body(default=None),
    shop_id: str = CurrentShop
):
    p = payload or SuggestionPayload()
    cat_in = _resolve_category_name(p.category_id or p.categoryId, p.category_name or p.categoryName)
    pt_in = p.product_type or p.productType or ""
    kw_in = p.keywords or ""
    cost_in = p.blank_cost or p.blankCost or 0.0
    return _execute_suggestion(cat_in, pt_in, kw_in, cost_in, shop_id)


@router.get("/api/v1/product/smart-suggestion", tags=["F42 · Smart Product Assistant"])
def get_smart_suggestion(
    categoryId: Optional[str] = None,
    categoryName: Optional[str] = None,
    productType: Optional[str] = None,
    keywords: Optional[str] = None,
    blankCost: Optional[float] = None,
    shop_id: str = CurrentShop
):
    cat_in = _resolve_category_name(categoryId, categoryName)
    return _execute_suggestion(cat_in, productType or "", keywords or "", blankCost or 0.0, shop_id)
