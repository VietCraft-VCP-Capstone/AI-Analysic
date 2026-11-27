"""Backtest (chỉ đọc): so tet_aware_forecast với seasonal_naive (lùi 52 tuần) trên chuỗi Trends tuần thật quanh Tết.

Điểm cắt đặt 8 tuần trước mỗi Tết, dự báo 12 tuần (phủ đỉnh Tết). Thước đo: MAE theo tuần và
MASE (chia cho MAE của seasonal_naive trên cùng điểm cắt): < 1 là thắng.

Kết quả 27/11/2026 (135 điểm cắt, Tết 2024–2026): MAE TB naive 16,25 / tet_aware 10,7;
MASE trung vị 0,939; thắng 49% điểm cắt (Tết 2026 hòa). Chưa đủ để thay phương pháp chính.
"""
import sys
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))  # chạy: python -m app.core.seasonal_dl.backtest_tet
from app.core.calendar_vn import get_tet_date  # noqa: E402
from app.core.listing_intel.trend_store import weekly_series  # noqa: E402
from app.models.seasonal_forecast import seasonal_naive, tet_aware_forecast  # noqa: E402

ALL = weekly_series()
KEYWORDS = list(ALL)
H, LEAD_WEEKS = 12, 8

rows = []
for kw in KEYWORDS:
    s = ALL[kw].sort_index()
    if s.empty:
        continue
    dates, vals = list(s.index), s.values
    for year in range(2021, 2027):
        tet = get_tet_date(year)
        cut_date = tet - timedelta(weeks=LEAD_WEEKS)
        cut = int(np.searchsorted(np.array(dates), cut_date))
        if cut < 104 or cut + H > len(vals):
            continue
        tr_d, tr_v = dates[:cut], vals[:cut]
        te_d, te_v = dates[cut:cut + H], vals[cut:cut + H]
        naive = np.array(seasonal_naive(tr_v, H, 52))
        aware = np.array(tet_aware_forecast(tr_d, tr_v, te_d)["predictions"])
        mae_n, mae_a = float(np.mean(np.abs(te_v - naive))), float(np.mean(np.abs(te_v - aware)))
        rows.append({"kw": kw, "tet": tet.date().isoformat(), "mae_naive": mae_n, "mae_aware": mae_a,
                     "mase": mae_a / mae_n if mae_n > 0 else np.nan})

if not rows:
    print("Không có điểm cắt nào đủ dữ liệu (cần ≥104 tuần trước điểm cắt).")
    sys.exit(0)
df = pd.DataFrame(rows)
pd.set_option("display.width", 160)
print(df.groupby("tet")[["mae_naive", "mae_aware", "mase"]].median().round(3).to_string())
print("\nSố điểm cắt:", len(df), "| MASE trung vị:", round(float(df["mase"].median()), 3),
      "| tỷ lệ thắng (MASE<1):", f"{(df['mase'] < 1).mean():.0%}",
      "| MAE TB naive / aware:", round(df["mae_naive"].mean(), 2), "/", round(df["mae_aware"].mean(), 2))
