"""
calendar_vn.py — Xử lý lịch Tết âm lịch và chuyển đổi trục thời gian (Lễ Tết Việt Nam).

Vấn đề:
Tết âm lịch rơi vào các ngày dương lịch khác nhau mỗi năm (lệch tới gần 4 tuần):
  2021: 12/02 | 2022: 01/02 | 2023: 22/01 | 2024: 10/02 | 2025: 29/01 | 2026: 17/02
Nếu gộp chuỗi theo tuần dương lịch trong năm (week of year), đỉnh Tết sẽ bị phân mảnh và biến mất.
Giải pháp:
Đổi trục thời gian theo số ngày cách Tết gần nhất (days_to_tet).
"""

import pandas as pd
import numpy as np
from datetime import datetime, date
from typing import Union, Dict

# Bảng ngày mùng 1 Tết Nguyên Đán (Dương lịch).
# Mở rộng tới 2030: dự báo 12 tuần tính từ cuối 2026 sẽ chạm sang 2027, và bảng
# cũ dừng ở 2026 làm get_tet_date() ném lỗi ngay giữa kỳ dự báo.
TET_DATES: Dict[int, str] = {
    2021: "2021-02-12",
    2022: "2022-02-01",
    2023: "2023-01-22",
    2024: "2024-02-10",
    2025: "2025-01-29",
    2026: "2026-02-17",
    2027: "2027-02-06",
    2028: "2028-01-26",
    2029: "2029-02-13",
    2030: "2030-02-03",
}

# Các ngày lễ cố định dương lịch tại Việt Nam (tháng, ngày)
VN_HOLIDAYS_SOLAR = {
    (1, 1): "Tết Dương Lịch",
    (4, 30): "Giải phóng Miền Nam",
    (5, 1): "Quốc tế Lao Động",
    (9, 2): "Quốc Khánh",
    (10, 20): "Phụ nữ Việt Nam",
    (11, 20): "Nhà giáo Việt Nam",
    (12, 24): "Giáng Sinh",
    (2, 14): "Valentine",
    (3, 8): "Quốc tế Phụ nữ",
}


def get_tet_date(year: int) -> pd.Timestamp:
    """Trả về ngày mùng 1 Tết của một năm nhất định."""
    if year in TET_DATES:
        return pd.Timestamp(TET_DATES[year])
    raise ValueError(f"Chưa có cấu hình ngày Tết cho năm {year} (hỗ trợ 2021–2026).")


def days_to_tet(date_val: Union[str, datetime, date, pd.Timestamp]) -> int:
    """
    Tính số ngày cách Tết Nguyên Đán gần nhất.
    - Giá trị âm (-k): k ngày TRƯỚC Tết.
    - Giá trị 0: Đúng mùng 1 Tết.
    - Giá trị dương (+k): k ngày SAU Tết.
    """
    ts = pd.to_datetime(date_val)
    year = ts.year

    # Tìm ngày Tết gần nhất (so sánh Tết năm trước, năm nay và năm sau)
    candidate_years = [y for y in [year - 1, year, year + 1] if y in TET_DATES]
    if not candidate_years:
        raise ValueError(f"Không tìm thấy năm Tết phù hợp cho ngày {date_val}")

    diffs = [(ts - pd.Timestamp(TET_DATES[y])).days for y in candidate_years]
    # Chọn ngày có khoảng cách tuyệt đối nhỏ nhất
    min_diff = min(diffs, key=abs)
    return int(min_diff)


def is_vn_holiday(date_val: Union[str, datetime, date, pd.Timestamp]) -> bool:
    """Kiểm tra một ngày có phải ngày lễ hoặc cận Tết (trong vòng +- 7 ngày Tết) hay không."""
    ts = pd.to_datetime(date_val)
    if (ts.month, ts.day) in VN_HOLIDAYS_SOLAR:
        return True
    if abs(days_to_tet(ts)) <= 7:
        return True
    return False


def get_tet_aligned_series(series: pd.Series) -> pd.DataFrame:
    """
    Chuyển chuỗi thời gian nhiều năm sang trục ngày cách Tết (-60 đến +30 ngày).
    Trả về DataFrame gồm: observed_on, value, year, days_to_tet.
    """
    df = series.reset_index()
    df.columns = ["observed_on", "value"]
    df["observed_on"] = pd.to_datetime(df["observed_on"])
    df["year"] = df["observed_on"].dt.year
    df["days_to_tet"] = df["observed_on"].apply(days_to_tet)
    return df


if __name__ == "__main__":
    print("=== TỰ KIỂM TRA MODULE CALENDAR_VN.PY ===")
    
    # 1. Kiểm tra tính đúng ngày cách Tết
    assert days_to_tet("2023-01-20") == -2, "20/01/2023 phải là -2 ngày trước Tết 2023 (22/01)"
    assert days_to_tet("2026-02-15") == -2, "15/02/2026 phải là -2 ngày trước Tết 2026 (17/02)"
    assert days_to_tet("2024-02-10") == 0, "10/02/2024 phải là đúng mùng 1 Tết 2024"
    assert days_to_tet("2024-02-15") == 5, "15/02/2024 phải là +5 ngày sau Tết 2024"
    print("✓ Kiểm tra days_to_tet: Chính xác 100% trên các mốc thực tế.")

    # 2. Thử nghiệm đổi trục mô phỏng dữ liệu 5 năm
    sample_dates = pd.date_range("2021-01-01", "2026-03-01", freq="W-SUN")
    # Giả lập tín hiệu đỉnh vào đúng 2 tuần trước Tết
    values = []
    for d in sample_dates:
        dtet = days_to_tet(d)
        val = 100.0 * np.exp(-0.5 * ((dtet - (-14)) / 7) ** 2) + 10.0
        values.append(val)
    
    s = pd.Series(values, index=sample_dates)
    aligned = get_tet_aligned_series(s)
    
    # Đỉnh khi gom theo ngày cách Tết phải nằm trong khoảng [-21, -7]
    peak_dtet = aligned.groupby("days_to_tet")["value"].mean().idxmax()
    print(f"✓ Đỉnh mùa vụ sau khi đổi trục: ngày {peak_dtet} (trước Tết ~2 tuần)")
    assert -21 <= peak_dtet <= -7, f"Đỉnh mùa vụ sai lệch: {peak_dtet}"

    print("✅ TẤT CẢ SELF-CHECKS CỦA CALENDAR_VN.PY ĐÃ PASS!")
