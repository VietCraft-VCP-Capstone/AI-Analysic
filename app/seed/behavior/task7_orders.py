
"""
Task 7 - Sinh 25.000 đơn hàng
Cần trước: events.csv (task 6), dist_funnel.json (task 3), dist_olist.json
(task 1), buyers.csv (task 4), listings.csv + listing_variants.csv (Hạt).
Kết quả: orders.csv (~25.000 dòng) và order_items.csv (~38.000 dòng)
"""

import csv
import json
import os
import sys
from typing import Any, cast

import numpy as np
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    getattr(sys.stdout, "reconfigure")(encoding="utf-8")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
AI_ANALYSIC_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "..", ".."))


def resolve_path(rel_path: str) -> str:
    if os.path.exists(rel_path):
        return rel_path
    alt_path = os.path.join(AI_ANALYSIC_DIR, rel_path)
    if os.path.exists(alt_path):
        return alt_path
    return rel_path


# ---- Đường dẫn ----
EVENTS_PATH = resolve_path("data/seed_out/v1/events.csv")
DIST_FUNNEL_PATH = resolve_path("data/seed_out/v1/dist_funnel.json")
DIST_OLIST_PATH = resolve_path("data/seed_out/v1/dist_olist.json")
BUYERS_PATH = resolve_path("data/seed_out/v1/buyers.csv")
LISTINGS_PATH = resolve_path("data/external/products/listings.csv")
VARIANTS_PATH = resolve_path("data/external/products/listing_variants.csv")
OUT_ORDERS_PATH = resolve_path("data/seed_out/v1/orders.csv")
OUT_ITEMS_PATH = resolve_path("data/seed_out/v1/order_items.csv")

# SỬA LẠI cho khớp tên cột thật của Hạt nếu khác
COT_LISTING_ID = "listing_id"
COT_SHOP_ID = "shop_id"
COT_CREATED_AT_LISTING = "created_at"
COT_VARIANT_ID = "variant_id"
COT_VARIANT_LISTING_ID = "listing_id"
COT_GIA_BAN = "price"
COT_GIA_VON = "cost"

TY_LE_THANH_TOAN = {"cod": 45, "vnpay": 25, "momo": 20, "bank_transfer": 10}
TY_LE_HUY = 0.05
TY_LE_TRA_HANG = 0.02
TY_LE_SO_SAN_PHAM_MOI_DON = {1: 70, 2: 20, 3: 10}
TY_LE_SO_LUONG = {1: 85, 2: 10, 3: 5}


def load_gio_trong_ngay() -> tuple[np.ndarray, np.ndarray]:
    with open(DIST_OLIST_PATH, encoding="utf-8") as f:
        dist = json.load(f)
    gio = dist["gio_trong_ngay"]
    gio_list = sorted(int(k) for k in gio.keys())
    ty_le = np.array([gio[str(g)] for g in gio_list])
    return np.array(gio_list), ty_le / ty_le.sum()


def bocc_gio_theo_phan_bo(rng: Any, gio_list: Any, ty_le: Any, n: int) -> np.ndarray:
    return np.asarray(rng.choice(gio_list, size=n, p=ty_le))


def sinh_trang_thai(rng: Any, n: int) -> np.ndarray:
    huy = rng.random(n) < TY_LE_HUY
    trang_thai = np.where(huy, "cancelled", "delivered")
    con_lai_idx = np.where(trang_thai == "delivered")[0]
    tra_hang = rng.random(len(con_lai_idx)) < TY_LE_TRA_HANG
    trang_thai[con_lai_idx[tra_hang]] = "returned"
    return trang_thai


def main():
    rng = np.random.default_rng(42)
    os.makedirs(os.path.dirname(OUT_ORDERS_PATH), exist_ok=True)

    print(f"Đọc dữ liệu từ {EVENTS_PATH}...")
    events = pd.read_csv(EVENTS_PATH, parse_dates=["occurred_at"])
    listings = pd.read_csv(LISTINGS_PATH, parse_dates=[COT_CREATED_AT_LISTING])
    variants = pd.read_csv(VARIANTS_PATH)
    buyers = pd.read_csv(BUYERS_PATH, encoding="utf-8-sig", parse_dates=["created_at"])

    with open(DIST_FUNNEL_PATH, encoding="utf-8") as f:
        ty_le_cart_sang_mua = json.load(f)["ty_le_cart_sang_mua"]

    gio_list, ty_le_gio = load_gio_trong_ngay()

    buyer_created = dict(zip(buyers["buyer_id"], buyers["created_at"]))
    listing_created = dict(zip(listings[COT_LISTING_ID], listings[COT_CREATED_AT_LISTING]))
    listing_shop = dict(zip(listings[COT_LISTING_ID], listings[COT_SHOP_ID])) if COT_SHOP_ID in listings.columns else {}
    variants_theo_listing = variants.groupby(COT_VARIANT_LISTING_ID)

    cart_events = events[events["event_type"] == "add_to_cart"].reset_index(drop=True)
    print(f"Tổng lượt thêm giỏ: {len(cart_events):,}")

    thanh_don = np.asarray(rng.random(len(cart_events)) < ty_le_cart_sang_mua)
    don_hang_goc = pd.DataFrame(cart_events.loc[thanh_don]).reset_index(drop=True)
    print(f"Số lượt thành đơn: {len(don_hang_goc):,}")

    if len(don_hang_goc) >= len(cart_events):
        raise AssertionError("Số đơn phải nhỏ hơn số lượt thêm giỏ - kiểm lại Bước 2")

    orders_rows = []
    items_rows = []
    order_counter = 0
    item_counter = 0

    trang_thai_list = sinh_trang_thai(rng, len(don_hang_goc))
    thanh_toan_keys = list(TY_LE_THANH_TOAN.keys())
    thanh_toan_weights = np.array(list(TY_LE_THANH_TOAN.values())) / 100
    phuong_thuc_list = np.asarray(rng.choice(thanh_toan_keys, size=len(don_hang_goc), p=thanh_toan_weights))
    gio_dat_list = bocc_gio_theo_phan_bo(rng, gio_list, ty_le_gio, len(don_hang_goc))

    danh_sach_listing_id = np.asarray(listings[COT_LISTING_ID].values)

    for i, row in enumerate(don_hang_goc.itertuples(index=False)):
        order_counter += 1
        order_id = f"ord_{order_counter:07d}"

        buyer_id = str(getattr(row, "buyer_id"))
        listing_id_goc = str(getattr(row, "listing_id"))
        ngay_cart = pd.Timestamp(cast(Any, getattr(row, "occurred_at")))

        ordered_at = pd.Timestamp(
            year=int(ngay_cart.year),
            month=int(ngay_cart.month),
            day=int(ngay_cart.day),
            hour=int(gio_dat_list[i]),
            minute=int(rng.integers(0, 60)),
            second=int(rng.integers(0, 60)),
        )

        ngay_tao_sp = listing_created.get(listing_id_goc)
        ngay_dang_ky_buyer = buyer_created.get(buyer_id)

        if ngay_tao_sp is not None and not (ngay_tao_sp < ordered_at):
            raise AssertionError(
                f"Đơn {order_id}: ngày tạo sản phẩm {ngay_tao_sp} KHÔNG nhỏ hơn "
                f"ngày đặt đơn {ordered_at}."
            )
        if ngay_dang_ky_buyer is not None and not (ngay_dang_ky_buyer < ordered_at):
            raise AssertionError(
                f"Đơn {order_id}: buyer {buyer_id} đăng ký ngày {ngay_dang_ky_buyer} "
                f"KHÔNG nhỏ hơn ngày đặt đơn {ordered_at}."
            )

        trang_thai = str(trang_thai_list[i])
        delivered_at = ""
        if trang_thai in ("delivered", "returned"):
            so_ngay_giao = int(rng.integers(2, 8))
            delivered_at_ts = ordered_at + pd.Timedelta(days=so_ngay_giao)
            assert ordered_at < delivered_at_ts, f"Đơn {order_id}: ngày giao phải sau ngày đặt"
            delivered_at = delivered_at_ts.strftime("%Y-%m-%d %H:%M:%S")

        so_san_pham = int(rng.choice(
            list(TY_LE_SO_SAN_PHAM_MOI_DON.keys()),
            p=np.array(list(TY_LE_SO_SAN_PHAM_MOI_DON.values())) / 100,
        ))
        listing_ids_don = [listing_id_goc]
        if so_san_pham > 1:
            them = np.asarray(rng.choice(danh_sach_listing_id, size=so_san_pham - 1, replace=False))
            listing_ids_don += [str(x) for x in them if str(x) != listing_id_goc]

        tong_tien_hang = 0
        for lst_id in listing_ids_don:
            bien_the_cua_listing = None
            if lst_id in variants_theo_listing.groups:
                bien_the_cua_listing = variants_theo_listing.get_group(lst_id)
            if bien_the_cua_listing is None or bien_the_cua_listing.empty:
                continue

            bien_the = bien_the_cua_listing.sample(1, random_state=int(rng.integers(0, 1_000_000))).iloc[0]
            so_luong = int(rng.choice(
                list(TY_LE_SO_LUONG.keys()),
                p=np.array(list(TY_LE_SO_LUONG.values())) / 100,
            ))
            gia_ban = float(bien_the[COT_GIA_BAN])
            gia_von = float(bien_the[COT_GIA_VON])

            item_counter += 1
            items_rows.append(
                (order_id, lst_id, bien_the[COT_VARIANT_ID], so_luong, gia_ban, gia_von)
            )
            tong_tien_hang += gia_ban * so_luong

        shipping_fee = int(rng.integers(15_000, 45_001))
        total_vnd = tong_tien_hang + shipping_fee
        shop_id = listing_shop.get(listing_id_goc, "")

        orders_rows.append(
            (order_id, buyer_id, shop_id, ordered_at.strftime("%Y-%m-%d %H:%M:%S"),
             trang_thai, delivered_at, str(phuong_thuc_list[i]), shipping_fee, total_vnd)
        )

        if order_counter % 5000 == 0:
            print(f"  đã sinh {order_counter:,} đơn...")

    print(f"\nGhi {len(orders_rows):,} đơn ra {OUT_ORDERS_PATH}...")
    with open(OUT_ORDERS_PATH, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["order_id", "buyer_id", "shop_id", "ordered_at", "status",
                    "delivered_at", "payment_method", "shipping_fee_vnd", "total_vnd"])
        w.writerows(orders_rows)

    print(f"Ghi {len(items_rows):,} chi tiết đơn ra {OUT_ITEMS_PATH}...")
    with open(OUT_ITEMS_PATH, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["order_id", "listing_id", "variant_id", "quantity", "unit_price", "unit_cost"])
        w.writerows(items_rows)

    df_orders = pd.DataFrame(orders_rows, columns=[
        "order_id", "buyer_id", "shop_id", "ordered_at", "status",
        "delivered_at", "payment_method", "shipping_fee_vnd", "total_vnd",
    ])

    print(f"\nĐơn hàng     : {len(df_orders):,}")
    print(f"Chi tiết đơn : {len(items_rows):,}")
    for st, nhan in [("delivered", "Đã giao"), ("cancelled", "Huỷ"), ("returned", "Trả hàng")]:
        n = (df_orders["status"] == st).sum()
        print(f"{nhan:<12} : {n:>7,}  ({n / len(df_orders) * 100:.0f}%)")

    print("\nTự kiểm:")
    print(f"  Số đơn ({len(df_orders):,}) < số thêm giỏ ({len(cart_events):,}): "
          f"{'OK' if len(df_orders) < len(cart_events) else '!! SAI'}")
    print("  Tỷ lệ thanh toán thực tế:")
    for pt in thanh_toan_keys:
        ty_le_thuc = (df_orders["payment_method"] == pt).mean() * 100
        print(f"    {pt:<14} {ty_le_thuc:.1f}%  (kỳ vọng {TY_LE_THANH_TOAN[pt]}%)")


if __name__ == "__main__":
    main()
