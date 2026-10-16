
import os
import sys
import uuid
import argparse
from datetime import datetime, timezone
from typing import Any, Dict

from pymongo import MongoClient, ASCENDING

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.dirname(BASE_DIR)
ROOT_DIR = os.path.dirname(APP_DIR)
sys.path.insert(0, ROOT_DIR)

from app.config import settings
from app.core.writer import MART_SCHEMA, MartWriteError

TARGET = "listing_daily"   # sửa tại chỗ, không sinh bảng mới
SOURCE = "listing_daily"
JOIN = "listings"
MODEL_VERSION = "backfill-1.0"
SCOPE = "listing_day"

# Cột khoá nối bị rỗng trong nguồn, phải lấy từ `listings`.
JOIN_FIELDS = ["shop_id", "product_type_id", "category_id", "tags"]
# Cột số giữ nguyên từ nguồn.
METRIC_FIELDS = ["views", "add_to_carts", "orders", "units_sold", "revenue_vnd", "cost_vnd"]


# Khoá của listing_daily. KHÔNG lấy từ MART_SCHEMA vì đây là bảng THÔ, không
# phải mart — MART_SCHEMA chỉ quản các bảng kết quả model và 4 bảng nền.
KEY = ["listing_id", "date"]


def _check_contract() -> list:
    """Khoá phải thật sự duy nhất trong bảng, nếu không $merge sẽ gộp nhầm dòng."""
    if TARGET in MART_SCHEMA:
        raise MartWriteError(
            f"`{TARGET}` là bảng THÔ nhưng đang nằm trong MART_SCHEMA — gỡ ra, "
            f"kẻo job mart khác ghi đè lên dữ liệu gốc của Hiếu."
        )
    return KEY


def _pipeline(run_id: str, computed_at: str, limit: int = 0, month: str = "") -> list:
    stages: list = []
    if month:
        # Lọc theo tháng TRƯỚC $lookup — đây là thứ giữ mỗi lượt chạy đủ nhỏ.
        stages.append({"$match": {"date": {"$regex": f"^{month}"}}})
    if limit:
        stages.append({"$limit": limit})

    stages += [
        # Nối sang listings để lấy 4 khoá đang rỗng.
        {"$lookup": {
            "from": JOIN,
            "localField": "listing_id",
            "foreignField": "listing_id",
            "as": "_l",
        }},
        {"$addFields": {"_l": {"$first": "$_l"}}},
        {"$project": {
            "_id": 0,
            "listing_id": 1,
            "date": 1,
            **{f: {"$ifNull": [f"$_l.{f}", None]} for f in JOIN_FIELDS},
           
        }},
    ]
    return stages


def main(dry_run: bool = False) -> int:
    key = _check_contract()
    run_id = f"run_{TARGET}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    computed_at = datetime.now(timezone.utc).isoformat()

    client = MongoClient(settings.MONGO_URI, serverSelectionTimeoutMS=20000)
    db = client[settings.MONGO_DB_SEED]

    n_src = db[SOURCE].estimated_document_count()
    n_join = db[JOIN].estimated_document_count()
    print(f"=== ĐIỀN 4 CỘT KHOÁ TRONG `{TARGET}` (sửa tại chỗ) ===")
    print(f"  nguồn  {SOURCE:16} {n_src:>9,} dòng")
    print(f"  nối    {JOIN:16} {n_join:>9,} dòng")
    print(f"  khoá   {key}")
    print(f"  run_id {run_id}")

    if dry_run:
        sample = list(db[SOURCE].aggregate(_pipeline(run_id, computed_at, limit=3)))
        print("\n--dry-run: 3 dòng mẫu, KHÔNG ghi gì\n")
        print("  (chỉ 4 cột dưới được ghi đè; views/orders/revenue giữ nguyên)")
        for d in sample:
            print("  ", {k: d.get(k) for k in ["listing_id", "date"] + JOIN_FIELDS})
        return 0

    # $merge cần index duy nhất trên khoá — tạo trước khi chạy.
    db[TARGET].create_index([(k, ASCENDING) for k in key], unique=True)

    # CHIA THEO THÁNG. Chạy một phát cho cả 796k dòng thì Atlas bản free ném
    # MaxTimeMSExpired giữa chừng (đã gặp: dừng ở 74.540 dòng). Mỗi tháng tối đa
    # ~67k dòng, nằm gọn trong hạn mức. $merge whenMatched=merge là idempotent
    # nên ngắt giữa chừng thì chạy lại là xong.
    months = [d["_id"] for d in db[SOURCE].aggregate([
        {"$group": {"_id": {"$substr": ["$date", 0, 7]}, "n": {"$sum": 1}}},
        {"$sort": {"_id": 1}},
    ])]
    print(f"\n  chạy $lookup + $merge trong MongoDB, chia {len(months)} tháng:")
    done = 0
    for m in months:
        db[SOURCE].aggregate(
            _pipeline(run_id, computed_at, month=m) +
            [{"$merge": {"into": TARGET, "on": key,
                         "whenMatched": "merge", "whenNotMatched": "discard"}}],
            maxTimeMS=600_000,
        )
        done = db[TARGET].count_documents({})
        print(f"    {m}  ->  {done:>9,} dòng", flush=True)

    # Xuất xứ: một document trong model_run, không lặp trên 796.025 dòng.
    db["model_run"].update_one({"run_id": run_id}, {"$set": {
        "run_id": run_id, "model_name": os.path.basename(__file__)[:-3],
        "model_version": MODEL_VERSION, "scope": SCOPE,
        "started_at": computed_at, "finished_at": computed_at,
        "status": "COMPLETED", "target": TARGET, "key": key,
        "fields_filled": JOIN_FIELDS,
    }}, upsert=True)
    print(f"  ✓ xuất xứ ghi vào model_run: {run_id}")

    print("\n=== TẠO INDEX TRA CỨU ===")
    for f in ["shop_id", "category_id", "product_type_id", "date"]:
        db[TARGET].create_index([(f, ASCENDING)])
        print(f"  ✓ {f}")

    print("\n=== KIỂM TRA SAU KHI DỰNG ===")
    n_out = db[TARGET].count_documents({})
    print(f"  {TARGET:20} {n_out:>9,} dòng  (trước {n_src:,} — phải bằng nhau)")
    if n_out != n_src:
        print(f"  ✗ SỐ DÒNG ĐỔI {abs(n_out - n_src):,} — sửa tại chỗ không được thêm/bớt dòng")
        return 1

    still_blank = db[TARGET].count_documents({"shop_id": ""})
    print(f"  còn chuỗi rỗng         : {still_blank:>9,}  (phải = 0)")
    orphan = db[TARGET].count_documents({"shop_id": None})
    print(f"  không nối được listing : {orphan:>9,}  ({orphan * 100 / max(n_out,1):.1f}%)")
    for f in JOIN_FIELDS[:3]:
        filled = db[TARGET].count_documents({f: {"$nin": [None, ""]}})
        print(f"  {f:22} đã điền {filled:>9,}  ({filled * 100 / max(n_out,1):.1f}%)")

    blank = db[TARGET].count_documents({"$or": [{k: ""} for k in JOIN_FIELDS]})
    if blank:
        print(f"  ✗ còn {blank:,} dòng có khoá nối là CHUỖI RỖNG — phải là null")
        return 1

    print("\n=== THỬ ĐÚNG THỨ F26/F31 CẦN ===")
    top = list(db[TARGET].aggregate([
        {"$match": {"shop_id": {"$ne": None}}},
        {"$group": {"_id": "$shop_id", "revenue": {"$sum": "$revenue_vnd"}, "orders": {"$sum": "$orders"}}},
        {"$sort": {"revenue": -1}}, {"$limit": 3},
    ]))
    print("  doanh thu theo shop (F26) — top 3:")
    for r in top:
        print(f"    {r['_id']:12} {r['revenue']:>14,.0f} đ   {r['orders']:>6,} đơn")
    cat = list(db[TARGET].aggregate([
        {"$match": {"category_id": {"$ne": None}}},
        {"$group": {"_id": "$category_id", "revenue": {"$sum": "$revenue_vnd"}}},
        {"$sort": {"revenue": -1}}, {"$limit": 3},
    ]))
    print("  doanh thu theo danh mục (F31) — top 3:")
    for r in cat:
        print(f"    {r['_id']:22} {r['revenue']:>14,.0f} đ")

    print(f"\n=== XONG — `{TARGET}` sẵn sàng cho F26 · F27 · F30 · F31 · F37 ===")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=f"Dựng bảng nền {TARGET}")
    ap.add_argument("--dry-run", action="store_true", help="xem mẫu, không ghi")
    args = ap.parse_args()
    try:
        sys.exit(main(dry_run=args.dry_run))
    except MartWriteError as e:
        print(f"\n✗ SAI HỢP ĐỒNG MART: {e}")
        sys.exit(2)
    except Exception as e:
        print(f"\n✗ LỖI MONGODB: {type(e).__name__}: {e}")
        sys.exit(3)
