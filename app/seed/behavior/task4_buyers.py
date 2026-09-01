"""
Task 4 - Sinh 6.000 người mua
Cần trước: data/seed_out/v1/provinces.csv (do Hạt giao)
Kết quả: data/seed_out/v1/buyers.csv có 6.000 dòng
"""

import csv
import os
import random
from datetime import datetime, timedelta

PROVINCES_PATH = "data/seed_out/v1/provinces.csv"
OUT_PATH = "data/seed_out/v1/buyers.csv"

SO_LUONG_BUYER = 6000

# Nếu file provinces.csv của Hạt dùng tên cột khác, sửa dòng này
COT_MA_TINH = "province_code"

# Bước 2 - danh sách tên Việt để ghép ngẫu nhiên (mỗi danh sách 10-20 mục)
HO = [
    "Nguyễn", "Trần", "Lê", "Phạm", "Hoàng", "Huỳnh", "Phan", "Vũ",
    "Võ", "Đặng", "Bùi", "Đỗ", "Hồ", "Ngô", "Dương", "Lý",
]
TEN_DEM = [
    "Văn", "Thị", "Hữu", "Đức", "Minh", "Ngọc", "Thanh", "Xuân",
    "Anh", "Quang", "Thành", "Kim",
]
TEN = [
    "Anh", "Bình", "Chi", "Dũng", "Giang", "Hà", "Hải", "Hương",
    "Khánh", "Linh", "Long", "Mai", "Nam", "Nga", "Phương", "Quân",
    "Thảo", "Trang", "Tuấn", "Vy",
]

TY_LE_DEVICE = {"mobile": 70, "desktop": 25, "tablet": 5}
TY_LE_SEGMENT = {"one_time": 60, "seasonal": 30, "frequent": 10}


def doc_ma_tinh() -> list[str]:
    # Bước 3 - đọc danh sách mã tỉnh từ file của Hạt
    with open(PROVINCES_PATH, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        ma_tinh = [row[COT_MA_TINH] for row in reader]
    if not ma_tinh:
        raise ValueError(f"Không đọc được mã tỉnh nào từ {PROVINCES_PATH}")
    return ma_tinh


def sinh_ngay_dang_ky() -> str:
    # created_at - ngẫu nhiên trong 12 tháng qua (tính từ lúc chạy script)
    bay_gio = datetime.now()
    so_ngay_lui = random.randint(0, 365)
    so_giay_trong_ngay = random.randint(0, 86399)
    ngay = bay_gio - timedelta(days=so_ngay_lui, seconds=-so_giay_trong_ngay)
    return ngay.strftime("%Y-%m-%d %H:%M:%S")


def main():
    # Bước 1 - cố định hạt giống ngẫu nhiên
    random.seed(42)

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    ma_tinh_list = doc_ma_tinh()

    rows = []
    for i in range(1, SO_LUONG_BUYER + 1):
        buyer_id = f"byr_{i:06d}"
        display_name = f"{random.choice(HO)} {random.choice(TEN_DEM)} {random.choice(TEN)}"
        email = f"buyer{i}@example.com"
        province_code = random.choice(ma_tinh_list)
        device_type = random.choices(
            list(TY_LE_DEVICE.keys()), weights=list(TY_LE_DEVICE.values())
        )[0]
        segment = random.choices(
            list(TY_LE_SEGMENT.keys()), weights=list(TY_LE_SEGMENT.values())
        )[0]
        created_at = sinh_ngay_dang_ky()

        rows.append(
            {
                "buyer_id": buyer_id,
                "display_name": display_name,
                "email": email,
                "province_code": province_code,
                "device_type": device_type,
                "segment": segment,
                "created_at": created_at,
            }
        )

    # Bước 5 - ghi ra CSV, mã hoá utf-8-sig để Excel không lỗi dấu tiếng Việt
    with open(OUT_PATH, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print(f"Đã sinh {len(rows)} người mua\n")

    # Bước 6 - in thống kê để tự kiểm
    print("Chia theo kiểu mua:")
    for seg, ty_le in TY_LE_SEGMENT.items():
        n = sum(1 for r in rows if r["segment"] == seg)
        print(f"  {seg:<12} {n:>5}  ({n / len(rows) * 100:.0f}%)")

    print("Chia theo thiết bị:")
    for dev, ty_le in TY_LE_DEVICE.items():
        n = sum(1 for r in rows if r["device_type"] == dev)
        print(f"  {dev:<12} {n:>5}  ({n / len(rows) * 100:.0f}%)")


if __name__ == "__main__":
    main()
