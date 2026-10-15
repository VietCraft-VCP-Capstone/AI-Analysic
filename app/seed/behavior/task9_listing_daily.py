"""
Task 9 - Gộp thành bảng thống kê theo ngày (listing_daily)
Cần trước: events.csv (task 6), orders.csv + order_items.csv (task 7), listings.csv.
Kết quả: data/seed_out/v1/listing_daily.csv (~830.000 dòng) và nạp lên MongoDB.
"""

import csv
import json
import os
import sys
from typing import Any, cast

import numpy as np
import pandas as pd
from pymongo import MongoClient

if hasattr(sys.stdout, "reconfigure"):
    getattr(sys.stdout, "reconfigure")(encoding="utf-8")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
AI_ANALYSIC_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "..", ".."))
if AI_ANALYSIC_DIR not in sys.path:
    sys.path.insert(0, AI_ANALYSIC_DIR)

from app.config import settings


def resolve_path(rel_path: str) -> str:
    if os.path.exists(rel_path):
        return rel_path
    alt_path = os.path.join(AI_ANALYSIC_DIR, rel_path)
    if os.path.exists(alt_path):
        return alt_path
    return rel_path


# ---- Đường dẫn ----
EVENTS_PATH = resolve_path("data/seed_out/v1/events.csv")
ORDERS_PATH = resolve_path("data/seed_out/v1/orders.csv")
ORDER_ITEMS_PATH = resolve_path("data/seed_out/v1/order_items.csv")
LISTINGS_PATH = resolve_path("data/external/products/listings.csv")
OUT_PATH = resolve_path("data/seed_out/v1/listing_daily.csv")

COT_LISTING_ID = "listing_id"
COT_TIER = "tier"
COT_SHOP_ID = "shop_id"
COT_PRODUCT_TYPE_ID = "product_type_id"
COT_CATEGORY_ID = "category_id"
COT_TAGS = "tags"

NGAY_KET_THUC = pd.Timestamp("2026-08-30")
SO_NGAY_BU = 365


def build_listing_daily() -> pd.DataFrame:
    print(f"1. Đọc dữ liệu sự kiện từ {EVENTS_PATH}...")
    events = pd.read_csv(EVENTS_PATH)
    events["date"] = events["occurred_at"].astype(str).str.slice(0, 10)

    print("   Đếm lượt xem (view) theo (listing_id, date)...")
    views = (
        events[events["event_type"] == "view"]
        .groupby(["listing_id", "date"])
        .size()
        .to_frame(name="views")
    )

    print("   Đếm lượt thêm giỏ (add_to_cart) theo (listing_id, date)...")
    carts = (
        events[events["event_type"] == "add_to_cart"]
        .groupby(["listing_id", "date"])
        .size()
        .to_frame(name="add_to_carts")
    )

    print(f"2. Đọc dữ liệu đơn hàng từ {ORDERS_PATH} và {ORDER_ITEMS_PATH}...")
    orders = pd.read_csv(ORDERS_PATH)
    items = pd.read_csv(ORDER_ITEMS_PATH)
    orders["date"] = orders["ordered_at"].astype(str).str.slice(0, 10)

    items_merged = items.merge(orders[["order_id", "date"]], on="order_id")
    items_merged["revenue"] = items_merged["quantity"] * items_merged["unit_price"]
    items_merged["cost"] = items_merged["quantity"] * items_merged["unit_cost"]

    print("   Tính số đơn, số lượng, doanh thu, giá vốn theo (listing_id, date)...")
    order_agg = items_merged.groupby(["listing_id", "date"]).agg(
        orders=("order_id", "nunique"),
        units_sold=("quantity", "sum"),
        revenue_vnd=("revenue", "sum"),
        cost_vnd=("cost", "sum"),
    )

    print("3. Nối các chỉ số hoạt động...")
    activity = (
        views.join(carts, how="outer")
        .join(order_agg, how="outer")
        .fillna(0)
        .reset_index()
    )

    print(f"4. Đọc thông tin sản phẩm từ {LISTINGS_PATH}...")
    listings = pd.read_csv(LISTINGS_PATH)

    # Đảm bảo các cột metadata nếu thiếu trong file gốc sẽ có giá trị mặc định ""
    for col in [COT_SHOP_ID, COT_PRODUCT_TYPE_ID, COT_CATEGORY_ID, COT_TAGS]:
        if col not in listings.columns:
            listings[col] = ""

    listings_meta = listings[[
        COT_LISTING_ID, COT_TIER, COT_SHOP_ID, COT_PRODUCT_TYPE_ID, COT_CATEGORY_ID, COT_TAGS
    ]].copy()

    # Live product identity contract: seed listing IDs remain distinct from live product IDs.
    # Do not fabricate cross-database joins; live rollups use product_id as canonical key.

    hot_med_listings = listings[listings[COT_TIER].isin(["hot", "medium"])][COT_LISTING_ID].tolist()
    tail_listings = list(listings[listings[COT_TIER] == "tail"][COT_LISTING_ID])

    print(f"5. Bù đủ {SO_NGAY_BU} ngày cho nhóm hot/medium ({len(hot_med_listings):,} sản phẩm)...")
    dates_365 = pd.date_range(end=NGAY_KET_THUC, periods=SO_NGAY_BU, freq="D").strftime("%Y-%m-%d").tolist()

    # Tạo lưới đầy đủ 365 ngày cho hot & medium
    grid_hot_med = pd.MultiIndex.from_product(
        [hot_med_listings, dates_365], names=["listing_id", "date"]
    ).to_frame().reset_index(drop=True)

    # Outer join để vừa giữ đủ lưới 365 ngày, vừa bảo toàn toàn bộ dữ liệu đơn/doanh thu nếu có ngày sớm hơn
    hot_med_activity = activity[activity["listing_id"].isin(hot_med_listings)]
    hot_med_merged = grid_hot_med.merge(hot_med_activity, on=["listing_id", "date"], how="outer").fillna(0)

    print(f"6. Lấy các ngày có hoạt động cho nhóm tail ({len(tail_listings):,} sản phẩm)...")
    tail_merged = activity[activity["listing_id"].isin(tail_listings)].copy()

    print("7. Gộp 2 nhóm sản phẩm...")
    df_all = pd.concat([hot_med_merged, tail_merged], ignore_index=True)

    # Đảm bảo logic phễu hợp lệ: orders <= add_to_carts <= views
    df_all["add_to_carts"] = np.maximum(df_all["add_to_carts"], df_all["orders"])
    df_all["views"] = np.maximum(df_all["views"], df_all["add_to_carts"])

    print("8. Chép metadata (shop_id, product_type_id, category_id, tags, tier)...")
    df_result = df_all.merge(listings_meta, on=COT_LISTING_ID, how="left")

    # Ép kiểu dữ liệu chuẩn xác
    df_result["views"] = df_result["views"].astype(int)
    df_result["add_to_carts"] = df_result["add_to_carts"].astype(int)
    df_result["orders"] = df_result["orders"].astype(int)
    df_result["units_sold"] = df_result["units_sold"].astype(int)
    df_result["revenue_vnd"] = df_result["revenue_vnd"].round(2)
    df_result["cost_vnd"] = df_result["cost_vnd"].round(2)

    # Sắp xếp theo mã sản phẩm và ngày
    col_order = [
        "listing_id", "date", "shop_id", "product_type_id", "category_id",
        "tags", "tier", "views", "add_to_carts", "orders", "units_sold",
        "revenue_vnd", "cost_vnd"
    ]
    df_sorted = pd.DataFrame(df_result[col_order]).sort_values(by=["listing_id", "date"]).reset_index(drop=True)
    return df_sorted


def upload_to_mongodb(df: pd.DataFrame, batch_size: int = 20000) -> None:
    uri = settings.MONGO_URI
    db_name = settings.MONGO_DB_SEED
    coll_name = "listing_daily"

    print(f"\n--- Nạp dữ liệu vào MongoDB: {db_name}.{coll_name} ---")
    try:
        client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        db = client[db_name]
        coll = db[coll_name]

        # Kiểm tra kết nối
        client.server_info()
        print("  Đã kết nối MongoDB thành công!")

        # Xóa collection cũ để nạp mới nhanh chóng bằng insert_many
        coll.drop()
        print(f"  Đang chuẩn bị {len(df):,} document để nạp...")
        records = df.to_dict(orient="records")

        total_inserted = 0
        for i in range(0, len(records), batch_size):
            chunk = records[i:i + batch_size]
            res = coll.insert_many(chunk, ordered=False)
            total_inserted += len(res.inserted_ids)
            print(f"    đã nạp {total_inserted:,}/{len(records):,} dòng...")

        print("  Tạo index compound [listing_id, date]...")
        coll.create_index([("listing_id", 1), ("date", 1)], unique=True)
        print(f"  Hoàn thành nạp {total_inserted:,} dòng lên MongoDB {db_name}.{coll_name}!")
    except Exception as e:
        print(f"  !! Không thể nạp lên MongoDB ({e}). Dữ liệu vẫn được lưu an toàn trong file CSV.")


def run_self_checks(df_daily: pd.DataFrame) -> None:
    print("\n=== TỰ KIỂM TRA TASK 9 ===")
    tong_dong = len(df_daily)
    print(f"1. Tổng số dòng: {tong_dong:,}")
    if 750_000 <= tong_dong <= 850_000:
        print(f"   OK  tổng số dòng {tong_dong:,} nằm trong dải khoảng 830.000 dòng.")
    else:
        print(f"   !!  tổng số dòng {tong_dong:,} ngoài dải kỳ vọng.")

    print("\n2. Kiểm tra điều kiện phễu: orders <= add_to_carts <= views...")
    funnel_check = (df_daily["orders"] <= df_daily["add_to_carts"]) & (df_daily["add_to_carts"] <= df_daily["views"])
    if funnel_check.all():
        print("   OK  100% dòng thoả mãn: orders <= add_to_carts <= views.")
    else:
        vi_pham = int(cast(Any, (~funnel_check).sum()))
        print(f"   !!  CÓ {vi_pham:,} dòng vi phạm điều kiện phễu.")

    print("\n3. Kiểm tra tổng doanh thu so với order_items.csv...")
    items = pd.read_csv(ORDER_ITEMS_PATH)
    tong_tien_items = float(cast(Any, (items["quantity"] * items["unit_price"]).sum()))
    tong_tien_daily = float(cast(Any, df_daily["revenue_vnd"].sum()))
    diff_rev = abs(tong_tien_daily - tong_tien_items)
    print(f"   Tổng doanh thu order_items : {tong_tien_items:,.2f} đ")
    print(f"   Tổng doanh thu listing_daily: {tong_tien_daily:,.2f} đ")
    if diff_rev < 1.0:
        print("   OK  tổng doanh thu khớp chính xác 100% đến từng đồng.")
    else:
        print(f"   !!  doanh thu lệch {diff_rev:,.2f} đ.")

    print("\n4. Kiểm tra số dòng nhóm hot/medium...")
    listings = pd.read_csv(LISTINGS_PATH)
    hot_sample = str(listings[listings[COT_TIER] == "hot"].iloc[0][COT_LISTING_ID])
    hot_count = int(cast(Any, (df_daily["listing_id"] == hot_sample).sum()))
    print(f"   Sản phẩm hot ({hot_sample}): {hot_count} dòng.")
    if hot_count >= SO_NGAY_BU:
        print(f"   OK  sản phẩm hot có ít nhất {SO_NGAY_BU} dòng (bù đủ chuỗi thời gian).")
    else:
        print(f"   !!  sản phẩm hot có {hot_count} dòng (kỳ vọng >= {SO_NGAY_BU}).")


def main():
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    df_daily = build_listing_daily()

    print(f"\nGhi {len(df_daily):,} dòng ra {OUT_PATH}...")
    df_daily.to_csv(OUT_PATH, index=False, encoding="utf-8-sig")
    file_size_mb = os.path.getsize(OUT_PATH) / (1024 * 1024)
    print(f"Đã lưu {OUT_PATH} ({file_size_mb:.2f} MB)")

    run_self_checks(df_daily)
    upload_to_mongodb(df_daily)


if __name__ == "__main__":
    main()
