"""
Task 5 - Lấy hệ số mùa vụ từ dữ liệu Google Trends
Kết quả: hàm he_so_mua_vu(chu_de) -> pandas.Series, index là ngày,
value là hệ số mùa vụ (trung bình = 1.0).

QUAN TRỌNG: task này có tự-kiểm bắt buộc ở cuối file. Nếu 4 điều tự-kiểm
không đúng thì DỪNG LẠI, đừng sang Task 6 - dữ liệu sinh ra sau đó sẽ
vô nghĩa nếu hệ số mùa vụ sai.
"""

import os
from typing import cast

import pandas as pd
from pymongo import MongoClient

# Sửa biến môi trường MONGO_URI nếu connection string khác, hoặc export
# MONGO_URI=mongodb+srv://... trước khi chạy.
MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
DB_NAME = os.environ.get("MONGO_DB", "vietcraft")
COLLECTION = "trend_interest"


def _get_collection():
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000)
    return client[DB_NAME][COLLECTION]


def he_so_mua_vu(chu_de: str, collection=None) -> pd.Series:
    """
    Nhận vào tên chủ đề (vd. "tet"), trả về Series mỗi ngày một hệ số
    mùa vụ, trung bình toàn chuỗi luôn bằng 1.0.
    """
    coll = collection if collection is not None else _get_collection()

    # Bước 1 - lọc đúng 3 điều kiện, chỉ lấy 2 cột cần dùng
    cursor = coll.find(
        {"topic": chu_de, "granularity": "weekly", "is_anchor": False},
        {"_id": 0, "observed_on": 1, "scaled": 1},
    )
    df = pd.DataFrame(list(cursor))

    if df.empty:
        raise ValueError(
            f"Không có dữ liệu cho chủ đề '{chu_de}'. "
            "Kiểm tra lại tên chủ đề có đúng như trong MongoDB không."
        )

    df["observed_on"] = pd.to_datetime(df["observed_on"])

    # Bước 2 - gộp nhiều từ khoá thành một chuỗi, trung bình theo ngày quan sát
    theo_tuan = df.groupby("observed_on")["scaled"].mean().sort_index()

    # Bước 3 - đổi từ tuần sang ngày, nội suy tuyến tính
    theo_ngay = theo_tuan.resample("D").interpolate()

    # Bước 4 - kéo trung bình về 1
    he_so = theo_ngay / theo_ngay.mean()

    return he_so


def liet_ke_chu_de(collection=None) -> list[str]:
    coll = collection if collection is not None else _get_collection()
    return sorted(
        coll.distinct("topic", {"granularity": "weekly", "is_anchor": False})
    )


def main():
    coll = _get_collection()
    chu_de_list = liet_ke_chu_de(coll)

    if not chu_de_list:
        print("Không tìm thấy chủ đề nào trong bảng trend_interest.")
        return

    # Bước 5 - chạy thử trên mọi chủ đề
    print(f"{'chủ đề':<16}{'cao nhất':>10}  {'ngày cao nhất':<15}{'thấp nhất':>10}")
    print("-" * 57)

    ket_qua = {}
    for chu_de in chu_de_list:
        he_so = he_so_mua_vu(chu_de, coll)
        ket_qua[chu_de] = he_so
        cao_nhat = he_so.max()
        ngay_cao_nhat = cast(pd.Timestamp, he_so.idxmax()).date()
        thap_nhat = he_so.min()
        print(f"{chu_de:<16}{cao_nhat:>10.1f}  {str(ngay_cao_nhat):<15}{thap_nhat:>10.2f}")

    # Tự kiểm - dừng lại nếu sai
    print("\nTự kiểm:")
    loi = []

    if "tet" in ket_qua:
        cao_nhat = ket_qua["tet"].max()
        ngay = cast(pd.Timestamp, ket_qua["tet"].idxmax())
        if cao_nhat < 5:
            loi.append(f"tet: hệ số cao nhất chỉ {cao_nhat:.1f}, cần ít nhất gấp 5 lần")
        if ngay.month not in (1, 2):
            loi.append(f"tet: ngày cao nhất rơi vào tháng {ngay.month}, cần tháng 1 hoặc 2")
    else:
        loi.append("Không có chủ đề 'tet' trong dữ liệu")

    if "womens_day" in ket_qua:
        ngay = cast(pd.Timestamp, ket_qua["womens_day"].idxmax())
        if not (ngay.month == 3 and ngay.day <= 15):
            loi.append(
                f"womens_day: ngày cao nhất là {ngay.date()}, cần rơi vào đầu tháng 3"
            )
    else:
        loi.append("Không có chủ đề 'womens_day' trong dữ liệu")

    if "evergreen" in ket_qua:
        # Docx không cho ngưỡng số cụ thể cho evergreen, chỉ nói "gần 1,0".
        # Kiểm tương đối: evergreen phải phẳng hơn hẳn các chủ đề mùa vụ khác -
        # tức biên độ dao động của nó nhỏ hơn trung vị biên độ các chủ đề khác.
        bien_do_evergreen = ket_qua["evergreen"].max() - ket_qua["evergreen"].min()
        bien_do_khac = [
            ket_qua[cd].max() - ket_qua[cd].min()
            for cd in ket_qua
            if cd != "evergreen"
        ]
        trung_vi_khac = sorted(bien_do_khac)[len(bien_do_khac) // 2] if bien_do_khac else 0

        print(
            f"  (tham khảo) biên độ evergreen = {bien_do_evergreen:.2f}, "
            f"trung vị các chủ đề khác = {trung_vi_khac:.2f}"
        )
        if trung_vi_khac and bien_do_evergreen > trung_vi_khac:
            loi.append(
                f"evergreen: biên độ dao động {bien_do_evergreen:.2f} lớn hơn cả "
                f"trung vị các chủ đề mùa vụ khác ({trung_vi_khac:.2f}) - "
                "không hợp lý, hàng phổ thông phải phẳng nhất"
            )
    else:
        loi.append("Không có chủ đề 'evergreen' trong dữ liệu")

    if loi:
        print("!! CÓ VẤN ĐỀ - DỪNG LẠI, ĐỪNG SANG TASK 6:")
        for l in loi:
            print(f"  - {l}")
    else:
        print("Cả 4 điều tự-kiểm đều ổn. Có thể sang Task 6.")


if __name__ == "__main__":
    main()
