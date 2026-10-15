"""
F42 · Smart Product Suggestion for Sellers.
Gợi ý thông minh Tên sản phẩm chuẩn SEO, Từ khóa hot trending và Giá bán tối ưu
dựa trên cơ sở dữ liệu thị trường thực tế (Google Trends, mart_competitor, niche_score).
"""

import sys
import re
from pathlib import Path
from typing import List, Optional, Dict, Any
from pydantic import BaseModel

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from fastapi import APIRouter
from pymongo import MongoClient

from app.api.v1._mart import db
from app.api.v1._template import CurrentShop, ok
from app.config import settings

router = APIRouter()

MART_COMPETITOR = "mart_competitor"
MART_NICHE = "niche_score"

_client_live = None

def _tu_khoa_cam() -> set:
    global _client_live
    try:
        if _client_live is None:
            _client_live = MongoClient(settings.MONGO_URI, serverSelectionTimeoutMS=4000, maxPoolSize=5)
        return {str(x.get("keyword", "")).lower().strip()
                for x in _client_live[settings.MONGO_DB_LIVE]["banned_keywords"].find({}, {"keyword": 1})}
    except Exception:
        return set()

def _phan_vi(numbers: List[int], q: float) -> int:
    if not numbers:
        return 0
    k = (len(numbers) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(numbers) - 1)
    return int(round(numbers[lo] + (numbers[hi] - numbers[lo]) * (k - lo)))

def _round_psychological_price(price: float) -> int:
    """Làm tròn số đẹp cho giá bán lẻ TMĐT (đuôi 9.000 hoặc 0.000)."""
    p = int(round(price))
    if p < 50000:
        return max(15000, (p // 5000) * 5000)
    # tròn về đuôi 9.000 hoặc 0.000
    thousands = p // 1000
    if thousands % 10 in (7, 8, 9):
        return (thousands // 10) * 10000 + 9000
    elif thousands % 10 in (3, 4, 5):
        return (thousands // 10) * 10000 + 5000
    else:
        return (thousands // 10) * 10000 + 9000

# Mapping từ khóa danh mục sang tiếng Việt thân thiện
CATEGORY_MAP = {
    "apparel": {"name": "Thời trang & May mặc", "pt_default": "tshirt_unisex", "noun": "Áo"},
    "tshirt": {"name": "Áo thun", "pt_default": "tshirt_unisex", "noun": "Áo Thun"},
    "hoodie": {"name": "Áo Hoodie", "pt_default": "hoodie", "noun": "Áo Hoodie"},
    "drinkware": {"name": "Cốc & Ly", "pt_default": "mug_11oz", "noun": "Cốc Sứ"},
    "mug": {"name": "Ly tách & Cốc", "pt_default": "mug_11oz", "noun": "Ly Sứ"},
    "bag": {"name": "Túi xách & Balo", "pt_default": "tote", "noun": "Túi Tote"},
    "tote": {"name": "Túi Tote vải", "pt_default": "tote", "noun": "Túi Tote"},
    "wallart": {"name": "Tranh & Poster", "pt_default": "canvas", "noun": "Tranh Canvas"},
    "canvas": {"name": "Tranh Canvas", "pt_default": "canvas", "noun": "Tranh Canvas"},
    "poster": {"name": "Poster dán tường", "pt_default": "poster", "noun": "Poster"},
    "stationery": {"name": "Văn phòng phẩm & Quà tặng", "pt_default": "sticker", "noun": "Bộ Sticker"},
    "accessory": {"name": "Phụ kiện", "pt_default": "keychain_acrylic", "noun": "Móc Khóa"},
    "home": {"name": "Trang trí nhà cửa", "pt_default": "pillow_full", "noun": "Gối Tựa"},
    "tech": {"name": "Phụ kiện công nghệ", "pt_default": "phonecase_hard", "noun": "Ốp Lưng"},
}

import unicodedata

def _remove_accents(s: str) -> str:
    if not s:
        return ""
    nfkd = unicodedata.normalize('NFKD', s)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).replace('đ', 'd').replace('Đ', 'D').lower()

# Danh mục từ khóa xung đột giữa các nhóm sản phẩm (Ví dụ: Áo thì tuyệt đối không lẫn Túi, Ly, Móc khóa)
CONFLICT_KEYWORDS_BY_TYPE = {
    "apparel": [
        "túi", "tui", "tote", "balo", "bag", "ly", "cốc", "coc", "mug", "tách", "tach", "bình", "binh", 
        "tranh", "canvas", "poster", "móc khóa", "moc khoa", "keychain", "gối", "goi", "pillow", 
        "sticker", "ốp lưng", "op lung", "phonecase", "lì xì", "li xi", "vòng", "vong", "khuyên tai", "khuyen tai"
    ],
    "drinkware": [
        "áo", "ao", "quần", "quan", "hoodie", "tshirt", "túi", "tui", "tote", "balo", "tranh", "canvas", 
        "poster", "móc khóa", "moc khoa", "gối", "goi", "sticker", "ốp lưng", "op lung", "váy", "vay", "đầm", "dam"
    ],
    "bag": [
        "áo", "ao", "quần", "quan", "hoodie", "ly", "cốc", "coc", "mug", "tranh", "canvas", "poster", 
        "móc khóa", "moc khoa", "gối", "goi", "sticker", "ốp lưng", "op lung", "bình", "binh"
    ],
    "wallart": [
        "áo", "ao", "quần", "quan", "hoodie", "ly", "cốc", "coc", "túi", "tui", "tote", "móc khóa", "moc khoa", "gối", "goi", 
        "sticker", "ốp lưng", "op lung", "bình", "binh"
    ],
    "accessory": [
        "áo", "ao", "quần", "quan", "hoodie", "ly", "cốc", "coc", "túi", "tui", "tote", "tranh", "gối", "goi", "poster"
    ],
    "home": [
        "áo", "ao", "quần", "quan", "hoodie", "ly", "cốc", "coc", "túi", "tui", "móc khóa", "moc khoa", "sticker"
    ],
    "tech": [
        "áo", "ao", "quần", "quan", "hoodie", "ly", "cốc", "coc", "túi", "tui", "móc khóa", "moc khoa", "tranh", "gối", "goi"
    ],
}

def _detect_category_type(text: str) -> str:
    t = _remove_accents(text)
    if any(w in t for w in ["ao", "quan", "hoodie", "thun", "polo", "shirt", "thoi trang", "may mac", "vay", "dam", "jean", "short", "dau", "bong da", "t-shirt", "the thao", "messi", "ronaldo"]):
        return "apparel"
    if any(w in t for w in ["ly", "coc", "mug", "tach", "binh"]):
        return "drinkware"
    if any(w in t for w in ["tui", "tote", "balo", "bag"]):
        return "bag"
    if any(w in t for w in ["tranh", "poster", "canvas"]):
        return "wallart"
    if any(w in t for w in ["moc khoa", "keychain", "vong"]):
        return "accessory"
    if any(w in t for w in ["goi", "pillow"]):
        return "home"
    if any(w in t for w in ["op", "phonecase"]):
        return "tech"
    return "general"

from fastapi import APIRouter, Body

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

    # Xác định loại ngành hàng (apparel, drinkware, bag...)
    combined_context = f"{cat_lower} {pt_lower} {kw_lower}"
    cat_type = _detect_category_type(combined_context)
    conflicts = CONFLICT_KEYWORDS_BY_TYPE.get(cat_type, [])

    # 1. Tìm Product Type & Category chuẩn hóa
    matched_cat_info = None
    for k, v in CATEGORY_MAP.items():
        if (k in cat_lower or k in pt_lower or (v["noun"].lower() in cat_lower) or (v["noun"].lower() in pt_lower)
            or (_remove_accents(v["noun"]) in _remove_accents(combined_context))):
            matched_cat_info = v
            break

    if not matched_cat_info and cat_type == "apparel":
        if "đấu" in combined_context or "bóng đá" in combined_context:
            matched_cat_info = {"name": "Áo Thể Thao & Áo Đấu", "pt_default": "tshirt_unisex", "noun": "Áo Đấu"}
        elif "hoodie" in combined_context:
            matched_cat_info = CATEGORY_MAP["hoodie"]
        else:
            matched_cat_info = CATEGORY_MAP["tshirt"]

    effective_noun = matched_cat_info["noun"] if matched_cat_info else "Sản Phẩm"
    effective_pt = pt_lower or (matched_cat_info["pt_default"] if matched_cat_info else "tshirt_unisex")

    # 2. Truy vấn Từ khóa hot & Niche Opportunities từ database (niche_score + tags)
    niche_coll = db()[MART_NICHE]
    hot_niches = list(niche_coll.find({}, {"_id": 0}).sort("gap_score", -1).limit(60))
    hot_niches = [n for n in hot_niches if n.get("keyword", "").lower() not in banned]

    # Lọc bỏ TẤT CẢ từ khóa chứa từ thuộc danh mục xung đột (vd: áo đấu thì tuyệt đối không nhận túi, móc khóa, cốc...)
    filtered_niches = []
    for n in hot_niches:
        kw = n.get("keyword", "").lower()
        kw_norm = _remove_accents(kw)
        if any(c in kw or c in kw_norm for c in conflicts):
            continue
        filtered_niches.append(n)

    # Phân loại độ liên quan phù hợp với loại sản phẩm
    relevant_niches = []
    other_niches = []
    is_sports = any(w in _remove_accents(combined_context) for w in ["dau", "messi", "ronaldo", "bong da", "football", "the thao", "sport", "cau thu", "clb"])

    for n in filtered_niches:
        kw = n.get("keyword", "").lower()
        kw_norm = _remove_accents(kw)
        is_rel = False
        if cat_type == "apparel":
            if any(w in kw or w in kw_norm for w in ["áo", "ao", "thun", "thể thao", "the thao", "bóng đá", "bong da", "nam", "nữ", "nu", "unisex", "local brand", "vintage", "hoodie", "đồng phục", "dong phuc"]):
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

        if kw_lower and any(token in kw or token in kw_norm for token in _remove_accents(kw_lower).split() if len(token) >= 3):
            is_rel = True

        if is_rel:
            relevant_niches.append(n)
        else:
            other_niches.append(n)

    # Ưu tiên theo chủ đề đặc thù (bóng đá / thể thao)
    if is_sports and cat_type == "apparel":
        relevant_niches.sort(key=lambda x: (
            1 if any(sw in _remove_accents(x.get("keyword", "")) for sw in ["bong da", "the thao", "ao", "the duc"]) else 0,
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

    # 3. Phân tích Giá bán từ đối thủ thị trường (mart_competitor)
    comp_coll = db()[MART_COMPETITOR]
    query_filter: Dict[str, Any] = {}
    if effective_pt:
        query_filter["product_type_id"] = {"$regex": f"^{effective_pt}", "$options": "i"}
    
    rows = list(comp_coll.find(query_filter, {"_id": 0, "price_vnd": 1, "est_sales_90d": 1, "tags": 1}).limit(200))
    if not rows and effective_pt:
        base_pt = effective_pt.split("_")[0]
        rows = list(comp_coll.find({"product_type_id": {"$regex": f"^{base_pt}", "$options": "i"}}, {"_id": 0, "price_vnd": 1, "est_sales_90d": 1, "tags": 1}).limit(200))
    
    if not rows:
        rows = list(comp_coll.find({}, {"_id": 0, "price_vnd": 1, "est_sales_90d": 1, "tags": 1}).limit(100))

    valid_prices = sorted([int(r["price_vnd"]) for r in rows if r.get("price_vnd") and int(r["price_vnd"]) > 0])
    if not valid_prices:
        valid_prices = [150000, 180000, 200000, 220000, 250000, 280000, 320000]

    p25 = _phan_vi(valid_prices, 0.25)
    p50 = _phan_vi(valid_prices, 0.50)
    p75 = _phan_vi(valid_prices, 0.75)
    p90 = _phan_vi(valid_prices, 0.90)

    recommended_retail_price = _round_psychological_price(p50)
    recommended_markup = max(35000, recommended_retail_price - int(blank_cost)) if blank_cost > 0 else 50000
    if blank_cost > 0:
        recommended_retail_price = int(blank_cost) + recommended_markup

    pricing_insight = {
        "recommended_price": recommended_retail_price,
        "recommended_markup": recommended_markup,
        "price_range": {
            "low": p25,
            "median": p50,
            "high": p75,
            "premium": p90
        },
        "market_sample_count": len(valid_prices),
        "summary": (
            f"Phân tích từ {len(valid_prices)} sản phẩm cùng phân khúc đang bán chạy: "
            f"50% thị trường tập trung mức giá từ {p25:,.0f}đ đến {p75:,.0f}đ. "
            f"Mức giá {recommended_retail_price:,.0f}đ giúp tối ưu tỷ lệ nhấp và chuyển đổi đơn hàng."
        ).replace(",", ".")
    }

    # 4. Sinh Tiêu Đề Gợi Ý (AI Title Suggestions)
    top_kw_1 = trending_keywords[0]["keyword"] if len(trending_keywords) > 0 else "Thiết Kế Độc Đáo"
    top_kw_2 = trending_keywords[1]["keyword"] if len(trending_keywords) > 1 else "Hot Trend 2026"
    top_kw_3 = trending_keywords[2]["keyword"] if len(trending_keywords) > 2 else "Phong Cách Trẻ Trung"
    user_hint = kw_input.title().strip() if kw_input else ""

    # Tránh lặp từ như "Áo Áo Đấu Messi" hoặc "Sản Phẩm Túi Tote"
    if user_hint:
        hint_norm = _remove_accents(user_hint)
        noun_norm = _remove_accents(effective_noun)
        if hint_norm.startswith(noun_norm) or noun_norm in ["san pham", ""]:
            clean_title_base = user_hint
        else:
            clean_title_base = f"{effective_noun} {user_hint}"
    else:
        clean_title_base = effective_noun

    titles = []
    if user_hint:
        titles.append(f"{clean_title_base} - {top_kw_1} Form Đẹp Cao Cấp")
        titles.append(f"{clean_title_base} Phong Cách {top_kw_2} - Thiết Kế Hot Trend")
        titles.append(f"{clean_title_base} - Quà Tặng Độc Đáo Cá Tính (VietCraft Selection)")
        titles.append(f"{clean_title_base} {top_kw_1} - Chất Liệu Cao Cấp Bền Màu")
    else:
        titles.append(f"{effective_noun} {top_kw_1} - Thiết Kế Độc Quyền Theo Yêu Cầu")
        titles.append(f"{effective_noun} In Họa Tiết {top_kw_2} Cao Cấp - Phong Cách Trẻ Trung")
        titles.append(f"{effective_noun} Handmade {top_kw_3} - Quà Tặng Tinh Tế Chuẩn Gu")
        titles.append(f"{effective_noun} {top_kw_1} Hot Trend 2026 - Chất Liệu Thoáng Mát Chuẩn Form")
        titles.append(f"{effective_noun} Thiết Kế Tối Giản {top_kw_2} - VietCraft Artist Edition")

    # 5. Sinh Thẻ Tags phù hợp danh mục (Lọc bỏ triệt để từ khóa không cùng ngành)
    suggested_tags = []
    if user_hint:
        clean_hint_tag = user_hint.lower().replace(" ", "-")
        suggested_tags.append(clean_hint_tag)
        if is_sports and cat_type == "apparel":
            for sports_tag in ["ao-bong-da", "ao-the-thao", "ao-dau", "ao-thun-nam", "ao-thun-unisex"]:
                if sports_tag not in suggested_tags:
                    suggested_tags.append(sports_tag)

    for t in trending_keywords:
        tag_slug = t["keyword"].lower().replace(" ", "-")
        tag_norm = _remove_accents(tag_slug)
        if not any(c in tag_slug or c in tag_norm for c in conflicts):
            if tag_slug not in suggested_tags:
                suggested_tags.append(tag_slug)

    seo_description = f"""✨ {titles[0]} ✨

🌟 ĐIỂM NỔI BẬT:
• Thiết kế độc quyền dẫn đầu xu hướng thị trường, lấy cảm hứng từ phong cách {top_kw_1}.
• Công nghệ in chuyển nhiệt / kỹ thuật số hiện đại, màu sắc sắc nét, bền đẹp không bong tróc.
• Chất liệu tuyển chọn tỉ mỉ, thân thiện với người dùng và mang lại trải nghiệm tối ưu khi sử dụng hàng ngày.
• Phù hợp làm quà tặng ý nghĩa cho bạn bè, người thân vào các dịp kỷ niệm, sinh nhật.

📋 HƯỚNG DẪN BẢO QUẢN:
• Nên giặt/vệ sinh nhẹ nhàng bằng tay hoặc chế độ giặt êm, tránh chất tẩy mạnh.
• Phơi ở nơi thoáng mát, tránh ánh nắng gắt trực tiếp để giữ màu in bền lâu nhất.

🔖 TỪ KHÓA TÌM KIẾM:
{', '.join(['#' + t.replace('-', '') for t in suggested_tags[:6]])}
"""

    return ok({
        "category_detected": matched_cat_info["name"] if matched_cat_info else (cat_input or "Thủ công & Nghệ thuật"),
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
    cat_in = p.category_id or p.categoryId or p.category_name or p.categoryName or ""
    pt_in = p.product_type or p.productType or ""
    kw_in = p.keywords or ""
    cost_in = p.blank_cost or p.blankCost or 0.0
    return _execute_suggestion(cat_in, pt_in, kw_in, cost_in, shop_id)


@router.get("/api/v1/product/smart-suggestion", tags=["F42 · Smart Product Assistant"])
def get_smart_suggestion(
    categoryId: Optional[str] = None,
    productType: Optional[str] = None,
    keywords: Optional[str] = None,
    blankCost: Optional[float] = None,
    shop_id: str = CurrentShop
):
    return _execute_suggestion(categoryId or "", productType or "", keywords or "", blankCost or 0.0, shop_id)
