"""
import_all_seeds.py — Nạp master data CSV của 4 thành viên vào MongoDB `vietcraft-seed`.

NGUYÊN TẮC: THIẾU FILE LÀ DỪNG, KHÔNG ĐI TIẾP.
    Bản trước trả về [] khi thiếu file rồi chạy tiếp, in "Hoàn tất" dù nạp thiếu.
    Bản này kiểm toàn bộ manifest TRƯỚC khi ghi một dòng nào, và liệt kê MỌI file
    lỗi cùng lúc thay vì dừng ở cái đầu tiên.

DỮ LIỆU CỦA HIẾU KHÔNG NẰM Ở ĐÂY.
    buyers / orders / order_items / reviews / listing_daily do Hiếu nạp thẳng vào
    Mongo, không qua CSV. Bốn đường dẫn `seed_out/v1/*.csv` mà bản trước cố đọc
    CHƯA BAO GIỜ TỒN TẠI. Script này chỉ KIỂM TRA chúng đã có trong DB, không nạp lại.

GHI BẰNG UPSERT, KHÔNG BAO GIỜ DROP.
    Chạy lại nhiều lần cho cùng kết quả. Không đụng tới collection của Hiếu.

Dùng:
    python -m app.seed.import_all_seeds --dry-run   # kiểm tra, không ghi
    python -m app.seed.import_all_seeds             # nạp thật
"""

import os
import sys
import csv
import argparse
from typing import List, Dict, Any, Tuple
from pymongo import MongoClient, UpdateOne, ASCENDING

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.dirname(BASE_DIR)
ROOT_DIR = os.path.dirname(APP_DIR)
WORKSPACE_ROOT = os.path.dirname(ROOT_DIR)
DATA_DIR = os.path.join(WORKSPACE_ROOT, "SE16-AI", "data")

sys.path.insert(0, ROOT_DIR)
from app.config import settings

NHI = "Nhi_Bui_Data Collection"
HUNG = "Hung_TaskAI"
HAT = "Le_Hat_Task_AI"

# (chủ sở hữu, đường dẫn tương đối trong SE16-AI/data, collection, khoá chính, số dòng mong đợi)
# Khoá chính lấy từ header CSV thật, đã đối chiếu ngày 21/09/2026.
MANIFEST: List[Tuple[str, str, str, str, int]] = [
    ("Nhi",  f"{NHI}/categories.csv",        "categories",         "category_id",        85),
    ("Nhi",  f"{NHI}/tags.csv",              "tags",               "tag_id",             77),
    ("Nhi",  f"{NHI}/tag_keyword_map.csv",   "tag_keyword_map",    "map_id",            118),
    ("Hưng", f"{HUNG}/vc_product_type.csv",  "vc_product_type",    "product_type_id",   138),
    ("Hưng", f"{HUNG}/vc_price_rule.csv",    "vc_price_rule",      "price_rule_id",     138),
    ("Hưng", f"{HUNG}/vc_setting.csv",       "vc_setting",         "setting_key",         4),
    ("Hưng", f"{HUNG}/vc_catalog_variant.csv","vc_catalog_variant","catalog_variant_id",25773),
    ("Hạt",  f"{HAT}/shops.csv",             "shops",              "shop_id",            80),
    ("Hạt",  f"{HAT}/listings.csv",          "listings",           "listing_id",       5000),
    ("Hạt",  f"{HAT}/listing_variants.csv",  "listing_variants",   "listing_variant_id",39920),
    ("Hạt",  "seed_out/v1/provinces.csv",    "provinces",          "province_code",      63),
]

# Dữ liệu Hiếu nạp thẳng vào Mongo — chỉ kiểm tra, không nạp lại.
BEHAVIOR_COLLECTIONS = {
    "buyers":        6000,
    "orders":       24736,
    "order_items":  34710,
    "reviews":       6882,
    "listing_daily":796025,
}

# Index tạo sau khi nạp — đây là các cột dùng để nối bảng khi dựng mart.
INDEXES = {
    "categories":         ["parent_id"],
    "tags":               ["category_id"],
    "tag_keyword_map":    ["tag_id", "keyword"],
    "vc_product_type":    ["product_group"],
    "vc_price_rule":      ["product_type_id"],
    "vc_catalog_variant": ["product_type_id", "blueprint_id"],
    "shops":              ["province_code"],
    "listings":           ["shop_id", "category_id", "product_type_id", "status"],
    "listing_variants":   ["listing_id"],
}


class SeedImportError(RuntimeError):
    """Lỗi dữ liệu đầu vào — KHÁC hẳn lỗi kết nối MongoDB."""


def read_csv_rows(path: str) -> List[Dict[str, Any]]:
    with open(path, mode="r", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def preflight() -> Dict[str, List[Dict[str, Any]]]:
    """Đọc và kiểm TOÀN BỘ manifest trước khi ghi. Gom mọi lỗi rồi báo một lần."""
    print("=== KIỂM TRA ĐẦU VÀO ===")
    problems: List[str] = []
    loaded: Dict[str, List[Dict[str, Any]]] = {}

    for owner, rel, coll, key, expect in MANIFEST:
        path = os.path.join(DATA_DIR, rel)
        if not os.path.exists(path):
            problems.append(f"THIẾU FILE  {rel}  (cần cho collection `{coll}`, chủ sở hữu: {owner})")
            continue
        try:
            rows = read_csv_rows(path)
        except Exception as e:
            problems.append(f"ĐỌC LỖI    {rel}  -> {type(e).__name__}: {e}")
            continue
        if not rows:
            problems.append(f"FILE RỖNG   {rel}  (collection `{coll}`)")
            continue
        if key not in rows[0]:
            problems.append(
                f"THIẾU CỘT   {rel}  không có cột khoá `{key}`. "
                f"Cột đang có: {', '.join(list(rows[0].keys())[:6])}..."
            )
            continue
        blank = sum(1 for r in rows if not str(r.get(key, "")).strip())
        if blank:
            problems.append(f"KHOÁ RỖNG   {rel}  {blank}/{len(rows)} dòng có `{key}` rỗng")
            continue
        uniq = len({r[key] for r in rows})
        dup = "" if uniq == len(rows) else f"  ⚠ {len(rows) - uniq} khoá trùng (upsert sẽ gộp)"
        delta = "" if len(rows) == expect else f"  ⚠ mong đợi {expect:,}"
        print(f"  ✓ {owner:4} {coll:20} {len(rows):>7,} dòng{delta}{dup}")
        loaded[coll] = rows

    if problems:
        print("\n=== DỪNG LẠI — KHÔNG GHI GÌ VÀO DATABASE ===")
        for p in problems:
            print(f"  ✗ {p}")
        raise SeedImportError(f"{len(problems)} vấn đề ở dữ liệu đầu vào. Sửa xong rồi chạy lại.")

    return loaded


def upsert_collection(db, coll_name: str, rows: List[Dict[str, Any]], key_field: str,
                      batch_size: int = 5000) -> Tuple[int, bool]:
    """Trả về (số document sau khi nạp, có bỏ qua không).

    Bỏ qua khi collection đã đủ số dòng VÀ khoá cuối cùng đã có mặt — để chạy lại
    sau khi bị ngắt giữa chừng không phải nạp lại từ đầu. Upsert vốn idempotent,
    đây chỉ là tối ưu thời gian, không đổi kết quả.
    """
    coll = db[coll_name]
    if coll.count_documents({}) >= len(rows) and coll.find_one({key_field: rows[-1][key_field]}):
        return coll.count_documents({}), True

    for i in range(0, len(rows), batch_size):
        ops = [UpdateOne({key_field: r[key_field]}, {"$set": dict(r)}, upsert=True)
               for r in rows[i:i + batch_size]]
        coll.bulk_write(ops, ordered=False)
        if len(rows) > batch_size:
            done = min(i + batch_size, len(rows))
            print(f"      {coll_name}: {done:,}/{len(rows):,}", flush=True)
    return coll.count_documents({}), False


def check_behavior_data(db) -> List[str]:
    """Dữ liệu Hiếu phải sẵn có trong DB. Thiếu thì cảnh báo, không tự nạp."""
    print("\n=== DỮ LIỆU HÀNH VI (Hiếu — nạp thẳng vào Mongo, không qua CSV) ===")
    warnings = []
    for coll, expect in BEHAVIOR_COLLECTIONS.items():
        n = db[coll].estimated_document_count()
        if n == 0:
            warnings.append(f"`{coll}` RỖNG — cần Hiếu nạp lại")
            print(f"  ✗ {coll:16} {0:>9,}  (mong đợi ~{expect:,})")
        else:
            flag = "" if abs(n - expect) <= expect * 0.05 else f"  ⚠ mong đợi ~{expect:,}"
            print(f"  ✓ {coll:16} {n:>9,}{flag}")
    return warnings


def main(dry_run: bool = False) -> int:
    loaded = preflight()

    if dry_run:
        print("\n--dry-run: đầu vào hợp lệ, KHÔNG ghi gì. Bỏ cờ này để nạp thật.")
        return 0

    dbname = settings.MONGO_DB_SEED
    print(f"\n=== NẠP VÀO `{dbname}` (upsert, không drop) ===")
    client = MongoClient(settings.MONGO_URI, serverSelectionTimeoutMS=20000)
    db = client[dbname]

    for owner, rel, coll, key, _expect in MANIFEST:
        rows = loaded[coll]
        after, skipped = upsert_collection(db, coll, rows, key)
        tag = "đã đủ, bỏ qua" if skipped else f"nạp {len(rows):>7,} dòng"
        print(f"  ✓ {coll:20} {tag} -> collection có {after:>7,} document", flush=True)

    print("\n=== TẠO INDEX ===")
    for coll, fields in INDEXES.items():
        for f in fields:
            db[coll].create_index([(f, ASCENDING)])
        print(f"  ✓ {coll:20} {', '.join(fields)}")

    warnings = check_behavior_data(db)

    print("\n=== XONG ===")
    if warnings:
        print("Còn cảnh báo:")
        for w in warnings:
            print(f"  ⚠ {w}")
        return 1
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Nạp master data CSV vào MongoDB vietcraft-seed")
    ap.add_argument("--dry-run", action="store_true", help="chỉ kiểm tra đầu vào, không ghi")
    args = ap.parse_args()
    try:
        sys.exit(main(dry_run=args.dry_run))
    except SeedImportError as e:
        print(f"\n✗ LỖI DỮ LIỆU: {e}")
        sys.exit(2)
    except Exception as e:
        print(f"\n✗ LỖI KẾT NỐI / GHI MONGODB: {type(e).__name__}: {e}")
        sys.exit(3)
