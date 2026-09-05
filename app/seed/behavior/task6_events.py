"""
Task 6 - Sinh 1,2 triệu lượt xem và thêm giỏ
Cần trước: listings.csv (khung sản phẩm của Hạt), buyers.csv (task 4),
dist_olist.json (task 1), dist_funnel.json (task 3), he_so_mua_vu (task 5).
Kết quả: data/seed_out/v1/events.csv (~1,2 triệu dòng)
"""

import csv
import json
import os
import sys
from datetime import datetime, timedelta
from typing import Any, cast

import numpy as np
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    getattr(sys.stdout, "reconfigure")(encoding="utf-8")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
AI_ANALYSIC_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "..", ".."))
if AI_ANALYSIC_DIR not in sys.path:
    sys.path.insert(0, AI_ANALYSIC_DIR)
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from app.seed.behavior.task5_seasonal import he_so_mua_vu  # noqa: E402


def resolve_path(rel_path: str) -> str:
    if os.path.exists(rel_path):
        return rel_path
    alt_path = os.path.join(AI_ANALYSIC_DIR, rel_path)
    if os.path.exists(alt_path):
        return alt_path
    return rel_path


# ---- Đường dẫn ----
LISTINGS_PATH = resolve_path("data/external/products/listings.csv")
BUYERS_PATH = resolve_path("data/seed_out/v1/buyers.csv")
DIST_OLIST_PATH = resolve_path("data/seed_out/v1/dist_olist.json")
DIST_FUNNEL_PATH = resolve_path("data/seed_out/v1/dist_funnel.json")
OUT_PATH = resolve_path("data/seed_out/v1/events.csv")
QC_IMG_PATH = resolve_path("docs/qc/luot_xem_theo_ngay.png")

# Nếu file của Hạt đặt tên cột khác, sửa 4 dòng này
COT_LISTING_ID = "listing_id"
COT_TIER = "tier"
COT_TOPIC = "topic"
COT_CREATED_AT = "created_at"

NGAY_KET_THUC: pd.Timestamp = cast(pd.Timestamp, pd.Timestamp("2026-08-30"))

MUC_NEN_THEO_TIER = {"hot": 6.45, "medium": 1.02, "tail": 0.17}


def he_so_tuoi(so_ngay_tuoi: int) -> float:
    if so_ngay_tuoi < 7:
        return 1.8
    if so_ngay_tuoi < 14:
        return 1.4
    if so_ngay_tuoi < 28:
        return 1.1
    return 1.0


def load_thu_trong_tuan_chuan_hoa() -> np.ndarray:
    with open(DIST_OLIST_PATH, encoding="utf-8") as f:
        dist = json.load(f)
    thu = dist["thu_trong_tuan"]  # key "0".."6", 0 = Thứ Hai
    mang = np.array([thu[str(i)] for i in range(7)])
    return mang * 7


def load_ty_le_view_sang_cart() -> float:
    with open(DIST_FUNNEL_PATH, encoding="utf-8") as f:
        dist = json.load(f)
    return dist["ty_le_view_sang_cart"]


def load_danh_sach_buyer() -> pd.DataFrame:
    df = pd.read_csv(BUYERS_PATH, encoding="utf-8-sig", parse_dates=["created_at"])
    return df.sort_values("created_at").reset_index(drop=True)


def build_buyer_pool_by_date(buyers_df: pd.DataFrame, min_date: Any, max_date: Any) -> dict[Any, np.ndarray]:
    buyer_dates = np.asarray(buyers_df["created_at"].values)
    buyer_ids = np.asarray(buyers_df["buyer_id"].values)

    pool = {}
    curr = pd.Timestamp(min_date).floor("D")
    end = pd.Timestamp(max_date).floor("D")
    while curr <= end:
        day_start = np.datetime64(str(curr)[:10])
        # Chỉ bốc buyer đã đăng ký trước ngày này
        idx = int(np.searchsorted(buyer_dates, day_start, side="left"))
        if idx == 0:
            idx = max(1, int(len(buyer_ids) * 0.05))
        pool[curr] = buyer_ids[:idx]
        curr += timedelta(days=1)
    return pool


def tinh_truoc_he_so_mua_vu(chu_de_list) -> dict:
    cache = {}
    for chu_de in chu_de_list:
        try:
            chuoi = he_so_mua_vu(str(chu_de).strip().lower())
            date_dict = {pd.Timestamp(cast(Any, ts)).floor("D"): float(val) for ts, val in chuoi.items()}
            cache[chu_de] = {
                "series": chuoi,
                "dict": date_dict,
                "min_date": chuoi.index.min(),
                "max_date": chuoi.index.max(),
            }
        except (ValueError, Exception) as e:
            print(f"  !! không có dữ liệu mùa vụ cho chủ đề '{chu_de}', dùng hệ số 1.0 (chi tiết: {e})")
            cache[chu_de] = None
    return cache


def tra_he_so_mua_vu(cache_mua_vu: dict, chu_de: str, ngay: Any) -> float:
    item = cache_mua_vu.get(chu_de)
    if item is None:
        return 1.0
    ngay_floor = pd.Timestamp(ngay).floor("D")
    val = item["dict"].get(ngay_floor)
    if val is not None:
        return float(val)
    chuoi = item["series"]
    idx_gan_nhat = chuoi.index[chuoi.index.get_indexer([ngay_floor], method="nearest")[0]]
    loc_val = chuoi.loc[idx_gan_nhat]
    if hasattr(loc_val, "iloc"):
        return float(loc_val.iloc[0])
    return float(loc_val)


def main():
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    rng = np.random.default_rng(42)

    print(f"Đọc dữ liệu sản phẩm từ {LISTINGS_PATH}...")
    listings = pd.read_csv(LISTINGS_PATH, parse_dates=[COT_CREATED_AT])

    for cot in [COT_LISTING_ID, COT_TIER, COT_TOPIC, COT_CREATED_AT]:
        if cot not in listings.columns:
            raise ValueError(f"Không tìm thấy cột '{cot}' trong file {LISTINGS_PATH}. Vui lòng kiểm tra lại cấu hình tên cột.")

    buyers_df = load_danh_sach_buyer()
    all_buyer_ids = np.asarray(buyers_df["buyer_id"].values)
    buyer_pool_by_date = build_buyer_pool_by_date(buyers_df, listings[COT_CREATED_AT].min(), NGAY_KET_THUC)
    he_so_thu = load_thu_trong_tuan_chuan_hoa()
    ty_le_cart = load_ty_le_view_sang_cart()

    chu_de_list = listings[COT_TOPIC].unique().tolist()
    print(f"Tính trước hệ số mùa vụ cho {len(chu_de_list)} chủ đề: {chu_de_list}")
    cache_mua_vu = tinh_truoc_he_so_mua_vu(chu_de_list)

    rows = []
    event_counter = 0
    tong_san_pham = len(listings)

    print(f"Bắt đầu sinh hành vi xem và thêm giỏ cho {tong_san_pham:,} sản phẩm...")

    for so_thu_tu, listing in enumerate(listings.itertuples(index=False), start=1):
        listing_id = getattr(listing, COT_LISTING_ID)
        tier = getattr(listing, COT_TIER)
        topic = getattr(listing, COT_TOPIC)
        created_at = getattr(listing, COT_CREATED_AT)

        muc_nen = MUC_NEN_THEO_TIER.get(tier, 0.1)
        so_ngay = (NGAY_KET_THUC - created_at).days
        if so_ngay < 1:
            continue

        # Bắt đầu từ ngày hôm sau khi tạo sản phẩm để đảm bảo created_at < occurred_at
        for delta_ngay in range(1, so_ngay + 1):
            ngay = created_at + timedelta(days=delta_ngay)
            ngay_floor = pd.Timestamp(ngay).floor("D")

            hs_mua_vu = tra_he_so_mua_vu(cache_mua_vu, topic, ngay)
            hs_thu = he_so_thu[ngay.weekday()]
            hs_tuoi = he_so_tuoi(delta_ngay)

            ky_vong = muc_nen * hs_mua_vu * hs_thu * hs_tuoi

            so_luot_xem = max(0, int(round(float(rng.normal(ky_vong, ky_vong * 0.4)))))
            if so_luot_xem == 0:
                continue

            eligible_buyers = buyer_pool_by_date.get(ngay_floor)
            candidates: np.ndarray = (
                eligible_buyers if eligible_buyers is not None and len(eligible_buyers) > 0 else all_buyer_ids
            )
            nguoi_mua_view = rng.choice(candidates, size=so_luot_xem)
            gio_view = rng.integers(0, 24, size=so_luot_xem)
            phut_view = rng.integers(0, 60, size=so_luot_xem)
            giay_view = rng.integers(0, 60, size=so_luot_xem)

            co_them_gio = rng.random(so_luot_xem) < ty_le_cart

            for k in range(so_luot_xem):
                event_counter += 1
                occurred_at = datetime(
                    ngay.year,
                    ngay.month,
                    ngay.day,
                    int(gio_view[k]),
                    int(phut_view[k]),
                    int(giay_view[k]),
                )
                rows.append(
                    (
                        f"evt_{event_counter:08d}",
                        nguoi_mua_view[k],
                        listing_id,
                        "view",
                        occurred_at.strftime("%Y-%m-%d %H:%M:%S"),
                    )
                )

                if co_them_gio[k]:
                    event_counter += 1
                    tre_phut = int(rng.integers(1, 30))
                    occurred_at_cart = occurred_at + timedelta(minutes=tre_phut)
                    rows.append(
                        (
                            f"evt_{event_counter:08d}",
                            nguoi_mua_view[k],
                            listing_id,
                            "add_to_cart",
                            occurred_at_cart.strftime("%Y-%m-%d %H:%M:%S"),
                        )
                    )

        if so_thu_tu % 500 == 0 or so_thu_tu == tong_san_pham:
            print(f"  đã xử lý {so_thu_tu}/{tong_san_pham} sản phẩm, {len(rows):,} dòng...")

    print(f"\nGhi {len(rows):,} dòng sự kiện ra {OUT_PATH}...")
    with open(OUT_PATH, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["event_id", "buyer_id", "listing_id", "event_type", "occurred_at"])
        writer.writerows(rows)

    df_result = pd.DataFrame(rows, columns=["event_id", "buyer_id", "listing_id", "event_type", "occurred_at"])
    so_view = int((df_result["event_type"] == "view").sum())
    so_cart = int((df_result["event_type"] == "add_to_cart").sum())

    print(f"\nĐã lưu {OUT_PATH}")
    print(f"Tổng    : {len(df_result):,} dòng")
    print(f"Lượt xem: {so_view:,}")
    print(f"Thêm giỏ: {so_cart:,}  ({so_cart / so_view * 100:.2f}% số lượt xem)")

    print("\nTự kiểm:")
    if 1_000_000 <= so_view <= 1_300_000:
        print(f"  OK  tổng lượt xem {so_view:,} trong khoảng 1,0-1,3 triệu")
    else:
        print(f"  !!  tổng lượt xem {so_view:,} NGOÀI khoảng 1,0-1,3 triệu (xem phân bố tier/độ tuổi)")

    ty_le_thuc_te = so_cart / so_view if so_view > 0 else 0
    if abs(ty_le_thuc_te - ty_le_cart) < 0.02:
        print(f"  OK  tỷ lệ thêm giỏ thực tế {ty_le_thuc_te:.4f} khớp task 3 ({ty_le_cart:.4f})")
    else:
        print(f"  !!  tỷ lệ thêm giỏ thực tế {ty_le_thuc_te:.4f} LỆCH so với task 3 ({ty_le_cart:.4f})")

    ve_bieu_do_kiem_tra(df_result)


def ve_bieu_do_kiem_tra(df_result: pd.DataFrame) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    qc_dir = os.path.dirname(QC_IMG_PATH)
    os.makedirs(qc_dir, exist_ok=True)

    df_view = df_result[df_result["event_type"] == "view"].copy()
    df_view["ngay"] = [str(x)[:10] for x in df_view["occurred_at"]]
    theo_ngay = df_view.groupby("ngay").size()

    plt.style.use("seaborn-v0_8-whitegrid" if "seaborn-v0_8-whitegrid" in plt.style.available else "default")
    fig, ax = plt.subplots(figsize=(15, 6), dpi=130)

    x_vals = list(theo_ngay.index)
    y_vals = np.asarray(theo_ngay.values, dtype=float)
    ax.plot(x_vals, y_vals, color="#1f77b4", linewidth=1.6, label="Lượt xem theo ngày (Views/day)")

    ax.set_title("Biểu Đồ Kiểm Tra: Lượt Xem Theo Ngày (Events Views Timeline)", fontsize=14, fontweight="bold", pad=12)
    ax.set_xlabel("Thời gian (Ngày)", fontsize=11, labelpad=8)
    ax.set_ylabel("Số lượt xem (Views)", fontsize=11, labelpad=8)
    ax.grid(True, linestyle="--", alpha=0.6)

    plt.tight_layout()
    plt.savefig(QC_IMG_PATH, dpi=130)
    plt.close()

    print(f"\nĐã lưu biểu đồ {QC_IMG_PATH}")


if __name__ == "__main__":
    main()
