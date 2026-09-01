"""
import_all_seeds.py — Script gom và nạp toàn bộ dữ liệu CSV của 5 thành viên vào MongoDB vietcraft-seed.
Tuân thủ quy định Task 26 (HUONG_DAN_6_DAT.md):
  - Nạp master data: Danh mục (Nhi), Tags (Nhi), Catalog 138 loại & giá (Hưng), Shops & 5.000 listings (Hạt).
  - Nạp behavior data: Buyers (Hiếu), Orders & Items (Hiếu), Reviews (Hiếu), Listing Daily (Hiếu).
  - KHÔNG nạp bảng raw events (1.2M dòng) để bảo vệ hạn mức 512MB MongoDB Atlas.
  - Sử dụng cơ chế ghi Upsert chống nhân đôi dữ liệu khi chạy lại nhiều lần.
"""

import os
import sys
import csv
from typing import List, Dict, Any
from pymongo import MongoClient, UpdateOne

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.dirname(BASE_DIR)
ROOT_DIR = os.path.dirname(APP_DIR)
WORKSPACE_ROOT = os.path.dirname(ROOT_DIR)
DATA_DIR = os.path.join(WORKSPACE_ROOT, "SE16-AI", "data")

sys.path.insert(0, ROOT_DIR)
from app.config import settings


def read_csv_rows(path: str) -> List[Dict[str, Any]]:
    if not os.path.exists(path):
        return []
    with open(path, mode="r", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def upsert_collection(db, coll_name: str, rows: List[Dict[str, Any]], key_field: str, batch_size: int = 2000) -> int:
    if not rows:
        return 0
    coll = db[coll_name]
    total_processed = 0

    for i in range(0, len(rows), batch_size):
        batch = rows[i:i + batch_size]
        ops = []
        for r in batch:
            doc = dict(r)
            filter_doc = {key_field: doc[key_field]}
            ops.append(UpdateOne(filter_doc, {"$set": doc}, upsert=True))
        if ops:
            res = coll.bulk_write(ops, ordered=False)
            total_processed += (res.upserted_count + res.modified_count + res.matched_count)

    return total_processed


def import_all_seeds(db_uri: str = None, db_name: str = None):
    uri = db_uri or settings.MONGO_URI
    dbname = db_name or settings.MONGO_DB_SEED
    print(f"=== Đang nạp toàn bộ dữ liệu Seed vào MongoDB: {dbname} ===")
    
    client = MongoClient(uri, serverSelectionTimeoutMS=5000)
    db = client[dbname]

    # 1. Dữ liệu từ Nhi
    cat_rows = read_csv_rows(os.path.join(DATA_DIR, "Nhi_Bui_Data Collection", "categories.csv"))
    tag_rows = read_csv_rows(os.path.join(DATA_DIR, "Nhi_Bui_Data Collection", "tags.csv"))
    tag_map_rows = read_csv_rows(os.path.join(DATA_DIR, "Nhi_Bui_Data Collection", "tag_keyword_map.csv"))
    
    print(f"  - Categories (Nhi): {len(cat_rows)} dòng")
    print(f"  - Tags (Nhi): {len(tag_rows)} dòng")
    print(f"  - Tag Keyword Map (Nhi): {len(tag_map_rows)} dòng")
    if cat_rows: upsert_collection(db, "categories", cat_rows, "category_id")
    if tag_rows: upsert_collection(db, "tags", tag_rows, "tag_id")

    # 2. Dữ liệu từ Hưng
    pt_rows = read_csv_rows(os.path.join(DATA_DIR, "Hung_TaskAI", "vc_product_type.csv"))
    pr_rows = read_csv_rows(os.path.join(DATA_DIR, "Hung_TaskAI", "vc_price_rule.csv"))
    var_rows = read_csv_rows(os.path.join(DATA_DIR, "Hung_TaskAI", "vc_catalog_variant.csv"))
    set_rows = read_csv_rows(os.path.join(DATA_DIR, "Hung_TaskAI", "vc_setting.csv"))
    
    print(f"  - Product Types (Hưng): {len(pt_rows)} dòng")
    print(f"  - Price Rules (Hưng): {len(pr_rows)} dòng")
    print(f"  - Catalog Variants (Hưng): {len(var_rows)} dòng")
    if pt_rows: upsert_collection(db, "vc_product_type", pt_rows, "product_type_id")
    if pr_rows: upsert_collection(db, "vc_price_rule", pr_rows, "product_type_id")
    if set_rows: upsert_collection(db, "vc_setting", set_rows, "setting_key")
    if var_rows: upsert_collection(db, "vc_catalog_variant", var_rows, "catalog_variant_id")

    # 3. Dữ liệu từ Hạt
    shop_rows = read_csv_rows(os.path.join(DATA_DIR, "Le_Hat_Task_AI", "shops.csv"))
    listing_rows = read_csv_rows(os.path.join(DATA_DIR, "Le_Hat_Task_AI", "listings.csv"))
    lvar_rows = read_csv_rows(os.path.join(DATA_DIR, "Le_Hat_Task_AI", "listing_variants.csv"))
    
    print(f"  - Shops (Hạt): {len(shop_rows)} dòng")
    print(f"  - Listings (Hạt): {len(listing_rows)} dòng")
    print(f"  - Listing Variants (Hạt): {len(lvar_rows)} dòng")
    if shop_rows: upsert_collection(db, "shops", shop_rows, "shop_id")
    if listing_rows: upsert_collection(db, "listings", listing_rows, "listing_id")
    if lvar_rows: upsert_collection(db, "listing_variants", lvar_rows, "variant_id")

    # 4. Dữ liệu từ Hiếu
    buyer_rows = read_csv_rows(os.path.join(DATA_DIR, "seed_out", "v1", "buyers.csv"))
    order_rows = read_csv_rows(os.path.join(DATA_DIR, "seed_out", "v1", "orders.csv"))
    item_rows = read_csv_rows(os.path.join(DATA_DIR, "seed_out", "v1", "order_items.csv"))
    review_rows = read_csv_rows(os.path.join(DATA_DIR, "seed_out", "v1", "reviews.csv"))
    daily_rows = read_csv_rows(os.path.join(DATA_DIR, "seed_out", "v1", "listing_daily.csv"))
    
    print(f"  - Buyers (Hiếu): {len(buyer_rows)} dòng")
    print(f"  - Orders (Hiếu): {len(order_rows)} dòng {'(PENDING TỪ HIẾU)' if not order_rows else ''}")
    print(f"  - Order Items (Hiếu): {len(item_rows)} dòng {'(PENDING TỪ HIẾU)' if not item_rows else ''}")
    print(f"  - Reviews (Hiếu): {len(review_rows)} dòng {'(PENDING TỪ HIẾU)' if not review_rows else ''}")
    print(f"  - Listing Daily (Hiếu): {len(daily_rows)} dòng {'(PENDING TỪ HIẾU)' if not daily_rows else ''}")

    if buyer_rows: upsert_collection(db, "buyers", buyer_rows, "buyer_id")
    if order_rows: upsert_collection(db, "orders", order_rows, "order_id")
    if item_rows: upsert_collection(db, "order_items", item_rows, "order_item_id")
    if review_rows: upsert_collection(db, "reviews", review_rows, "review_id")
    if daily_rows:
        # Với listing_daily, upsert theo cặp (listing_id, date)
        print("  -> Đang nạp listing_daily (batch upsert)...")
        ops = []
        for r in daily_rows:
            ops.append(UpdateOne({"listing_id": r["listing_id"], "date": r["date"]}, {"$set": dict(r)}, upsert=True))
            if len(ops) >= 5000:
                db["listing_daily"].bulk_write(ops, ordered=False)
                ops = []
        if ops:
            db["listing_daily"].bulk_write(ops, ordered=False)

    print("\n✓ Hoàn tất tiến trình nạp dữ liệu Seed.")


if __name__ == "__main__":
    try:
        import_all_seeds()
    except Exception as e:
        print(f"⚠ Lỗi khi kết nối MongoDB: {e}")
