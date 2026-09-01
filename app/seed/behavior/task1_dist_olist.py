""""
Task 1 - Lấy 4 phân bố từ dữ liệu Olist
Kết quả: data/seed_out/v1/dist_olist.json chứa 4 bảng tỷ lệ:
  gio_trong_ngay, thu_trong_tuan, diem_sao, do_tre_danh_gia
"""

import json
import os

import pandas as pd

ORDERS_PATH = "data/external/olist/olist_orders_dataset.csv"
REVIEWS_PATH = "data/external/olist/olist_order_reviews_dataset.csv"
OUT_PATH = "data/seed_out/v1/dist_olist.json"


def load_data():
    # Bước 3 - đọc cột thời gian thành kiểu ngày giờ, không phải chuỗi
    orders = pd.read_csv(
        ORDERS_PATH,
        parse_dates=["order_purchase_timestamp", "order_delivered_customer_date"],
    )
    reviews = pd.read_csv(REVIEWS_PATH, parse_dates=["review_answer_timestamp"])
    return orders, reviews


def dist_gio_trong_ngay(orders: pd.DataFrame) -> dict:
    # Bước 4 - phân bố giờ trong ngày (0-23), cộng lại = 1
    s = orders["order_purchase_timestamp"].dt.hour.value_counts(normalize=True)
    return {str(k): round(v, 6) for k, v in s.sort_index().items()}


def dist_thu_trong_tuan(orders: pd.DataFrame) -> dict:
    # Bước 5 - phân bố thứ trong tuần (0 = Thứ Hai ... 6 = Chủ nhật)
    s = orders["order_purchase_timestamp"].dt.dayofweek.value_counts(normalize=True)
    return {str(k): round(v, 6) for k, v in s.sort_index().items()}


def dist_diem_sao(reviews: pd.DataFrame) -> dict:
    # Bước 6 - phân bố điểm sao (1-5)
    s = reviews["review_score"].value_counts(normalize=True)
    return {str(k): round(v, 6) for k, v in s.sort_index().items()}


def dist_do_tre_danh_gia(orders: pd.DataFrame, reviews: pd.DataFrame) -> dict:
    # Bước 7 - độ trễ đánh giá = ngày viết đánh giá - ngày giao hàng
    merged = reviews.merge(
        orders[["order_id", "order_delivered_customer_date"]],
        on="order_id",
        how="left",
    )
    merged = merged.dropna(subset=["order_delivered_customer_date"])

    delay_days = (
        merged["review_answer_timestamp"] - merged["order_delivered_customer_date"]
    ).dt.days

    # bỏ giá trị âm và > 60 ngày (dữ liệu lỗi)
    delay_days = delay_days[(delay_days >= 0) & (delay_days <= 60)]

    s = delay_days.value_counts(normalize=True)
    return {str(k): round(v, 6) for k, v in s.sort_index().items()}


def tu_kiem(ten: str, bang: dict, so_muc_ky_vong: int) -> None:
    tong = sum(bang.values())
    print(f"{ten:<20} {len(bang):>3} mục, tổng tỷ lệ = {tong:.3f}")
    if len(bang) != so_muc_ky_vong:
        print(f"  !! cảnh báo: kỳ vọng {so_muc_ky_vong} mục, thực tế {len(bang)} mục")


def main():
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)

    orders, reviews = load_data()

    result = {
        "gio_trong_ngay": dist_gio_trong_ngay(orders),
        "thu_trong_tuan": dist_thu_trong_tuan(orders),
        "diem_sao": dist_diem_sao(reviews),
        "do_tre_danh_gia": dist_do_tre_danh_gia(orders, reviews),
    }

    # Bước 8 - lưu vào json
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"Đã lưu {OUT_PATH}\n")

    # Tự kiểm - in số mục và tổng tỷ lệ
    tu_kiem("gio_trong_ngay", result["gio_trong_ngay"], 24)
    tu_kiem("thu_trong_tuan", result["thu_trong_tuan"], 7)
    tu_kiem("diem_sao", result["diem_sao"], 5)
    tu_kiem("do_tre_danh_gia", result["do_tre_danh_gia"], 61)


if __name__ == "__main__":
    main()
