"""
loader.py — Data Access Layer dùng chung cho toàn bộ các mô hình AI VietCraft.
Toàn bộ nhóm đọc dữ liệu qua module này, không viết query trực tiếp trong model.

Quy tắc:
- Tự động fallback giữa MongoDB và CSV repo SE16-AI/data/.
- Chuỗi thời gian trả về dạng pd.Series có DatetimeIndex chuẩn và tần suất rõ ràng.
"""

import os
import sys
import pandas as pd
from typing import Optional, List, Dict, Any
from pymongo import MongoClient

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.dirname(BASE_DIR)
AI_ANALYSIC_DIR = os.path.dirname(APP_DIR)
WORKSPACE_ROOT = os.path.dirname(AI_ANALYSIC_DIR)
SE16_DATA_DIR = os.path.join(WORKSPACE_ROOT, "SE16-AI", "data")

sys.path.insert(0, AI_ANALYSIC_DIR)
from app.config import settings


# 40 từ khoá đạt chuẩn phân tích từ Sprint 0 (loại bỏ 5 từ khoá chết có tín hiệu = 0)
ACTIVE_KEYWORDS_FALLBACK = [
    "áo thun", "áo phông nam", "áo phông nữ", "in áo thun", "áo đôi",
    "áo nhóm", "áo lớp", "áo đồng phục", "áo gia đình", "túi tote",
    "tranh treo tường", "tranh canvas", "móc khóa", "áo tết", "quà tết",
    "lì xì tết", "trang trí tết", "quà 8/3", "quà tặng mẹ", "quà 20/10",
    "quà 20/11", "quà tặng thầy cô", "quà giáng sinh", "trang trí noel", "quà valentine",
    "quà tặng người yêu", "quà tặng", "quà cưới", "quà tân gia", "quà tặng bạn thân",
    "quà handmade", "quà lưu niệm", "áo anime", "áo oversize", "áo local brand",
    "áo vintage", "áo hoodie", "áo bóng đá việt nam", "áo thun thể thao", "quà sinh nhật"
]


def _get_mongo_coll(db_name: str, coll_name: str):
    try:
        client = MongoClient(settings.MONGO_URI, serverSelectionTimeoutMS=2000)
        return client[db_name][coll_name]
    except Exception:
        return None


def get_trend_series(keyword: str, granularity: str = "weekly") -> pd.Series:
    """
    Đọc chuỗi thời gian Google Trends cho một từ khoá.
    - granularity: 'weekly' (5 năm, W-SUN) hoặc 'daily' (90 ngày gần nhất, D).
    Trả về pd.Series có DatetimeIndex và tần suất (freq).
    """
    coll = _get_mongo_coll(settings.MONGO_DB_DATA, "trend_interest")
    df = pd.DataFrame()

    if coll is not None:
        try:
            cursor = coll.find(
                {"keyword": keyword, "granularity": granularity, "is_anchor": False},
                {"_id": 0, "observed_on": 1, "scaled": 1}
            ).sort("observed_on", 1)
            df = pd.DataFrame(list(cursor))
        except Exception:
            df = pd.DataFrame()

    if df.empty:
        # Fallback đọc từ CSV cục bộ nếu MongoDB chưa kết nối
        csv_path = os.path.join(APP_DIR, "collectors", "data", f"trends_{granularity}_{keyword}.csv")
        if os.path.exists(csv_path):
            df = pd.read_csv(csv_path)

    if df.empty:
        raise ValueError(f"Không tìm thấy dữ liệu Trends cho từ khoá '{keyword}' (granularity={granularity}).")

    df["observed_on"] = pd.to_datetime(df["observed_on"])
    df = df.set_index("observed_on").sort_index()

    # Nhóm theo ngày nếu có trùng lặp và gán tần suất
    series = df["scaled"].astype(float)
    if granularity == "weekly":
        series = series.asfreq("W-SUN")
    else:
        series = series.asfreq("D")

    series.name = keyword
    return series


def get_active_keywords() -> List[str]:
    """Trả về danh sách 40 từ khoá đủ điều kiện chạy model."""
    coll = _get_mongo_coll(settings.MONGO_DB_DATA, "keyword_quality")
    if coll is not None:
        try:
            doc = coll.find_one({"type": "usable_keywords"})
            if doc and "keywords" in doc:
                return doc["keywords"]
        except Exception:
            pass
    return list(ACTIVE_KEYWORDS_FALLBACK)


def get_categories() -> pd.DataFrame:
    """Đọc cây danh mục từ dữ liệu của Nhi."""
    path = os.path.join(SE16_DATA_DIR, "Nhi_Bui_Data Collection", "categories.csv")
    if os.path.exists(path):
        return pd.read_csv(path, encoding="utf-8-sig")
    return pd.DataFrame()


def get_tags() -> pd.DataFrame:
    """Đọc bộ tag chuẩn từ dữ liệu của Nhi."""
    path = os.path.join(SE16_DATA_DIR, "Nhi_Bui_Data Collection", "tags.csv")
    if os.path.exists(path):
        return pd.read_csv(path, encoding="utf-8-sig")
    return pd.DataFrame()


def get_tag_keyword_mapping() -> pd.DataFrame:
    """Đọc bảng ánh xạ Tag <-> Keyword từ dữ liệu của Nhi."""
    path = os.path.join(SE16_DATA_DIR, "Nhi_Bui_Data Collection", "tag_keyword_map.csv")
    if os.path.exists(path):
        return pd.read_csv(path, encoding="utf-8-sig")
    return pd.DataFrame()


def get_catalog_info(product_type_id: Optional[str] = None) -> pd.DataFrame:
    """Đọc thông tin 138 loại sản phẩm và giá vốn từ dữ liệu của Hưng."""
    types_path = os.path.join(SE16_DATA_DIR, "Hung_TaskAI", "vc_product_type.csv")
    if not os.path.exists(types_path):
        return pd.DataFrame()
    df = pd.read_csv(types_path, encoding="utf-8-sig")
    if product_type_id:
        df = df[df["product_type_id"] == product_type_id]
    return df


def get_shops() -> pd.DataFrame:
    """Đọc thông tin 80 shop từ dữ liệu của Hạt."""
    path = os.path.join(SE16_DATA_DIR, "Le_Hat_Task_AI", "shops.csv")
    if os.path.exists(path):
        return pd.read_csv(path, encoding="utf-8-sig")
    return pd.DataFrame()


def get_listings(shop_id: Optional[str] = None, category_id: Optional[str] = None) -> pd.DataFrame:
    """Đọc 5.000 sản phẩm từ dữ liệu của Hạt."""
    path = os.path.join(SE16_DATA_DIR, "Le_Hat_Task_AI", "listings.csv")
    if not os.path.exists(path):
        return pd.DataFrame()
    df = pd.read_csv(path, encoding="utf-8-sig")
    if shop_id:
        df = df[df["shop_id"] == shop_id]
    if category_id:
        df = df[df["category_id"] == category_id]
    return df


def get_listing_daily(
    listing_id: Optional[str] = None,
    shop_id: Optional[str] = None,
    category_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None
) -> pd.DataFrame:
    """
    Đọc bảng thống kê listing_daily.
    Hỗ trợ đọc từ MongoDB vietcraft-seed hoặc fallback file CSV khi Hiếu hoàn thành.
    """
    coll = _get_mongo_coll(settings.MONGO_DB_SEED, "listing_daily")
    if coll is not None:
        try:
            query: Dict[str, Any] = {}
            if listing_id:
                query["listing_id"] = listing_id
            if shop_id:
                query["shop_id"] = shop_id
            if category_id:
                query["category_id"] = category_id
            if date_from or date_to:
                date_filter = {}
                if date_from:
                    date_filter["$gte"] = date_from
                if date_to:
                    date_filter["$lte"] = date_to
                query["date"] = date_filter

            cursor = coll.find(query, {"_id": 0})
            df = pd.DataFrame(list(cursor))
            if not df.empty:
                df["date"] = pd.to_datetime(df["date"])
                return df.sort_values("date")
        except Exception:
            pass

    # Fallback đọc từ CSV seed_out
    csv_path = os.path.join(SE16_DATA_DIR, "seed_out", "v1", "listing_daily.csv")
    if os.path.exists(csv_path):
        df = pd.read_csv(csv_path, encoding="utf-8-sig")
        if listing_id:
            df = df[df["listing_id"] == listing_id]
        if shop_id:
            df = df[df["shop_id"] == shop_id]
        if category_id and "category_id" in df.columns:
            df = df[df["category_id"] == category_id]
        if not df.empty:
            df["date"] = pd.to_datetime(df["date"])
            if date_from:
                df = df[df["date"] >= pd.to_datetime(date_from)]
            if date_to:
                df = df[df["date"] <= pd.to_datetime(date_to)]
            return df.sort_values("date")

    return pd.DataFrame()


if __name__ == "__main__":
    print("=== TỰ KIỂM TRA MODULE LOADER.PY ===")
    kw_list = get_active_keywords()
    print(f"✓ get_active_keywords: {len(kw_list)} từ khoá chuẩn")
    assert len(kw_list) >= 40, "Thiếu từ khoá chuẩn"

    cats = get_categories()
    print(f"✓ get_categories: {len(cats)} danh mục")
    assert not cats.empty, "Không đọc được categories.csv"

    tags = get_tags()
    print(f"✓ get_tags: {len(tags)} tags")
    assert not tags.empty, "Không đọc được tags.csv"

    tag_map = get_tag_keyword_mapping()
    print(f"✓ get_tag_keyword_mapping: {len(tag_map)} mappings")
    assert not tag_map.empty, "Không đọc được tag_keyword_map.csv"

    catalog = get_catalog_info()
    print(f"✓ get_catalog_info: {len(catalog)} loại sản phẩm")
    assert len(catalog) == 138, "Số lượng loại sản phẩm khác 138"

    shops = get_shops()
    print(f"✓ get_shops: {len(shops)} shops")
    assert len(shops) == 80, "Số lượng shop khác 80"

    listings = get_listings()
    print(f"✓ get_listings: {len(listings)} listings")
    assert len(listings) == 5000, "Số lượng listing khác 5000"

    print("✅ TẤT CẢ SELF-CHECKS CỦA LOADER.PY ĐÃ PASS!")
