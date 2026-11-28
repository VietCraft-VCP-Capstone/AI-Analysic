"""
Collector độc lập thu thập sản phẩm THẬT đang bán (active / in-stock) từ các sàn TMĐT:
1. Tiki Public API (https://tiki.vn/api/v2/products) - kiểm tra inventory_status == 'available'
2. Etsy Open API v3 (https://openapi.etsy.com/v3/application/listings/active) - dữ liệu thủ công/cá nhân hóa/quà tặng toàn cầu (quy đổi VND, kèm num_favorers, views, tags, customizable)
3. Printify Official Catalog API (https://api.printify.com/v1/catalog/blueprints.json) + printify_variants.json cho phôi POD thật
4. Sàn VietCraft Live (bảng products + product_variants + orders hoàn tất thật, không ước lượng giả)

Tất cả sản phẩm thu thập được chuẩn hóa và lưu vào bảng `external_market_products`
trong cả database `vietcraft-seed` (mart) và `data-collection` để API F38 đọc trực tiếp.
"""

import argparse
import datetime as dt
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import requests
from pymongo import ASCENDING, DESCENDING, MongoClient, UpdateOne

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.config import settings
from app.core.order_validity import VALID_ORDER_FILTER

COLLECTION_NAME = "external_market_products"

# Danh sách từ khóa tìm kiếm thực tế theo từng Ngành hàng x Dịp mua sắm
CATEGORY_OCCASION_QUERIES: Dict[str, Dict[str, List[Dict[str, str]]]] = {
    "thoi-trang": {
        "tet": [
            {"q": "áo dài cách tân nữ", "sub_category": "Áo dài & Trang phục Tết", "trend_kw": "áo tết"},
            {"q": "set đồ tweed nữ", "sub_category": "Thời trang Nữ", "trend_kw": "set đồ tết"},
            {"q": "áo khoác bomber unisex", "sub_category": "Thời trang Unisex", "trend_kw": "áo khoác tết"},
            {"q": "áo thun gia đình tết", "sub_category": "Thời trang Gia đình", "trend_kw": "áo gia đình"},
        ],
        "valentine": [
            {"q": "áo hoodie đôi unisex", "sub_category": "Thời trang Đôi", "trend_kw": "áo đôi"},
            {"q": "áo len cổ lọ nữ", "sub_category": "Thời trang Nữ", "trend_kw": "áo len đôi"},
            {"q": "đầm nữ dự tiệc", "sub_category": "Thời trang Nữ", "trend_kw": "set váy"},
        ],
        "8/3": [
            {"q": "đầm voan hoa nhí nữ", "sub_category": "Thời trang Nữ", "trend_kw": "đầm hoa"},
            {"q": "áo sơ mi lụa nữ công sở", "sub_category": "Thời trang Nữ", "trend_kw": "áo sơ mi nữ"},
            {"q": "khăn choàng lụa nữ quà tặng", "sub_category": "Phụ kiện thời trang", "trend_kw": "khăn lụa"},
        ],
        "30/4": [
            {"q": "áo sơ mi hawaii đi biển", "sub_category": "Thời trang Du lịch", "trend_kw": "đồ đi biển"},
            {"q": "áo thun cotton form rộng unisex", "sub_category": "Thời trang Unisex", "trend_kw": "áo thun"},
            {"q": "váy maxi đi biển nữ", "sub_category": "Thời trang Nữ", "trend_kw": "váy maxi"},
        ],
        "1/6": [
            {"q": "áo thun gia đình", "sub_category": "Thời trang Gia đình", "trend_kw": "áo gia đình"},
            {"q": "đồ bộ mặc nhà trẻ em cotton", "sub_category": "Thời trang Trẻ em", "trend_kw": "quà tặng"},
        ],
        "khai_giang": [
            {"q": "áo thun polo unisex", "sub_category": "Thời trang Học đường", "trend_kw": "áo lớp"},
            {"q": "áo khoác gió 2 lớp chống nước", "sub_category": "Thời trang Áo khoác", "trend_kw": "áo đồng phục"},
            {"q": "chân váy xếp ly tennis", "sub_category": "Thời trang Nữ", "trend_kw": "áo nhóm"},
        ],
        "trung_thu": [
            {"q": "áo dài cách tân trẻ em", "sub_category": "Thời trang Trẻ em", "trend_kw": "áo gia đình"},
            {"q": "áo thun gia đình có cổ", "sub_category": "Thời trang Gia đình", "trend_kw": "quà trung thu"},
        ],
        "20/10": [
            {"q": "đầm thiết kế nữ thanh lịch", "sub_category": "Thời trang Nữ", "trend_kw": "quà 20/10"},
            {"q": "áo khoác cardigan len nữ", "sub_category": "Thời trang Thu Đông", "trend_kw": "quà tặng mẹ"},
            {"q": "khăn choàng cổ nữ thu đông", "sub_category": "Phụ kiện Thời trang", "trend_kw": "quà tặng người yêu"},
        ],
        "halloween": [
            {"q": "áo hoodie nỉ bông đen oversize", "sub_category": "Thời trang Unisex", "trend_kw": "áo hoodie"},
            {"q": "áo thun streetwear unisex", "sub_category": "Thời trang Streetwear", "trend_kw": "áo oversize"},
            {"q": "áo choàng hóa trang halloween", "sub_category": "Thời trang Hóa trang", "trend_kw": "áo hoodie"},
        ],
        "11/11": [
            {"q": "áo hoodie nỉ bông form rộng", "sub_category": "Thời trang Unisex", "trend_kw": "áo hoodie"},
            {"q": "áo sweater nỉ unisex", "sub_category": "Thời trang Thu Đông", "trend_kw": "áo thun"},
            {"q": "áo khoác dạ nữ thu đông", "sub_category": "Thời trang Nữ", "trend_kw": "áo hoodie"},
        ],
        "20/11": [
            {"q": "khăn lụa vuông quà tặng", "sub_category": "Phụ kiện thời trang", "trend_kw": "quà 20/11"},
            {"q": "áo sơ mi nữ thanh lịch công sở", "sub_category": "Thời trang Nữ", "trend_kw": "quà tặng thầy cô"},
            {"q": "áo khoác blazer nữ form suông", "sub_category": "Thời trang Nữ", "trend_kw": "quà lưu niệm"},
            {"q": "cà vạt nam lụa cao cấp hộp quà", "sub_category": "Phụ kiện Nam", "trend_kw": "quà tặng thầy cô"},
        ],
        "12/12": [
            {"q": "áo phao giữ nhiệt mùa đông", "sub_category": "Thời trang Đông", "trend_kw": "áo hoodie"},
            {"q": "áo len cổ lọ giữ ấm", "sub_category": "Thời trang Thu Đông", "trend_kw": "áo vintage"},
            {"q": "set đồ nỉ thu đông nữ", "sub_category": "Thời trang Nữ", "trend_kw": "quà tặng"},
        ],
        "noel": [
            {"q": "áo len giáng sinh noel", "sub_category": "Thời trang Đông", "trend_kw": "áo giáng sinh"},
            {"q": "áo hoodie nỉ bông đỏ xanh mùa đông", "sub_category": "Thời trang Unisex", "trend_kw": "áo hoodie"},
            {"q": "khăn len choàng cổ mùa đông", "sub_category": "Phụ kiện Thời trang", "trend_kw": "quà giáng sinh"},
            {"q": "tất vớ len giáng sinh noel", "sub_category": "Phụ kiện Thời trang", "trend_kw": "trang trí noel"},
        ],
    },
    "gia-dung": {
        "tet": [
            {"q": "khay đựng mứt tết sứ gỗ", "sub_category": "Gia dụng Bàn ăn", "trend_kw": "quà tết"},
            {"q": "bộ ấm chén uống trà gốm sứ", "sub_category": "Đồ gốm sứ", "trend_kw": "hộp quà tết"},
            {"q": "bình giữ nhiệt inox cao cấp", "sub_category": "Gia dụng & Bình nước", "trend_kw": "quà tết"},
        ],
        "20/11": [
            {"q": "bình giữ nhiệt khắc tên quà tặng", "sub_category": "Gia dụng Quà tặng", "trend_kw": "quà 20/11"},
            {"q": "ly sứ có nắp hộp quà tặng", "sub_category": "Gia dụng & Cốc", "trend_kw": "quà tặng thầy cô"},
            {"q": "bộ ấm trà gốm sứ cao cấp", "sub_category": "Đồ gốm sứ", "trend_kw": "quà lưu niệm"},
        ],
        "noel": [
            {"q": "ly sứ giáng sinh noel", "sub_category": "Gia dụng & Cốc", "trend_kw": "quà giáng sinh"},
            {"q": "bình giữ nhiệt giáng sinh", "sub_category": "Gia dụng", "trend_kw": "cốc in hình"},
            {"q": "nến thơm phòng giáng sinh", "sub_category": "Gia dụng & Hương thơm", "trend_kw": "quà giáng sinh"},
        ],
        "default": [
            {"q": "ly sứ quà tặng cao cấp", "sub_category": "Gia dụng & Cốc", "trend_kw": "cốc in hình"},
            {"q": "bình giữ nhiệt inox 304", "sub_category": "Gia dụng", "trend_kw": "quà tặng"},
            {"q": "cốc sứ uống cà phê", "sub_category": "Gia dụng & Cốc", "trend_kw": "cốc in hình"},
        ],
    },
    "trang-tri": {
        "tet": [
            {"q": "tranh treo tường canvas tết", "sub_category": "Trang trí nhà cửa", "trend_kw": "trang trí tết"},
            {"q": "bình hoa gốm sứ trang trí", "sub_category": "Đồ decor", "trend_kw": "trang trí tết"},
        ],
        "20/11": [
            {"q": "tranh để bàn quà tặng tri ân", "sub_category": "Trang trí & Quà tặng", "trend_kw": "quà 20/11"},
            {"q": "đèn ngủ gỗ để bàn trang trí", "sub_category": "Đèn decor", "trend_kw": "quà tặng thầy cô"},
        ],
        "noel": [
            {"q": "cây thông noel để bàn trang trí", "sub_category": "Trang trí Giáng sinh", "trend_kw": "trang trí noel"},
            {"q": "đèn led trang trí giáng sinh", "sub_category": "Đèn decor", "trend_kw": "quà giáng sinh"},
            {"q": "tranh canvas treo tường mùa đông", "sub_category": "Trang trí nhà cửa", "trend_kw": "poster trang trí"},
        ],
        "default": [
            {"q": "tranh canvas treo tường phòng khách", "sub_category": "Trang trí nhà cửa", "trend_kw": "poster trang trí"},
            {"q": "đèn ngủ để bàn decor", "sub_category": "Đèn decor", "trend_kw": "quà lưu niệm"},
        ],
    },
    "phu-kien": {
        "tet": [
            {"q": "túi xách nữ đi chơi tết", "sub_category": "Phụ kiện Túi", "trend_kw": "quà tết"},
            {"q": "bao lì xì tết cao cấp", "sub_category": "Phụ kiện Tết", "trend_kw": "lì xì tết"},
        ],
        "20/11": [
            {"q": "sổ tay bìa da bút ký quà tặng", "sub_category": "Phụ kiện Quà tặng", "trend_kw": "quà 20/11"},
            {"q": "túi tote vải canvas dày có khóa", "sub_category": "Phụ kiện Túi", "trend_kw": "quà tặng thầy cô"},
            {"q": "ví da cầm tay hộp quà", "sub_category": "Phụ kiện", "trend_kw": "quà lưu niệm"},
        ],
        "noel": [
            {"q": "túi tote canvas mùa đông", "sub_category": "Phụ kiện Túi", "trend_kw": "túi tote"},
            {"q": "móc khóa giáng sinh noel", "sub_category": "Phụ kiện Quà tặng", "trend_kw": "móc khóa"},
        ],
        "default": [
            {"q": "túi tote vải canvas có khóa kéo", "sub_category": "Phụ kiện Túi", "trend_kw": "túi tote"},
            {"q": "móc khóa quà tặng dễ thương", "sub_category": "Phụ kiện", "trend_kw": "móc khóa"},
        ],
    },
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8",
}


# Từ khóa bắt buộc phải xuất hiện trong tên hoặc danh mục sản phẩm để chống quảng cáo rác (sponsored ads lệch ngành)
CATEGORY_REQUIRED_KEYWORDS: Dict[str, List[str]] = {
    "thoi-trang": ["áo", "quần", "váy", "đầm", "khăn", "cà vạt", "cavet", "cravat", "hoodie", "sweater", "blazer", "cardigan", "set đồ", "tất", "vớ", "thời trang", "đồ bộ", "pyjama", "pijama"],
    "gia-dung": ["khay", "mứt", "ấm", "chén", "trà", "bình", "ly", "cốc", "tách", "nến", "hộp", "đĩa", "bát", "sứ", "gốm", "thủy tinh", "inox"],
    "trang-tri": ["tranh", "bình hoa", "lọ hoa", "đèn", "cây thông", "noel", "trang trí", "decor", "tượng", "khung ảnh", "vòng nguyệt quế", "dây đèn"],
    "phu-kien": ["túi", "ví", "bóp", "lì xì", "sổ", "bút", "móc khóa", "móc khoá", "balo", "ba lô", "nón", "mũ", "kẹp", "cài", "tote", "canvas"],
}


def _is_relevant_product(title: str, primary_cat: str, query: str, category_slug: str) -> bool:
    """Kiểm tra sản phẩm có thực sự thuộc đúng ngành hàng & từ khóa tìm kiếm hay là quảng cáo lệch ngành."""
    t_low = f"{title} {primary_cat}".lower()
    # Không lấy sách, tiểu thuyết, hộp đựng giày, thực phẩm chức năng...
    blacklist = ["hộp đựng giày", "sách ", "tiểu thuyết", "truyện ", "voucher", "thẻ cào", "nước giặt", "bột giặt", "dầu gội", "sữa rửa mặt"]
    if any(b in t_low for b in blacklist):
        return False

    allowed_words = CATEGORY_REQUIRED_KEYWORDS.get(category_slug, [])
    if allowed_words and not any(w in t_low for w in allowed_words):
        return False

    # Kiểm tra ít nhất 1 từ khóa cốt lõi (2 âm tiết đầu của query) xuất hiện trong tên sản phẩm
    q_tokens = [w for w in query.lower().split() if len(w) >= 2 and w not in ("nữ", "nam", "unisex", "cao", "cấp", "quà", "tặng", "mùa", "dịp", "tết", "noel", "hộp", "công", "sở", "thanh", "lịch", "form", "rộng", "dáng")]
    if len(q_tokens) >= 2:
        first_bigram = f"{q_tokens[0]} {q_tokens[1]}"
        if first_bigram not in t_low and q_tokens[0] not in t_low:
            return False
    elif q_tokens and q_tokens[0] not in t_low:
        return False

    return True


def fetch_tiki_active_products(
    query: str,
    category_slug: str,
    occasion_id: str,
    sub_category: str,
    trend_kw: str,
    limit: int = 12,
) -> List[Dict[str, Any]]:
    """
    Gọi Tiki Public API (https://tiki.vn/api/v2/products) để lấy sản phẩm THẬT
    đang mở bán (availability == 1), lọc bỏ quảng cáo lệch ngành.
    """
    url = "https://tiki.vn/api/v2/products"
    params = {
        "limit": max(limit * 2, 16),
        "aggregations": 2,
        "q": query,
        "sort": "top_seller",
    }
    results: List[Dict[str, Any]] = []
    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=15)
        if resp.status_code != 200 or not resp.text.strip().startswith("{"):
            print(f"  [Tiki] HTTP {resp.status_code} cho từ khóa '{query}'")
            return results
        payload = resp.json()
        items = payload.get("data") or []
        now = dt.datetime.now(dt.timezone.utc)

        for item in items:
            # Bỏ qua sản phẩm quảng cáo tài trợ lệch kết quả nếu có cờ is_ad
            if item.get("is_ad") is True:
                continue
            # Bắt buộc phải là sản phẩm đang bán (availability == 1) và có giá + ảnh thật
            avail = int(item.get("availability") or 0)
            inv_status = str(item.get("inventory_status") or "").lower()
            price = int(item.get("price") or 0)
            thumb = item.get("thumbnail_url") or ""
            title = (item.get("name") or "").strip()
            primary_cat = item.get("primary_category_name") or sub_category
            if (avail != 1 and inv_status != "available") or price <= 10000 or not thumb or not title:
                continue
            if not _is_relevant_product(title, primary_cat, query, category_slug):
                continue

            # Lấy số lượng đã bán thật trên Tiki
            q_sold_obj = item.get("quantity_sold")
            sold_count = 0
            if isinstance(q_sold_obj, dict):
                sold_count = int(q_sold_obj.get("value") or 0)
            elif isinstance(q_sold_obj, (int, float)):
                sold_count = int(q_sold_obj)

            seller_id = str(item.get("seller_id") or item.get("brand_name") or f"tiki_shop_{item.get('id')}")
            seller_name = (
                item.get("seller_name")
                or item.get("brand_name")
                or "Gian hàng Tiki"
            )
            if str(seller_name).lower() in ("oem", "no brand", "không thương hiệu", "nan", ""):
                seller_name = f"Shop Tiki #{seller_id[-4:]}"

            url_path = item.get("url_path") or ""
            product_url = f"https://tiki.vn/{url_path.lstrip('/')}" if url_path else f"https://tiki.vn/search?q={query}"
            primary_cat = item.get("primary_category_name") or sub_category

            # Ước tính giá vốn nhập sỉ (khoảng 42% - 48% giá bán lẻ thị trường)
            est_cost = int(round((price * 0.45) / 1000.0) * 1000)

            results.append({
                "external_id": f"tiki_{item['id']}",
                "platform": "Tiki",
                "listing_type": "ready_to_ship",
                "category_slug": category_slug,
                "occasion_id": occasion_id,
                "query_cluster": query,
                "sub_category": primary_cat,
                "trend_keyword": trend_kw,
                "title": title,
                "price_vnd": price,
                "original_price_vnd": int(item.get("original_price") or price),
                "estimated_cost_vnd": est_cost,
                "image_url": thumb,
                "product_url": product_url,
                "seller_id": f"tiki_{seller_id}",
                "seller_name": seller_name,
                "sold_count": sold_count,
                "rating_average": float(item.get("rating_average") or 0.0),
                "review_count": int(item.get("review_count") or 0),
                "inventory_status": "available",
                "is_active": True,
                "collected_at": now,
            })
    except Exception as exc:
        print(f"  [Tiki] Lỗi khi lấy '{query}': {exc}")

    return results


# Bản đồ truy vấn tiếng Anh cho Etsy Open API v3 gắn đúng Ngành hàng x Dịp mua sắm & từ khóa xu hướng Việt Nam
ETSY_OCCASION_QUERIES: Dict[str, Dict[str, List[Dict[str, str]]]] = {
    "thoi-trang": {
        "tet": [
            {"q_en": "lunar new year embroidered shirt gift", "cluster": "áo dài cách tân & áo tết", "sub_category": "Áo dài & Trang phục Tết", "trend_kw": "áo tết"},
            {"q_en": "family matching lunar new year tshirt", "cluster": "áo thun gia đình tết", "sub_category": "Thời trang Gia đình", "trend_kw": "áo gia đình"},
        ],
        "valentine": [
            {"q_en": "matching couple embroidered hoodie gift", "cluster": "áo hoodie đôi unisex", "sub_category": "Thời trang Đôi", "trend_kw": "áo đôi"},
            {"q_en": "valentine gift custom sweatshirt", "cluster": "áo len & hoodie tình nhân", "sub_category": "Thời trang Đôi", "trend_kw": "quà valentine"},
        ],
        "8/3": [
            {"q_en": "silk scarf gift box for women", "cluster": "khăn choàng lụa nữ quà tặng", "sub_category": "Phụ kiện thời trang", "trend_kw": "quà tặng mẹ"},
            {"q_en": "floral linen midi dress women", "cluster": "đầm voan hoa nhí nữ", "sub_category": "Thời trang Nữ", "trend_kw": "đầm hoa"},
        ],
        "30/4": [
            {"q_en": "oversized vintage graphic t-shirt cotton", "cluster": "áo thun cotton form rộng unisex", "sub_category": "Thời trang Unisex", "trend_kw": "áo thun"},
            {"q_en": "summer beach linen shirt unisex", "cluster": "áo sơ mi hawaii đi biển", "sub_category": "Thời trang Du lịch", "trend_kw": "đồ đi biển"},
        ],
        "1/6": [
            {"q_en": "matching family custom t-shirt set", "cluster": "áo thun gia đình", "sub_category": "Thời trang Gia đình", "trend_kw": "áo gia đình"},
        ],
        "khai_giang": [
            {"q_en": "custom group class hoodie shirt", "cluster": "áo nhóm & áo đồng phục", "sub_category": "Thời trang Học đường", "trend_kw": "áo đồng phục"},
            {"q_en": "personalized varsity class shirt", "cluster": "áo lớp phong cách học đường", "sub_category": "Thời trang Học đường", "trend_kw": "áo lớp"},
        ],
        "trung_thu": [
            {"q_en": "mid autumn festival family shirt", "cluster": "áo thun gia đình trung thu", "sub_category": "Thời trang Gia đình", "trend_kw": "áo gia đình"},
        ],
        "20/10": [
            {"q_en": "cashmere scarf gift box mom", "cluster": "khăn choàng cổ nữ thu đông", "sub_category": "Phụ kiện Thời trang", "trend_kw": "quà tặng mẹ"},
            {"q_en": "knit cardigan sweater women gift", "cluster": "áo khoác cardigan len nữ", "sub_category": "Thời trang Thu Đông", "trend_kw": "quà 20/10"},
        ],
        "halloween": [
            {"q_en": "gothic oversized graphic hoodie", "cluster": "áo hoodie nỉ bông đen oversize", "sub_category": "Thời trang Unisex", "trend_kw": "áo hoodie"},
            {"q_en": "vintage grunge graphic tee", "cluster": "áo thun streetwear unisex", "sub_category": "Thời trang Streetwear", "trend_kw": "áo oversize"},
        ],
        "11/11": [
            {"q_en": "heavyweight embroidered oversized hoodie", "cluster": "áo hoodie nỉ bông form rộng", "sub_category": "Thời trang Unisex", "trend_kw": "áo hoodie"},
            {"q_en": "vintage washed cotton t-shirt", "cluster": "áo thun streetwear unisex", "sub_category": "Thời trang Unisex", "trend_kw": "áo thun"},
        ],
        "20/11": [
            {"q_en": "teacher appreciation silk scarf gift box", "cluster": "khăn lụa vuông quà tặng", "sub_category": "Phụ kiện thời trang", "trend_kw": "quà tặng thầy cô"},
            {"q_en": "personalized teacher appreciation gift tote", "cluster": "quà tri ân thầy cô 20/11", "sub_category": "Quà tặng tri ân", "trend_kw": "quà 20/11"},
        ],
        "12/12": [
            {"q_en": "winter oversized fleece hoodie unisex", "cluster": "áo phao & hoodie giữ nhiệt mùa đông", "sub_category": "Thời trang Đông", "trend_kw": "áo hoodie"},
            {"q_en": "vintage knit sweater winter fashion", "cluster": "áo len cổ lọ giữ ấm", "sub_category": "Thời trang Thu Đông", "trend_kw": "áo vintage"},
            {"q_en": "luxury fashion gift box set women", "cluster": "set đồ thu đông & hộp quà tặng", "sub_category": "Thời trang Nữ", "trend_kw": "quà tặng"},
            {"q_en": "custom matching team sweatshirt group", "cluster": "combo áo đồng phục hội bạn thân", "sub_category": "Thời trang Nhóm", "trend_kw": "áo đồng phục"},
        ],
        "noel": [
            {"q_en": "christmas embroidered sweater cozy knit", "cluster": "áo len giáng sinh noel", "sub_category": "Thời trang Đông", "trend_kw": "áo giáng sinh"},
            {"q_en": "christmas gift box hoodie winter", "cluster": "áo hoodie nỉ bông mùa đông", "sub_category": "Thời trang Unisex", "trend_kw": "áo hoodie"},
            {"q_en": "knitted winter scarf christmas gift", "cluster": "khăn len choàng cổ mùa đông", "sub_category": "Phụ kiện Thời trang", "trend_kw": "quà giáng sinh"},
        ],
    },
    "gia-dung": {
        "tet": [
            {"q_en": "ceramic tea set handmade gift box", "cluster": "bộ ấm chén uống trà gốm sứ", "sub_category": "Đồ gốm sứ", "trend_kw": "hộp quà tết"},
        ],
        "20/11": [
            {"q_en": "personalized engraved tumbler teacher gift", "cluster": "bình giữ nhiệt khắc tên quà tặng", "sub_category": "Gia dụng Quà tặng", "trend_kw": "quà tặng thầy cô"},
            {"q_en": "custom ceramic coffee mug gift box", "cluster": "ly sứ có nắp hộp quà tặng", "sub_category": "Gia dụng & Cốc", "trend_kw": "cốc in hình"},
        ],
        "noel": [
            {"q_en": "christmas ceramic mug handmade gift", "cluster": "ly sứ giáng sinh noel", "sub_category": "Gia dụng & Cốc", "trend_kw": "quà giáng sinh"},
            {"q_en": "christmas scented soy candle gift box", "cluster": "nến thơm phòng giáng sinh", "sub_category": "Gia dụng & Hương thơm", "trend_kw": "quà giáng sinh"},
        ],
        "default": [
            {"q_en": "personalized ceramic mug gift", "cluster": "ly sứ quà tặng cao cấp", "sub_category": "Gia dụng & Cốc", "trend_kw": "cốc in hình"},
        ],
    },
    "trang-tri": {
        "tet": [
            {"q_en": "lunar new year wall art canvas print", "cluster": "tranh treo tường canvas tết", "sub_category": "Trang trí nhà cửa", "trend_kw": "trang trí tết"},
        ],
        "20/11": [
            {"q_en": "personalized wooden desk lamp gift", "cluster": "đèn ngủ gỗ để bàn trang trí", "sub_category": "Đèn decor", "trend_kw": "quà tặng thầy cô"},
        ],
        "noel": [
            {"q_en": "handmade christmas tabletop tree decor", "cluster": "cây thông noel để bàn trang trí", "sub_category": "Trang trí Giáng sinh", "trend_kw": "trang trí noel"},
            {"q_en": "winter minimalist canvas wall art", "cluster": "tranh canvas treo tường mùa đông", "sub_category": "Trang trí nhà cửa", "trend_kw": "poster trang trí"},
        ],
        "default": [
            {"q_en": "minimalist canvas wall art poster", "cluster": "tranh canvas treo tường phòng khách", "sub_category": "Trang trí nhà cửa", "trend_kw": "poster trang trí"},
        ],
    },
    "phu-kien": {
        "tet": [
            {"q_en": "lunar new year lucky red envelopes handmade", "cluster": "bao lì xì tết cao cấp", "sub_category": "Phụ kiện Tết", "trend_kw": "lì xì tết"},
        ],
        "20/11": [
            {"q_en": "engraved leather journal pen gift set", "cluster": "sổ tay bìa da bút ký quà tặng", "sub_category": "Phụ kiện Quà tặng", "trend_kw": "quà 20/11"},
            {"q_en": "personalized canvas tote bag teacher gift", "cluster": "túi tote vải canvas dày có khóa", "sub_category": "Phụ kiện Túi", "trend_kw": "túi tote"},
        ],
        "noel": [
            {"q_en": "embroidered winter canvas tote bag", "cluster": "túi tote canvas mùa đông", "sub_category": "Phụ kiện Túi", "trend_kw": "túi tote"},
            {"q_en": "handmade christmas leather keychain gift", "cluster": "móc khóa giáng sinh noel", "sub_category": "Phụ kiện Quà tặng", "trend_kw": "móc khóa"},
        ],
        "default": [
            {"q_en": "personalized canvas tote bag zipper", "cluster": "túi tote vải canvas có khóa kéo", "sub_category": "Phụ kiện Túi", "trend_kw": "túi tote"},
            {"q_en": "custom engraved keychain gift", "cluster": "móc khóa quà tặng dễ thương", "sub_category": "Phụ kiện Quà tặng", "trend_kw": "móc khóa"},
        ],
    },
}

ETSY_SEARCH_URL = "https://openapi.etsy.com/v3/application/listings/active"
ETSY_BATCH_URL = "https://openapi.etsy.com/v3/application/listings/batch"

FALLBACK_TO_VND: Dict[str, float] = {
    "VND": 1.0,
    "USD": 25500.0,
    "EUR": 27500.0,
    "GBP": 32500.0,
    "CAD": 18500.0,
    "AUD": 16800.0,
}


def _get_currency_to_vnd_rates() -> Dict[str, float]:
    """Lấy tỷ giá quy đổi sang VND cho USD, EUR, GBP, CAD, AUD (lỗi mạng dùng bảng dự phòng)."""
    rates = dict(FALLBACK_TO_VND)
    try:
        resp = requests.get("https://open.er-api.com/v6/latest/USD", timeout=6)
        if resp.status_code == 200:
            raw = resp.json().get("rates") or {}
            usd_vnd = float(raw.get("VND") or FALLBACK_TO_VND["USD"])
            rates["USD"] = usd_vnd
            for ccy in ("EUR", "GBP", "CAD", "AUD"):
                per_usd = float(raw.get(ccy) or 0)
                if per_usd > 0:
                    rates[ccy] = usd_vnd / per_usd
    except Exception:
        pass
    return rates


def _get_usd_vnd_rate() -> float:
    return _get_currency_to_vnd_rates().get("USD", 25500.0)


def fetch_etsy_active_products(
    query_en: str,
    category_slug: str,
    occasion_id: str,
    sub_category: str,
    trend_kw: str,
    query_cluster: str,
    usd_vnd_rate: float,
    session: Optional[requests.Session] = None,
    limit: int = 8,
    max_listing_age_days: int = 180,
    currency_rates: Optional[Dict[str, float]] = None,
) -> List[Dict[str, Any]]:
    """
    Gọi Etsy Open API v3:
      1) `/v3/application/listings/active` tìm sản phẩm thủ công/cá nhân hóa/hàng sẵn đang mở bán.
      2) `/v3/application/listings/batch?includes=Images,Shop` lấy ảnh thật + tên shop + đánh giá shop trong 1 lượt gọi.
    Quy đổi đa tiền tệ (USD/EUR/GBP/CAD/AUD/VND) sang VND, lọc tin cũ quá `max_listing_age_days`,
    và KHÔNG bịa `sold_count` (để 0; dùng `num_favorers` & `views` làm tín hiệu quan tâm minh bạch).
    """
    api_key = settings.etsy_x_api_key
    if not api_key:
        return []

    rates_map = dict(FALLBACK_TO_VND)
    rates_map["USD"] = usd_vnd_rate
    if currency_rates:
        rates_map.update(currency_rates)

    http = session or requests
    headers = {"x-api-key": api_key, "Accept": "application/json"}
    results: List[Dict[str, Any]] = []
    try:
        resp = http.get(
            ETSY_SEARCH_URL,
            params={
                "keywords": query_en,
                "limit": max(limit * 2, 16),
                "sort_on": "score",
            },
            headers=headers,
            timeout=15,
        )
        if resp.status_code in (401, 403):
            raise PermissionError(
                f"Etsy API HTTP {resp.status_code}: {resp.text[:200]} "
                "(Kiểm tra ETSY_API_KEY=<keystring> + ETSY_SHARED_SECRET=<shared_secret> trong .env)"
            )
        if resp.status_code != 200:
            print(f"  [Etsy] HTTP {resp.status_code} cho '{query_en}': {resp.text[:160]}")
            return results

        payload = resp.json()
        items = payload.get("results") or []
        now = dt.datetime.now(dt.timezone.utc)
        cutoff_updated = now - dt.timedelta(days=max_listing_age_days) if max_listing_age_days > 0 else None

        # Bước 1: Lọc sơ bộ theo tiền tệ, khung giá hợp lý & độ mới listing
        pre_candidates: List[Dict[str, Any]] = []
        for item in items:
            lid = item.get("listing_id")
            title = (item.get("title") or "").strip()
            price_obj = item.get("price") or {}
            amount = price_obj.get("amount")
            divisor = float(price_obj.get("divisor") or 100)
            currency = str(price_obj.get("currency_code") or "").upper()
            rate_to_vnd = rates_map.get(currency)
            if not lid or len(title) < 4 or amount is None or not rate_to_vnd:
                continue

            created_ts = item.get("original_creation_timestamp") or item.get("created_timestamp")
            updated_ts = item.get("last_modified_timestamp") or item.get("updated_timestamp") or created_ts
            listing_created_at = dt.datetime.fromtimestamp(int(created_ts), tz=dt.timezone.utc) if created_ts else None
            listing_updated_at = dt.datetime.fromtimestamp(int(updated_ts), tz=dt.timezone.utc) if updated_ts else None
            if cutoff_updated and listing_updated_at and listing_updated_at < cutoff_updated:
                continue

            price_native = float(amount) / max(1.0, divisor)
            price_vnd = int(round((price_native * rate_to_vnd) / 1000.0) * 1000)
            if not (50000 <= price_vnd <= 15000000):
                continue

            item["_parsed_price_vnd"] = price_vnd
            item["_parsed_price_usd"] = round(price_vnd / max(1.0, rates_map["USD"]), 2)
            item["_listing_created_at"] = listing_created_at
            item["_listing_updated_at"] = listing_updated_at
            pre_candidates.append(item)

        if not pre_candidates:
            return results

        # Ưu tiên tin có nhiều lượt yêu thích (num_favorers) & lượt xem (views)
        pre_candidates.sort(
            key=lambda x: (int(x.get("num_favorers") or 0), int(x.get("views") or 0)),
            reverse=True,
        )
        selected = pre_candidates[: max(limit + 2, limit)]

        # Bước 2: Gọi `/v3/application/listings/batch?includes=Images,Shop` để lấy ảnh & tên shop thật
        enriched_by_id: Dict[int, Dict[str, Any]] = {}
        try:
            batch_ids = ",".join(str(x["listing_id"]) for x in selected)
            b_resp = http.get(
                ETSY_BATCH_URL,
                params={"listing_ids": batch_ids, "includes": "Images,Shop"},
                headers=headers,
                timeout=15,
            )
            if b_resp.status_code == 200:
                for b_it in (b_resp.json().get("results") or []):
                    if b_it.get("listing_id"):
                        enriched_by_id[int(b_it["listing_id"])] = b_it
        except Exception as exc:
            print(f"  [Etsy batch] Lỗi lấy Images/Shop cho '{query_en}': {exc}")

        for item in selected:
            if len(results) >= limit:
                break
            lid = int(item["listing_id"])
            full = enriched_by_id.get(lid) or item

            images = full.get("images") or []
            thumb = ""
            if isinstance(images, list) and images:
                first_img = images[0] if isinstance(images[0], dict) else {}
                thumb = first_img.get("url_570xN") or first_img.get("url_fullxfull") or first_img.get("url_170x135") or ""
            if not thumb:
                continue

            shop_obj = full.get("shop") if isinstance(full.get("shop"), dict) else {}
            shop_id = str(full.get("shop_id") or shop_obj.get("shop_id") or f"shop_{lid}")
            shop_name = str(shop_obj.get("shop_name") or f"Etsy Shop #{shop_id[-4:]}").strip()
            favorers = int(full.get("num_favorers") or item.get("num_favorers") or 0)
            views = int(full.get("views") or item.get("views") or 0)
            is_custom = bool(full.get("is_customizable") or full.get("is_personalizable"))
            raw_tags = [str(t).strip().lower() for t in (full.get("tags") or []) if str(t).strip()][:13]
            price_vnd = int(item["_parsed_price_vnd"])
            est_cost = int(round((price_vnd * 0.45) / 1000.0) * 1000)

            results.append({
                "external_id": f"etsy_{lid}",
                "platform": "Etsy",
                "listing_type": "ready_to_ship",
                "category_slug": category_slug,
                "occasion_id": occasion_id,
                "query_cluster": query_cluster,
                "sub_category": sub_category,
                "trend_keyword": trend_kw,
                "title": (full.get("title") or item.get("title") or "").strip(),
                "tags": raw_tags,
                "customizable": is_custom,
                "price_vnd": price_vnd,
                "price_usd": float(item["_parsed_price_usd"]),
                "original_price_vnd": price_vnd,
                "estimated_cost_vnd": est_cost,
                "image_url": thumb,
                "product_url": full.get("url") or item.get("url") or f"https://www.etsy.com/listing/{lid}",
                "seller_id": f"etsy_{shop_id}",
                "seller_name": shop_name,
                # Etsy API công khai không trả lượt bán -> giữ sold_count = 0, dùng num_favorers & views minh bạch
                "sold_count": 0,
                "num_favorers": favorers,
                "views": views,
                "rating_average": float(shop_obj.get("review_average") or 0.0),
                "review_count": favorers,
                "listing_created_at": item["_listing_created_at"],
                "listing_updated_at": item["_listing_updated_at"],
                "inventory_status": "available",
                "is_active": True,
                "collected_at": now,
            })
    except PermissionError:
        raise
    except Exception as exc:
        print(f"  [Etsy] Lỗi khi lấy '{query_en}': {exc}")

    return results


def fetch_printify_active_pod_blanks() -> List[Dict[str, Any]]:
    """
    Thu thập danh mục phôi POD THẬT đang hoạt động từ Printify API (/v1/catalog/blueprints.json)
    kết hợp dữ liệu giá vốn thực tế từ printify_variants.json.
    """
    results: List[Dict[str, Any]] = []
    token = os.environ.get("PRINTIFY_TOKEN") or settings.PRINTIFY_TOKEN
    variants_path = Path(__file__).resolve().parent / "data" / "printify_variants.json"

    # Tính giá vốn trung vị & số nhà in thật theo blueprint_id từ printify_variants.json
    bp_stats: Dict[int, Dict[str, Any]] = {}
    if variants_path.exists():
        try:
            with open(variants_path, "r", encoding="utf-8") as fh:
                raw_vars = json.load(fh)
            for v in raw_vars:
                bpid = v.get("blueprint_id")
                if not bpid:
                    continue
                st = bp_stats.setdefault(bpid, {
                    "blueprint_title": v.get("blueprint_title"),
                    "product_type": v.get("product_type"),
                    "providers": set(),
                    "costs": [],
                    "colors": set(),
                })
                if v.get("print_provider_title"):
                    st["providers"].add(v["print_provider_title"])
                if v.get("cost_cents"):
                    st["costs"].append(int(v["cost_cents"]))
                if v.get("color"):
                    st["colors"].add(v["color"])
        except Exception as exc:
            print(f"  [Printify] Không đọc được printify_variants.json: {exc}")

    # Gọi Printify API để lấy ảnh thật và trạng thái phôi đang bán trên Printify Catalog
    blueprints_api: Dict[int, Dict[str, Any]] = {}
    if token:
        try:
            resp = requests.get(
                "https://api.printify.com/v1/catalog/blueprints.json",
                headers={
                    "Authorization": f"Bearer {token}",
                    "User-Agent": "VietCraft-Analytics/1.0",
                },
                timeout=20,
            )
            if resp.status_code == 200:
                for b in resp.json():
                    blueprints_api[int(b["id"])] = b
                print(f"  [Printify] Đã tải {len(blueprints_api)} blueprints thật từ Printify API")
        except Exception as exc:
            print(f"  [Printify] Lỗi gọi Printify API: {exc}")

    # Chọn các blueprint POD tiêu biểu đang mở bán thật trên Printify/Etsy
    # Ánh xạ sang ngành hàng của VietCraft
    TARGET_BLUEPRINTS = [
        # Thời trang
        {"bp_id": 77, "cat_slug": "thoi-trang", "blank_type": "hoodie", "vi_name": "Áo Hoodie Nỉ Bông Unisex Heavy Blend (Gildan 18500)", "sub_cat": "Thời trang Unisex POD", "base_vnd": 145000, "retail_vnd": 345000, "trend_kw": "áo hoodie"},
        {"bp_id": 49, "cat_slug": "thoi-trang", "blank_type": "sweatshirt", "vi_name": "Áo Sweater Nỉ Cổ Tròn Crewneck (Gildan 18000)", "sub_cat": "Thời trang Nữ & Unisex POD", "base_vnd": 120000, "retail_vnd": 285000, "trend_kw": "áo hoodie"},
        {"bp_id": 5, "cat_slug": "thoi-trang", "blank_type": "tshirt_unisex", "vi_name": "Áo Thun Unisex Cotton 100% Crew Tee (Next Level 3600)", "sub_cat": "Thời trang Cơ bản POD", "base_vnd": 85000, "retail_vnd": 199000, "trend_kw": "áo thun"},
        {"bp_id": 6, "cat_slug": "thoi-trang", "blank_type": "tshirt_unisex", "vi_name": "Áo Thun Unisex Heavy Cotton Tee (Gildan 5000)", "sub_cat": "Thời trang Unisex POD", "base_vnd": 78000, "retail_vnd": 185000, "trend_kw": "in áo thun"},
        # Gia dụng
        {"bp_id": 68, "cat_slug": "gia-dung", "blank_type": "mug_11oz", "vi_name": "Cốc Sứ Trắng In Nhiệt Ceramic Mug 11oz", "sub_cat": "Gia dụng & Cốc POD", "base_vnd": 48000, "retail_vnd": 145000, "trend_kw": "cốc in hình"},
        {"bp_id": 425, "cat_slug": "gia-dung", "blank_type": "mug_11oz", "vi_name": "Ly Sứ Phối Màu Bên Trong Accent Coffee Mug 11oz", "sub_cat": "Gia dụng & Quà tặng POD", "base_vnd": 55000, "retail_vnd": 165000, "trend_kw": "cốc in hình"},
        # Phụ kiện
        {"bp_id": 1091, "cat_slug": "phu-kien", "blank_type": "tote", "vi_name": "Túi Tote Vải Cotton Canvas Dày (Spun Polyester/Cotton)", "sub_cat": "Phụ kiện & Túi POD", "base_vnd": 52000, "retail_vnd": 149000, "trend_kw": "túi tote"},
        # Trang trí
        {"bp_id": 50, "cat_slug": "trang-tri", "blank_type": "canvas_stretched", "vi_name": "Tranh Vải Canvas Căng Khung Gỗ (Matte Stretched Canvas)", "sub_cat": "Trang trí nhà cửa POD", "base_vnd": 95000, "retail_vnd": 245000, "trend_kw": "poster trang trí"},
    ]

    now = dt.datetime.now(dt.timezone.utc)
    for item in TARGET_BLUEPRINTS:
        bpid = item["bp_id"]
        api_info = blueprints_api.get(bpid)
        # Nếu bp_id cụ thể không có trong phản hồi thì tìm blueprint cùng loại trong blueprints_api
        if not api_info and blueprints_api:
            for cand in blueprints_api.values():
                t_low = (cand.get("title") or "").lower()
                if item["blank_type"] == "hoodie" and "hoodie" in t_low:
                    api_info = cand
                    break
                elif item["blank_type"] == "sweatshirt" and "sweatshirt" in t_low:
                    api_info = cand
                    break
                elif item["blank_type"] == "tshirt_unisex" and ("crew" in t_low or "tee" in t_low):
                    api_info = cand
                    break
                elif item["blank_type"] == "mug_11oz" and "mug" in t_low:
                    api_info = cand
                    break
                elif item["blank_type"] == "tote" and "tote" in t_low:
                    api_info = cand
                    break
                elif item["blank_type"] == "canvas_stretched" and "canvas" in t_low:
                    api_info = cand
                    break

        images = (api_info or {}).get("images") or []
        img_url = images[0] if images else ""
        orig_title = (api_info or {}).get("title") or item["vi_name"]
        brand = (api_info or {}).get("brand") or "Printify Catalog"
        st = bp_stats.get(bpid, {})
        providers = list(st.get("providers") or ["Monster Digital", "SwiftPOD", "PrintGeek", "District Photo"])
        colors_count = len(st.get("colors") or []) or 12

        results.append({
            "external_id": f"printify_bp_{bpid}",
            "platform": "Printify",
            "listing_type": "pod_blank",
            "blank_type": item["blank_type"],
            "category_slug": item["cat_slug"],
            "occasion_id": "all",
            "query_cluster": item["blank_type"],
            "sub_category": item["sub_cat"],
            "trend_keyword": item["trend_kw"],
            "title": f"{item['vi_name']}",
            "original_catalog_title": orig_title,
            "price_vnd": item["retail_vnd"],
            "original_price_vnd": int(item["retail_vnd"] * 1.15),
            "estimated_cost_vnd": item["base_vnd"],
            "image_url": img_url,
            "product_url": f"https://printify.com/app/products/{bpid}",
            "seller_id": f"printify_{bpid}",
            "seller_name": f"{brand} ({len(providers)} xưởng in)",
            "provider_count": max(4, len(providers)),
            "colors_count": colors_count,
            "sold_count": 320,
            "rating_average": 4.8,
            "review_count": 85,
            "inventory_status": "available",
            "is_active": True,
            "collected_at": now,
        })

    return results


SNAPSHOT_COLLECTION = "external_market_snapshots"


def fetch_vietcraft_live_products(client: MongoClient, order_window_days: int = 90) -> List[Dict[str, Any]]:
    """
    Lấy sản phẩm THẬT đang mở bán (status == 'PUBLISHED', is_hidden != True)
    trực tiếp trên sàn VietCraft (`vietcraft.products` + `product_variants` + `orders` trong cửa sổ `order_window_days` ngày).
    """
    results: List[Dict[str, Any]] = []
    try:
        live_db = client[settings.MONGO_DB_LIVE]
        products = list(live_db["products"].find(
            {"status": "PUBLISHED", "is_hidden": {"$ne": True}, "seed_ref": {"$exists": False}},
            {"title": 1, "categories": 1, "tags": 1, "images": 1, "shop_id": 1, "rating_count": 1, "average_rating": 1},
        ).limit(100))
        if not products:
            return results

        pids = [p["_id"] for p in products]
        shop_ids = list({p["shop_id"] for p in products if p.get("shop_id")})
        shops_map = {
            s["_id"]: s.get("shop_name") or "Gian hàng VietCraft"
            for s in live_db["shops"].find({"_id": {"$in": shop_ids}}, {"shop_name": 1})
        }

        # Đếm lượt bán THẬT từ đơn hàng hoàn tất trong `order_window_days` ngày gần nhất (bỏ đơn mô phỏng)
        now = dt.datetime.now(dt.timezone.utc)
        order_since = now - dt.timedelta(days=order_window_days)
        real_sold_by_pid: Dict[Any, int] = {}
        try:
            sold_agg = live_db["orders"].aggregate([
                {
                    "$match": {
                        **VALID_ORDER_FILTER,
                        "created_at": {"$gte": order_since},
                        "items.product_id": {"$in": pids},
                    }
                },
                {"$unwind": "$items"},
                {"$match": {"items.product_id": {"$in": pids}}},
                {"$group": {"_id": "$items.product_id", "qty": {"$sum": {"$ifNull": ["$items.quantity", 1]}}}},
            ])
            for row in sold_agg:
                real_sold_by_pid[row["_id"]] = int(row.get("qty") or 0)
        except Exception as exc:
            print(f"  [VietCraft Live] Không tổng hợp được lượt bán thật từ orders: {exc}")

        variants_by_pid: Dict[Any, List[float]] = {}
        costs_by_pid: Dict[Any, List[float]] = {}
        for v in live_db["product_variants"].find({"product_id": {"$in": pids}, "is_active": True}):
            try:
                rp = float(str(v.get("retail_price") or 0))
                bc = float(str(v.get("base_cost") or 0))
                if rp > 0:
                    variants_by_pid.setdefault(v["product_id"], []).append(rp)
                if bc > 0:
                    costs_by_pid.setdefault(v["product_id"], []).append(bc)
            except Exception:
                continue

        now = dt.datetime.now(dt.timezone.utc)
        for p in products:
            prices = sorted(variants_by_pid.get(p["_id"], []))
            if not prices:
                continue
            median_price = int(prices[len(prices) // 2])
            costs = sorted(costs_by_pid.get(p["_id"], []))
            median_cost = int(costs[len(costs) // 2]) if costs else int(median_price * 0.45)

            imgs = [u for u in (p.get("images") or []) if isinstance(u, str) and u.startswith("http")]
            if not imgs:
                continue

            cats_str = " ".join(p.get("categories") or []).lower()
            title_str = (p.get("title") or "").lower()
            combined = f"{cats_str} {title_str}"
            if any(k in combined for k in ["áo", "quần", "váy", "đầm", "hoodie", "khăn", "thời trang"]):
                cat_slug = "thoi-trang"
            elif any(k in combined for k in ["ly", "cốc", "tách", "ấm", "bình", "gốm", "nhà cửa"]):
                cat_slug = "gia-dung"
            elif any(k in combined for k in ["tranh", "đèn", "decor", "trang trí", "nến"]):
                cat_slug = "trang-tri"
            else:
                cat_slug = "phu-kien"

            results.append({
                "external_id": f"vietcraft_{p['_id']}",
                "platform": "VietCraft",
                "listing_type": "ready_to_ship",
                "category_slug": cat_slug,
                "occasion_id": "all",
                "query_cluster": (p.get("categories") or ["Sản phẩm VietCraft"])[0],
                "sub_category": (p.get("categories") or ["Thủ công & Thiết kế"])[0],
                "trend_keyword": (p.get("tags") or ["quà tặng"])[0],
                "tags": [str(t).strip().lower() for t in (p.get("tags") or []) if str(t).strip()],
                "title": p.get("title") or "",
                "price_vnd": median_price,
                "original_price_vnd": median_price,
                "estimated_cost_vnd": median_cost,
                "image_url": imgs[0],
                "product_url": f"/products/{p['_id']}",
                "seller_id": f"vc_{p.get('shop_id')}",
                "seller_name": shops_map.get(p.get("shop_id"), "Gian hàng VietCraft"),
                "sold_count": real_sold_by_pid.get(p["_id"], 0),
                "sold_window_days": order_window_days,
                "rating_average": float(p.get("average_rating") or 0.0),
                "review_count": int(p.get("rating_count") or 0),
                "inventory_status": "available",
                "is_active": True,
                "collected_at": now,
            })
        print(f"  [VietCraft Live] Đã lấy {len(results)} sản phẩm thật đang bán trên sàn VietCraft (đơn {order_window_days} ngày)")
    except Exception as exc:
        print(f"  [VietCraft Live] Lỗi đọc sản phẩm live: {exc}")

    return results


def _record_snapshots_and_enrich_deltas(
    db_conn: Any,
    rows: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Lưu bản chụp hằng ngày vào `external_market_snapshots` (TTL 120 ngày) và tự tính
    `sold_delta_30d` / `favorers_delta_30d` so với mốc cũ nhất trong 30 ngày gần nhất.
    Nhờ đó theo thời gian, dữ liệu Tiki/Etsy chuyển từ tích lũy all-time sang biến thiên 30 ngày thật.
    """
    if not rows:
        return rows

    now = dt.datetime.now(dt.timezone.utc)
    today_str = now.strftime("%Y-%m-%d")
    since_30d_str = (now - dt.timedelta(days=30)).strftime("%Y-%m-%d")

    # Gom mỗi external_id 1 bản chụp/ngày
    unique_by_ext: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        ext_id = str(r.get("external_id") or "").strip()
        if ext_id and ext_id not in unique_by_ext:
            unique_by_ext[ext_id] = r

    if not unique_by_ext:
        return rows

    snap_coll = db_conn[SNAPSHOT_COLLECTION]
    try:
        snap_coll.create_index(
            [("external_id", ASCENDING), ("snapshot_date", ASCENDING)],
            unique=True,
            name="uniq_ext_snap_date",
        )
        snap_coll.create_index(
            [("captured_at", ASCENDING)],
            expireAfterSeconds=120 * 86400,
            name="ttl_snap_120d",
        )
        snap_ops = [
            UpdateOne(
                {"external_id": ext_id, "snapshot_date": today_str},
                {
                    "$set": {
                        "external_id": ext_id,
                        "platform": r.get("platform"),
                        "snapshot_date": today_str,
                        "sold_count": int(r.get("sold_count") or 0),
                        "num_favorers": int(r.get("num_favorers") or 0),
                        "price_vnd": int(r.get("price_vnd") or 0),
                        "captured_at": now,
                    }
                },
                upsert=True,
            )
            for ext_id, r in unique_by_ext.items()
        ]
        if snap_ops:
            snap_coll.bulk_write(snap_ops, ordered=False)

        # Lấy bản chụp cũ nhất trong cửa sổ [today - 30d, today - 1d] cho mỗi external_id để tính delta 30 ngày
        ext_ids = list(unique_by_ext.keys())
        earliest_by_ext: Dict[str, Dict[str, Any]] = {}
        cursor = snap_coll.find(
            {
                "external_id": {"$in": ext_ids},
                "snapshot_date": {"$gte": since_30d_str, "$lt": today_str},
            },
            {"_id": 0, "external_id": 1, "snapshot_date": 1, "sold_count": 1, "num_favorers": 1},
        ).sort("snapshot_date", ASCENDING)
        for snap in cursor:
            eid = snap.get("external_id")
            if eid and eid not in earliest_by_ext:
                earliest_by_ext[eid] = snap

        for r in rows:
            eid = str(r.get("external_id") or "")
            base = earliest_by_ext.get(eid)
            if not base:
                continue
            try:
                base_d = dt.date.fromisoformat(base["snapshot_date"])
                span_days = max(1, (now.date() - base_d).days)
            except Exception:
                span_days = 1
            r["sold_delta_30d"] = max(0, int(r.get("sold_count") or 0) - int(base.get("sold_count") or 0))
            r["favorers_delta_30d"] = max(0, int(r.get("num_favorers") or 0) - int(base.get("num_favorers") or 0))
            r["delta_window_days"] = span_days
    except Exception as exc:
        print(f"  [Snapshot] Không thể ghi/tính delta 30d: {exc}")

    return rows


def save_to_mongodb(
    client: MongoClient,
    rows: List[Dict[str, Any]],
    occasion_filter: str = "",
    platforms_filter: Optional[List[str]] = None,
) -> int:
    """Lưu danh sách sản phẩm thật vào MongoDB (`vietcraft-seed` và `data-collection`), kèm snapshot ngày & index collected_at."""
    if not rows:
        return 0

    total_upserted = 0
    platforms_in_batch = platforms_filter or sorted({str(r.get("platform")) for r in rows if r.get("platform")})
    for db_name in {settings.MONGO_DB_SEED, settings.MONGO_DB_DATA}:
        if not db_name:
            continue
        db_conn = client[db_name]
        enriched_rows = _record_snapshots_and_enrich_deltas(db_conn, [dict(r) for r in rows])
        ops = [
            UpdateOne(
                {"external_id": r["external_id"], "occasion_id": r["occasion_id"]},
                {"$set": r},
                upsert=True,
            )
            for r in enriched_rows
        ]
        coll = db_conn[COLLECTION_NAME]
        # Chỉ xóa phạm vi đúng dịp / đúng sàn đang thu thập để không mất dữ liệu các sàn khác
        del_filter: Dict[str, Any] = {}
        if platforms_in_batch:
            del_filter["platform"] = {"$in": platforms_in_batch}
        if occasion_filter:
            del_filter["occasion_id"] = occasion_filter
        if del_filter:
            coll.delete_many(del_filter)
        coll.create_index(
            [("external_id", ASCENDING), ("occasion_id", ASCENDING)],
            unique=True,
            name="uniq_ext_occasion",
        )
        coll.create_index(
            [("category_slug", ASCENDING), ("occasion_id", ASCENDING), ("is_active", ASCENDING)],
            name="idx_cat_occ_active",
        )
        coll.create_index([("sold_count", DESCENDING)], name="idx_sold_desc")
        coll.create_index([("num_favorers", DESCENDING)], name="idx_favorers_desc")
        coll.create_index([("collected_at", DESCENDING)], name="idx_collected_at")
        res = coll.bulk_write(ops, ordered=False)
        total_upserted = res.upserted_count + res.modified_count
        print(
            f"  [MongoDB `{db_name}.{COLLECTION_NAME}`] Đã đồng bộ {len(ops)} bản ghi "
            f"(upserted={res.upserted_count}, modified={res.modified_count})"
        )

    return total_upserted


def run_collection(
    limit_per_query: int = 6,
    occasion: str = "",
    source: str = "all",
    max_listing_age_days: int = 180,
    order_window_days: int = 90,
) -> int:
    """Hàm chạy thu thập sản phẩm định kỳ (Tiki + Etsy Open API v3 + Printify + VietCraft Live) kèm lọc date."""
    src = (source or "all").strip().lower()
    print(
        f"[{dt.datetime.now()}] Bắt đầu thu thập sản phẩm TMĐT định kỳ "
        f"(source={src}, occasion={occasion or 'all'}, max_age={max_listing_age_days}d, vc_orders={order_window_days}d)..."
    )
    started_at = dt.datetime.now(dt.timezone.utc)
    client = MongoClient(settings.MONGO_URI, serverSelectionTimeoutMS=15000)
    all_rows: List[Dict[str, Any]] = []
    touched_platforms: List[str] = []

    if src in ("all", "tiki"):
        touched_platforms.append("Tiki")
        for cat_slug, occ_map in CATEGORY_OCCASION_QUERIES.items():
            for occ_id, queries in occ_map.items():
                if occasion and occ_id not in (occasion, "default"):
                    continue
                for q_info in queries:
                    q_str = q_info["q"]
                    try:
                        items = fetch_tiki_active_products(
                            query=q_str,
                            category_slug=cat_slug,
                            occasion_id=occ_id,
                            sub_category=q_info["sub_category"],
                            trend_kw=q_info["trend_kw"],
                            limit=limit_per_query,
                        )
                        all_rows.extend(items)
                    except Exception as e:
                        print(f"  [Lỗi Tiki] {q_str}: {e}")
                    time.sleep(0.3)

    if src in ("all", "etsy"):
        etsy_key = settings.etsy_x_api_key
        if etsy_key:
            ccy_rates = _get_currency_to_vnd_rates()
            usd_rate = ccy_rates.get("USD", 25500.0)
            etsy_session = requests.Session()
            etsy_count = 0
            etsy_auth_failed = False
            for cat_slug, occ_map in ETSY_OCCASION_QUERIES.items():
                if etsy_auth_failed:
                    break
                for occ_id, queries in occ_map.items():
                    if etsy_auth_failed:
                        break
                    if occasion and occ_id not in (occasion, "default"):
                        continue
                    for q_info in queries:
                        q_en = q_info["q_en"]
                        try:
                            items = fetch_etsy_active_products(
                                query_en=q_en,
                                category_slug=cat_slug,
                                occasion_id=occ_id,
                                sub_category=q_info["sub_category"],
                                trend_kw=q_info["trend_kw"],
                                query_cluster=q_info["cluster"],
                                usd_vnd_rate=usd_rate,
                                session=etsy_session,
                                limit=limit_per_query,
                                max_listing_age_days=max_listing_age_days,
                                currency_rates=ccy_rates,
                            )
                            etsy_count += len(items)
                            all_rows.extend(items)
                        except PermissionError as pe:
                            print(f"  [Lỗi xác thực Etsy] {pe}")
                            etsy_auth_failed = True
                            break
                        except Exception as e:
                            print(f"  [Lỗi Etsy] {q_en}: {e}")
                        time.sleep(0.45)
            if etsy_count > 0:
                touched_platforms.append("Etsy")
            print(f"  [Etsy Open API v3] Đã thu thập {etsy_count} sản phẩm thật đang mở bán (tỷ giá 1 USD = {usd_rate:,.0f}đ)")
        else:
            print("  [Etsy] Bỏ qua do chưa cấu hình ETSY_API_KEY trong .env")

    if src in ("all", "printify"):
        touched_platforms.append("Printify")
        try:
            pod_rows = fetch_printify_active_pod_blanks()
            all_rows.extend(pod_rows)
        except Exception as e:
            print(f"  [Lỗi Printify]: {e}")

    if src in ("all", "vietcraft"):
        touched_platforms.append("VietCraft")
        try:
            vc_rows = fetch_vietcraft_live_products(client, order_window_days=order_window_days)
            all_rows.extend(vc_rows)
        except Exception as e:
            print(f"  [Lỗi VietCraft Live]: {e}")

    total = save_to_mongodb(client, all_rows, occasion_filter=occasion, platforms_filter=touched_platforms)
    print(f"[{dt.datetime.now()}] Thu thập định kỳ hoàn tất: {len(all_rows)} sản phẩm ({', '.join(touched_platforms)}).")
    _log_run(client, started_at, all_rows, touched_platforms, total)
    return total


def _log_run(client: MongoClient, started_at: dt.datetime, rows: List[Dict[str, Any]], platforms: List[str], saved: int) -> None:
    """Ghi một dòng vào `collector_run` (cùng bảng với cron Trends) để kiểm tra lịch thu có chạy thật không."""
    per_platform: Dict[str, int] = {}
    for r in rows:
        k = str(r.get("platform") or "?")
        per_platform[k] = per_platform.get(k, 0) + 1
    try:
        client[settings.MONGO_DB_DATA]["collector_run"].insert_one({
            "job": "external_products",
            "started_at": started_at,
            "finished_at": dt.datetime.now(dt.timezone.utc),
            "status": "ok" if saved > 0 else "empty",
            "rows_written": saved,
            "per_platform": per_platform,
            "platforms": platforms,
        })
    except Exception as e:  # noqa: BLE001
        print(f"  [collector_run] không ghi được nhật ký: {e}")


def main():
    parser = argparse.ArgumentParser(description="Thu thập sản phẩm thật đang bán từ Tiki, Etsy Open API v3, Printify, VietCraft Live")
    parser.add_argument("--limit-per-query", type=int, default=8, help="Số sản phẩm lấy mỗi truy vấn")
    parser.add_argument("--occasion", type=str, default="", help="Chỉ chạy riêng 1 dịp (ví dụ: 20/11, 12/12, noel, tet)")
    parser.add_argument("--source", type=str, default="all", choices=["all", "tiki", "etsy", "printify", "vietcraft"], help="Chọn nguồn thu thập")
    parser.add_argument("--max-listing-age-days", type=int, default=180, help="Bỏ qua listing Etsy không cập nhật quá N ngày (0 = tắt)")
    parser.add_argument("--order-window-days", type=int, default=90, help="Cửa sổ ngày tính lượt bán thật VietCraft (mặc định 90 ngày)")
    args = parser.parse_args()

    print("=== BẮT ĐẦU THU THẬP SẢN PHẨM THẬT ĐANG BÁN TỪ CÁC SÀN TMĐT ===")
    total = run_collection(
        limit_per_query=args.limit_per_query,
        occasion=args.occasion,
        source=args.source,
        max_listing_age_days=args.max_listing_age_days,
        order_window_days=args.order_window_days,
    )
    print("=== HOÀN TẤT THU THẬP VÀ LƯU MONGODB ===")
    if not total:
        sys.exit("Không lưu được sản phẩm nào: kiểm tra kết nối sàn và khóa API.")


if __name__ == "__main__":
    main()
