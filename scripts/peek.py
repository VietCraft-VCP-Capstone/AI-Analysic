#!/usr/bin/env python
"""
peek.py — Nhìn nhanh vào một bảng MongoDB: có bao nhiêu dòng, cột nào, mẫu ra sao.

Gần như task nào cũng mở đầu bằng "Bước 1 — xác nhận bằng số". Đây là công cụ cho
bước đó. Nó TỰ TÌM bảng trong cả ba database nên không phải nhớ bảng nào nằm đâu.

    python scripts/peek.py listing_daily
    python scripts/peek.py orders --limit 5
    python scripts/peek.py mart_listing_daily --limit 2

Bảng không có thì nó LIỆT KÊ bảng đang có ở cả ba database — sai tên là thấy ngay,
không phải đoán.
"""

import os
import sys
import json
import argparse

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(BASE_DIR)
sys.path.insert(0, ROOT_DIR)

from pymongo import MongoClient
from app.config import settings

# Thứ tự tìm: mồi trước (dùng nhiều nhất), rồi thu thập, rồi sàn live.
DATABASES = [settings.MONGO_DB_SEED, "data-collection", "vietcraft"]


def _short(v, width: int = 58) -> str:
    if isinstance(v, (dict, list)):
        v = json.dumps(v, ensure_ascii=False)
    s = str(v)
    return s if len(s) <= width else s[:width - 1] + "…"


def main() -> int:
    ap = argparse.ArgumentParser(description="Nhìn nhanh vào một bảng MongoDB")
    ap.add_argument("collection", help="tên bảng, ví dụ listing_daily")
    ap.add_argument("--limit", type=int, default=3, help="số dòng mẫu (mặc định 3)")
    ap.add_argument("--db", default="", help="ép tìm trong một database cụ thể")
    args = ap.parse_args()

    client = MongoClient(settings.MONGO_URI, serverSelectionTimeoutMS=15000)
    targets = [args.db] if args.db else DATABASES

    found = None
    for dbn in targets:
        if args.collection in client[dbn].list_collection_names():
            found = dbn
            break

    if not found:
        print(f"✗ Không có bảng `{args.collection}` trong: {', '.join(targets)}\n")
        print("Bảng đang có:")
        for dbn in targets:
            names = sorted(client[dbn].list_collection_names())
            print(f"\n  [{dbn}]  {len(names)} bảng")
            for n in names:
                print(f"    {n:32} {client[dbn][n].estimated_document_count():>9,}")
        return 1

    coll = client[found][args.collection]
    total = coll.count_documents({})
    print(f"=== {args.collection}  ·  database `{found}` ===")
    print(f"  {total:,} dòng")

    if total == 0:
        # THIẾU ≠ 0: bảng rỗng là trạng thái hợp lệ trước khi job chạy lần đầu,
        # không phải lỗi. Nói rõ để không ai tưởng mình kết nối sai.
        print("  (bảng rỗng — bình thường nếu job ghi vào nó chưa chạy lần nào)")
        return 0

    doc = coll.find_one()
    fields = sorted(k for k in doc if k != "_id")
    print(f"  {len(fields)} cột: {', '.join(fields)}")

    # Cột nào rỗng hết thì phải nói — đây là loại lỗi im lặng hay gặp nhất
    # trong dự án này (listing_daily có 4 cột khoá rỗng 100%).
    blank = []
    for f in fields:
        n = coll.count_documents({f: {"$in": ["", None]}})
        if n == total:
            blank.append(f)
    if blank:
        print(f"  ⚠ RỖNG 100%: {', '.join(blank)}  — không nối bảng bằng mấy cột này được")

    print(f"\n  {min(args.limit, total)} dòng mẫu:")
    for i, d in enumerate(coll.find().limit(args.limit), 1):
        print(f"  --- {i} ---")
        for f in fields:
            print(f"    {f:22} {_short(d.get(f))}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"✗ LỖI: {type(e).__name__}: {e}")
        sys.exit(2)
