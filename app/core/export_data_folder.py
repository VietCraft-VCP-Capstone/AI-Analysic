
import os
import sys
import argparse
from datetime import datetime, timezone

import pandas as pd
import pyarrow.parquet as pyarrow_pq
from pymongo import MongoClient

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(os.path.dirname(BASE_DIR))
WORKSPACE = os.path.dirname(ROOT_DIR)
sys.path.insert(0, ROOT_DIR)
from app.config import settings

OUT = os.path.join(WORKSPACE, "vc-data")

BANG = [
    ("seed", "listing_daily",      "behavior", False),
    ("seed", "orders",             "behavior", False),
    ("seed", "order_items",        "behavior", False),
    ("seed", "reviews",            "behavior", True),
    ("seed", "buyers",             "behavior", True),
    ("seed", "listings",           "master",   True),
    ("seed", "listing_variants",   "master",   False),
    ("seed", "shops",              "master",   True),
    ("seed", "categories",         "master",   True),
    ("seed", "tags",               "master",   True),
    ("seed", "tag_keyword_map",    "master",   True),
    ("seed", "vc_product_type",    "master",   True),
    ("seed", "vc_price_rule",      "master",   True),
    ("seed", "vc_setting",         "master",   True),
    ("seed", "vc_catalog_variant", "master",   False),
    ("seed", "provinces",          "master",   True),
    ("data", "trend_interest",     "trends",   True),
    ("data", "trend_keyword",      "trends",   True),
    ("data", "trend_related",      "trends",   True),
]


# (đường dẫn nguồn, thư mục con, tên đích, đổi sang parquet?)
# Đường dẫn tương đối so với thư mục `vc-ai/`.
FILE = [
    ("SE16-AI/data/1m2/events.csv",                    "behavior",  "events",        True),
    ("AI-Analysic/app/collectors/data/trends_weekly.json", "trends", "trends_weekly", False),
    ("SE16-AI/data/seed_out/v1/dist_olist.json",       "reference", "dist_olist",    False),
    ("SE16-AI/data/seed_out/v1/dist_funnel.json",      "reference", "dist_funnel",   False),
    ("AI-Analysic/app/data/baselines.json",            "reference", "baselines",     False),
    ("AI-Analysic/app/data/seed_keywords.json",        "reference", "seed_keywords", False),
    ("AI-Analysic/data/seed_out/samples/listing_daily.csv", "samples", "listing_daily", False),
    ("AI-Analysic/data/seed_out/samples/orders.csv",        "samples", "orders",        False),
    ("AI-Analysic/data/seed_out/samples/order_items.csv",   "samples", "order_items",   False),
    ("AI-Analysic/data/seed_out/samples/reviews.csv",       "samples", "reviews",       False),
    ("AI-Analysic/data/seed_out/samples/buyers.csv",        "samples", "buyers",        False),
]


def keo_file(force: bool):
    """Kéo phần KHÔNG nằm trong MongoDB. Trả về (số dòng, số byte)."""
    import shutil
    print("\n--- TỪ FILE (thứ cố ý không nạp lên Mongo) ---")
    dong = byte = 0
    for rel, thumuc, ten, sang_parquet in FILE:
        src = os.path.join(WORKSPACE, rel)
        d = os.path.join(OUT, thumuc)
        os.makedirs(d, exist_ok=True)

        if not os.path.exists(src):
            print(f"  ✗ {ten:22} THIẾU NGUỒN: {rel}")
            continue

        if sang_parquet:
            dst = os.path.join(d, f"{ten}.parquet")
            if os.path.exists(dst) and not force:
                n = pyarrow_pq.ParquetFile(dst).metadata.num_rows
                print(f"  · {ten:22} {n:>9,} dòng   (đã có, bỏ qua)")
                dong += n; byte += os.path.getsize(dst); continue
            df = pd.read_csv(src, encoding="utf-8-sig")
            df.to_parquet(dst, index=False, compression="snappy")
            sz = os.path.getsize(dst)
            print(f"  ✓ {ten:22} {len(df):>9,} dòng   {sz/1048576:>6.1f} MB"
                  f"   (CSV gốc {os.path.getsize(src)/1048576:.0f} MB)")
            dong += len(df); byte += sz
        else:
            dst = os.path.join(d, ten + os.path.splitext(src)[1])
            if os.path.exists(dst) and not force:
                print(f"  · {ten:22} (đã có, bỏ qua)")
                byte += os.path.getsize(dst); continue
            shutil.copy2(src, dst)
            sz = os.path.getsize(dst)
            print(f"  ✓ {ten:22} {'':>9}   {sz/1048576:>6.2f} MB   chép nguyên")
            byte += sz
    return dong, byte


def main(force: bool) -> int:
    c = MongoClient(settings.MONGO_URI, serverSelectionTimeoutMS=20000)
    dbs = {"seed": c[settings.MONGO_DB_SEED], "data": c[settings.MONGO_DB_DATA]}

    print(f"=== KÉO DỮ LIỆU VỀ {OUT} ===\n")
    tong_dong = tong_byte = 0
    for khoa, coll, thumuc, ra_csv in BANG:
        d = os.path.join(OUT, thumuc)
        os.makedirs(d, exist_ok=True)
        pq = os.path.join(d, f"{coll}.parquet")

        if os.path.exists(pq) and not force:
            n = pyarrow_pq.ParquetFile(pq).metadata.num_rows
            print(f"  · {coll:22} {n:>9,} dòng   (đã có, bỏ qua — dùng --force để kéo lại)")
            tong_dong += n
            tong_byte += os.path.getsize(pq)
            continue

        docs = list(dbs[khoa][coll].find({}, {"_id": 0}))
        if not docs:
            # THIẾU ≠ 0: bảng rỗng là trạng thái hợp lệ (bảng mart chưa ai ghi vào).
            # Không tạo file rỗng, để lần sau kéo lại là có ngay.
            print(f"  · {coll:22} {0:>9}   (rỗng trên Mongo — chưa job nào ghi, bỏ qua)")
            continue

        df = pd.DataFrame(docs)
        df.to_parquet(pq, index=False, compression="snappy")
        sz = os.path.getsize(pq)
        note = ""
        if ra_csv:
            df.to_csv(os.path.join(d, f"{coll}.csv"), index=False, encoding="utf-8-sig")
            note = " + csv"
        print(f"  ✓ {coll:22} {len(df):>9,} dòng   {sz/1048576:>6.1f} MB{note}")
        tong_dong += len(df)
        tong_byte += sz

    d2, b2_ = keo_file(force)
    tong_dong += d2
    tong_byte += b2_

    # Ghi lại thời điểm kéo — để biết bản trên đĩa cũ tới mức nào so với Atlas.
    with open(os.path.join(OUT, "KEO_LUC_NAO.txt"), "w", encoding="utf-8") as f:
        f.write(f"Kéo từ MongoDB lúc: {datetime.now(timezone.utc).isoformat()}\n")
        f.write(f"Tổng: {tong_dong:,} dòng · {tong_byte/1048576:.1f} MB\n\n")
        f.write("Kéo lại khi: có người nạp thêm dữ liệu lên Atlas, hoặc cron Trends\n")
        f.write("chạy thêm vài ngày và bạn cần số mới.\n")
        f.write("  python -m app.core.export_data_folder --force\n")

    print(f"\n=== XONG: {tong_dong:,} dòng · {tong_byte/1048576:.1f} MB ===")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Kéo dữ liệu Mongo về thư mục vc-data/")
    ap.add_argument("--force", action="store_true", help="kéo lại cả bảng đã có")
    args = ap.parse_args()
    try:
        sys.exit(main(args.force))
    except Exception as e:
        print(f"\n✗ LỖI: {type(e).__name__}: {e}")
        sys.exit(2)
