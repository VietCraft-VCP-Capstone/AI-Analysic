"""
Task 3 - Tính tỷ lệ phễu
Kết quả: data/seed_out/v1/dist_funnel.json chứa 2 tỷ lệ + tích của chúng
+ tên bộ dữ liệu kèm link nguồn.
"""

import json
import os

import pandas as pd

EVENTS_PATH = "data/external/funnel/events.csv"
OUT_PATH = "data/seed_out/v1/dist_funnel.json"

# Tên cột hành vi trong file events.csv - Retailrocket dùng cột "event"
# với 3 giá trị: view / addtocart / transaction.
# Nếu dùng bộ dữ liệu khác, chỉ cần sửa 4 dòng dưới đây.
COT_HANH_VI = "event"
GIA_TRI_VIEW = "view"
GIA_TRI_CART = "addtocart"
GIA_TRI_MUA = "transaction"

TEN_BO_DU_LIEU = "Retailrocket recommender system dataset"
LINK_NGUON = "https://www.kaggle.com/datasets/retailrocket/ecommerce-dataset"


def main():
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)

    df = pd.read_csv(EVENTS_PATH)

    # Bước 1 - xem file có những loại hành vi nào, đừng đoán, nhìn tận mắt
    print("Các giá trị trong cột hành vi:")
    print(df[COT_HANH_VI].value_counts())
    print()

    # Bước 2 - đếm 3 con số
    so_view = int((df[COT_HANH_VI] == GIA_TRI_VIEW).sum())
    so_cart = int((df[COT_HANH_VI] == GIA_TRI_CART).sum())
    so_mua = int((df[COT_HANH_VI] == GIA_TRI_MUA).sum())

    if so_view == 0 or so_cart == 0:
        raise ValueError(
            "Không đếm được lượt xem hoặc thêm giỏ nào - kiểm tra lại "
            "tên cột/giá trị ở Bước 1, có thể bộ dữ liệu đặt tên khác."
        )

    # Bước 3 - chia ra 2 tỷ lệ
    ty_le_view_sang_cart = so_cart / so_view
    ty_le_cart_sang_mua = so_mua / so_cart

    # Bước 4 - lưu vào json: 2 tỷ lệ, tích của chúng, tên + link nguồn
    result = {
        "ty_le_view_sang_cart": round(ty_le_view_sang_cart, 6),
        "ty_le_cart_sang_mua": round(ty_le_cart_sang_mua, 6),
        "ty_le_view_sang_mua": round(ty_le_view_sang_cart * ty_le_cart_sang_mua, 6),
        "nguon_du_lieu": TEN_BO_DU_LIEU,
        "link_nguon": LINK_NGUON,
    }

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"Đã lưu {OUT_PATH}\n")

    # Kết quả đúng trông như thế nào - in theo đúng format mẫu trong hướng dẫn
    print(f"100 lượt xem  -> {ty_le_view_sang_cart * 100:.1f} lượt thêm giỏ")
    print(f"100 thêm giỏ  -> {ty_le_cart_sang_mua * 100:.1f} đơn")
    print(f"100 lượt xem  -> {result['ty_le_view_sang_mua'] * 100:.2f} đơn")
    print()

    # Tự kiểm - báo động nếu ra ngoài khoảng hợp lý
    canh_bao = []
    if not (0.02 <= ty_le_view_sang_cart <= 0.15):
        canh_bao.append(
            f"  !! tỷ lệ xem->thêm giỏ = {ty_le_view_sang_cart:.3f}, "
            "ngoài khoảng 3%-15% kỳ vọng"
        )
    if not (0.15 <= ty_le_cart_sang_mua <= 0.45):
        canh_bao.append(
            f"  !! tỷ lệ thêm giỏ->mua = {ty_le_cart_sang_mua:.3f}, "
            "ngoài khoảng 15%-45% kỳ vọng"
        )
    if not (0.005 <= result["ty_le_view_sang_mua"] <= 0.05):
        canh_bao.append(
            f"  !! tỷ lệ xem->mua = {result['ty_le_view_sang_mua']:.4f}, "
            "ngoài khoảng 0.5%-5% kỳ vọng"
        )

    if canh_bao:
        print("Tự kiểm: RA NGOÀI KHOẢNG HỢP LÝ, xem lại Bước 1")
        for c in canh_bao:
            print(c)
    else:
        print("Tự kiểm: cả 3 tỷ lệ đều trong khoảng hợp lý.")


if __name__ == "__main__":
    main()
