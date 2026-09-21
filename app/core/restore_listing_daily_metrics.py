"""
restore_listing_daily_metrics.py — Dựng lại 7 cột số của `listing_daily`.

VÌ SAO CẦN: ngày 21/09/2026 một lượt $merge dùng nhầm `whenMatched: "replace"`
(đáng lẽ "merge") sau một $project chỉ giữ cột khoá — nên views / add_to_carts /
orders / units_sold / revenue_vnd / cost_vnd / tier bị xoá khỏi cả 796.025 dòng.
Cột khoá (shop_id, product_type_id, category_id, tags) thì đã điền đúng và giữ nguyên.

TÍNH LẠI TỪ ĐÂU — đúng cách task9_listing_daily.py đã làm:
    views, add_to_carts   <- SE16-AI/data/1m2/events.csv  (1.271.298 dòng)
    orders, units_sold,   <- Mongo `orders` + `order_items`
    revenue_vnd, cost_vnd    (bản CSV của Hiếu chưa từng tồn tại, dữ liệu ở Mongo)
    tier                  <- Mongo `listings`

ĐỐI CHIẾU BẮT BUỘC: AI-Analysic/data/seed_out/samples/listing_daily.csv giữ 100
dòng dữ liệu GỐC. Script phải khớp 100/100 dòng đó thì mới được ghi. Không khớp
là dừng — thà không khôi phục còn hơn khôi phục sai.

    python -m app.core.restore_listing_daily_metrics --check   # chỉ đối chiếu
    python -m app.core.restore_listing_daily_metrics           # đối chiếu rồi ghi
"""

import os
import sys
import argparse

import pandas as pd
from pymongo import MongoClient, UpdateOne
from pymongo.errors import OperationFailure

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.dirname(BASE_DIR)
ROOT_DIR = os.path.dirname(APP_DIR)
WORKSPACE = os.path.dirname(ROOT_DIR)
sys.path.insert(0, ROOT_DIR)
from app.config import settings

EVENTS = os.path.join(WORKSPACE, "SE16-AI/data/1m2/events.csv")
SAMPLE = os.path.join(ROOT_DIR, "data/seed_out/samples/listing_daily.csv")
METRICS = ["views", "add_to_carts", "orders", "units_sold", "revenue_vnd", "cost_vnd"]


def build() -> pd.DataFrame:
    print("1. Đọc events.csv ...", flush=True)
    ev = pd.read_csv(EVENTS, encoding="utf-8-sig",
                     usecols=["listing_id", "event_type", "occurred_at"])
    ev["date"] = ev["occurred_at"].str.slice(0, 10)
    print(f"   {len(ev):,} sự kiện")

    views = (ev[ev.event_type == "view"].groupby(["listing_id", "date"]).size()
             .to_frame("views"))
    carts = (ev[ev.event_type == "add_to_cart"].groupby(["listing_id", "date"]).size()
             .to_frame("add_to_carts"))

    print("2. Đọc orders + order_items từ Mongo ...", flush=True)
    c = MongoClient(settings.MONGO_URI, serverSelectionTimeoutMS=20000)
    db = c[settings.MONGO_DB_SEED]
    od = pd.DataFrame(list(db.orders.find({}, {"_id": 0, "order_id": 1, "ordered_at": 1})))
    it = pd.DataFrame(list(db.order_items.find(
        {}, {"_id": 0, "order_id": 1, "listing_id": 1, "quantity": 1,
             "unit_price": 1, "unit_cost": 1})))
    print(f"   {len(od):,} đơn · {len(it):,} dòng đơn")

    m = it.merge(od, on="order_id", how="inner")
    m["date"] = m["ordered_at"].str.slice(0, 10)
    m["revenue"] = m["quantity"] * m["unit_price"]
    m["cost"] = m["quantity"] * m["unit_cost"]
    sales = m.groupby(["listing_id", "date"]).agg(
        orders=("order_id", "nunique"),
        units_sold=("quantity", "sum"),
        revenue_vnd=("revenue", "sum"),
        cost_vnd=("cost", "sum"),
    )

    print("3. Gộp và áp ràng buộc phễu ...", flush=True)
    df = views.join(carts, how="outer").join(sales, how="outer").fillna(0)
    # task9 dòng 137-139: orders <= add_to_carts <= views. Giữ nguyên quy tắc đó.
    df["add_to_carts"] = df[["add_to_carts", "orders"]].max(axis=1)
    df["views"] = df[["views", "add_to_carts"]].max(axis=1)
    for col in ["views", "add_to_carts", "orders", "units_sold"]:
        df[col] = df[col].astype(int)
    df["revenue_vnd"] = df["revenue_vnd"].round(2)
    df["cost_vnd"] = df["cost_vnd"].round(2)
    return df.reset_index()


def check(df: pd.DataFrame) -> bool:
    """Đối chiếu với 100 dòng gốc còn giữ được. Không khớp là dừng."""
    print("\n4. ĐỐI CHIẾU với 100 dòng gốc ...", flush=True)
    s = pd.read_csv(SAMPLE, encoding="utf-8-sig")
    j = s[["listing_id", "date"] + METRICS].merge(
        df, on=["listing_id", "date"], how="left", suffixes=("_goc", "_moi"))
    for col in METRICS:
        j[f"{col}_moi"] = j[f"{col}_moi"].fillna(0)

    bad = 0
    for col in METRICS:
        diff = (j[f"{col}_goc"] - j[f"{col}_moi"]).abs()
        n = int((diff > 0.01).sum())
        print(f"   {col:14} lệch {n:>3}/{len(j)} dòng" + ("" if n == 0 else "   ✗"))
        bad += n
    if bad:
        print("\n   Ví dụ dòng lệch:")
        mask = (j["views_goc"] - j["views_moi"]).abs() > 0.01
        print(j[mask].head(3).to_string(index=False))
    return bad == 0


def main(check_only: bool) -> int:
    df = build()
    print(f"   {len(df):,} cặp (listing_id, date) có số liệu khác 0")

    if not check(df):
        print("\n✗ KHÔNG KHỚP DỮ LIỆU GỐC — DỪNG, không ghi gì.")
        return 1
    print("   ✓ khớp 100/100 dòng gốc")

    if check_only:
        print("\n--check: chỉ đối chiếu, không ghi.")
        return 0

    c = MongoClient(settings.MONGO_URI, serverSelectionTimeoutMS=20000)
    db = c[settings.MONGO_DB_SEED]

    # CHỐT HẠN MỨC. Cụm là Atlas M0 free 512 MB DÙNG CHUNG CẢ NHÓM — vượt là
    # Atlas chặn ghi với TẤT CẢ mọi người, không riêng người chạy. Đã xảy ra
    # sáng 21/09 (526/512 MB). Ước lượng trước, và dừng ngay khi Atlas kêu.
    used = sum(c[d].command("dbstats")["storageSize"] + c[d].command("dbstats")["indexSize"]
               for d in ["vietcraft-seed", "data-collection", "vietcraft"])
    print(f"\n   dung lượng đang dùng (ước): {used/1048576:.1f} MB")
    print(f"   lượt ghi này chỉ ĐẶT LẠI trường đã từng có, không tạo document mới")

    # CHIA THEO THÁNG. update_many trên cả 796k dòng vượt giới hạn thời gian của
    # Atlas M0 (đã gặp: MaxTimeMSExpired sau khi xong 613.156/796.025 dòng).
    # Cùng loại giới hạn đã bắt $merge phải chia nhỏ ở backfill_listing_daily_ids.py.
    print("\n5. Đặt 6 cột số về 0, chia theo tháng ...", flush=True)
    zero = {k: (0.0 if "vnd" in k else 0) for k in METRICS}
    months = [d["_id"] for d in db.listing_daily.aggregate([
        {"$group": {"_id": {"$substr": ["$date", 0, 7]}, "n": {"$sum": 1}}},
        {"$sort": {"_id": 1}}])]
    for mth in months:
        db.listing_daily.update_many({"date": {"$regex": f"^{mth}"}}, {"$set": zero})
    print(f"   xong {len(months)} tháng")

    print(f"6. Ghi {len(df):,} cặp có số liệu ...", flush=True)
    ops, done = [], 0
    for r in df.itertuples(index=False):
        ops.append(UpdateOne(
            {"listing_id": r.listing_id, "date": r.date},
            {"$set": {k: getattr(r, k) for k in METRICS}}))
        if len(ops) >= 5000:
            try:
                db.listing_daily.bulk_write(ops, ordered=False)
            except OperationFailure as e:
                if "space quota" in str(e):
                    print(f"\n   ✗ ATLAS HẾT DUNG LƯỢNG ở {done:,}/{len(df):,}. DỪNG NGAY.")
                    print("     Cụm dùng chung — ghi tiếp là chặn ghi với cả nhóm.")
                    print("     Chạy lại script này sau khi giải phóng chỗ; nó idempotent.")
                    return 1
                raise
            done += len(ops); ops = []
            if done % 50000 == 0:
                print(f"   {done:,}/{len(df):,}", flush=True)
    if ops:
        db.listing_daily.bulk_write(ops, ordered=False); done += len(ops)
    print(f"   {done:,}/{len(df):,}", flush=True)

    print("\n7. Dựng lại cột tier từ listings ...", flush=True)
    tiers = {}
    for d in db.listings.find({}, {"_id": 0, "listing_id": 1, "tier": 1}):
        tiers.setdefault(d.get("tier", "medium"), []).append(d["listing_id"])
    for t, ids in tiers.items():
        db.listing_daily.update_many({"listing_id": {"$in": ids}}, {"$set": {"tier": t}})
        print(f"   tier={t:8} {len(ids):>5,} listing")

    print("\n8. KIỂM TRA SAU KHI GHI", flush=True)
    tot = db.listing_daily.count_documents({})
    agg = list(db.listing_daily.aggregate([{"$group": {
        "_id": None, "rev": {"$sum": "$revenue_vnd"},
        "v": {"$sum": "$views"}, "o": {"$sum": "$orders"}}}]))[0]
    print(f"   {tot:,} dòng · {agg['v']:,} lượt xem · {agg['o']:,} đơn · {agg['rev']:,.0f} đ")
    if agg["rev"] <= 0:
        print("   ✗ tổng doanh thu vẫn 0 — KHÔNG ĐẠT")
        return 1
    print("\n=== KHÔI PHỤC XONG ===")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="chỉ đối chiếu, không ghi")
    args = ap.parse_args()
    try:
        sys.exit(main(args.check))
    except Exception as e:
        print(f"\n✗ LỖI: {type(e).__name__}: {e}")
        sys.exit(2)
