import json
import os
import sys
import numpy as np
import pandas as pd
from pymongo import MongoClient

if hasattr(sys.stdout, "reconfigure"):
    getattr(sys.stdout, "reconfigure")(encoding="utf-8")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
AI_ANALYSIC_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "..", ".."))
if AI_ANALYSIC_DIR not in sys.path:
    sys.path.insert(0, AI_ANALYSIC_DIR)

from app.config import settings

def main():
    print("=== TÍNH TOÁN TƯƠNG QUAN PEARSON GIỮA DOANH THU & GOOGLE TRENDS ===")
    client = MongoClient(settings.MONGO_URI, serverSelectionTimeoutMS=5000)
    db_seed = client[settings.MONGO_DB_SEED]
    db_data = client[settings.MONGO_DB_DATA]

    # 1. Gộp toàn bộ đơn trong vietcraft-seed thành chuỗi doanh thu theo ngày
    orders_cursor = db_seed["orders"].find(
        {},
        {"ordered_at": 1, "total_vnd": 1, "shipping_fee_vnd": 1, "_id": 0}
    )
    df_orders = pd.DataFrame(list(orders_cursor))
    df_orders["date"] = pd.to_datetime(df_orders["ordered_at"]).dt.date
    df_orders["revenue"] = df_orders["total_vnd"] - df_orders["shipping_fee_vnd"]
    daily_revenue = df_orders.groupby("date")["revenue"].sum().sort_index()

    idx = pd.date_range(daily_revenue.index.min(), daily_revenue.index.max(), freq="D").date
    daily_revenue = daily_revenue.reindex(idx, fill_value=0.0)

    print(f"\n1. Chuỗi Doanh Thu Daily (vietcraft-seed.orders):")
    print(f"   - Số ngày: {len(daily_revenue)} ngày ({daily_revenue.index[0]} -> {daily_revenue.index[-1]})")
    print(f"   - Tổng doanh thu: {daily_revenue.sum():,.0f} VND")
    print(f"   - Trung bình ngày: {daily_revenue.mean():,.0f} VND/ngày")

    # 2. Gộp đúng 40 keyword Trends chuẩn (app/data/seed_keywords.do-not-remove.json)
    seed_kw_path = os.path.join(AI_ANALYSIC_DIR, "app", "data", "seed_keywords.do-not-remove.json")
    with open(seed_kw_path, "r", encoding="utf-8") as f:
        seed_kws = [item["keyword"] for item in json.load(f)]

    trends_cursor = db_data["trend_interest"].find(
        {"granularity": "weekly", "is_anchor": False, "keyword": {"$in": seed_kws}},
        {"observed_on": 1, "scaled": 1, "keyword": 1, "_id": 0}
    )
    df_trends = pd.DataFrame(list(trends_cursor))
    n_kw = df_trends["keyword"].nunique()
    print(f"\n2. Chuỗi Google Trends Tổng Hợp ({n_kw}/40 từ khoá chuẩn):")
    print(f"   - Số bản ghi: {len(df_trends):,} điểm")

    df_trends["observed_on"] = pd.to_datetime(df_trends["observed_on"])
    trends_weekly_avg = df_trends.groupby("observed_on")["scaled"].mean().sort_index()
    trends_daily = trends_weekly_avg.resample("D").interpolate()
    trends_daily.index = trends_daily.index.date
    s_trends = trends_daily.reindex(daily_revenue.index).interpolate()

    correlations = []
    for lag in range(-30, 31):
        shifted_trends = s_trends.shift(lag)
        valid = pd.DataFrame({"revenue": daily_revenue, "trends": shifted_trends}).dropna()
        r = float(valid["revenue"].corr(valid["trends"]))
        correlations.append({"lag_days": lag, "pearson_r": r})

    df_corr = pd.DataFrame(correlations)
    best_row = df_corr.loc[df_corr["pearson_r"].idxmax()]
    best_lag = int(best_row["lag_days"])
    best_r = float(best_row["pearson_r"])

    print(f"\n3. Kết quả tương quan Pearson (40 từ khoá chuẩn):")
    print(f"   - Độ trễ tối ưu (Best Lag): {best_lag} ngày")
    print(f"   - Hệ số tương quan Pearson đỉnh cao nhất: r = {best_r:.4f}")

    print("\n   Bảng đối chiếu hệ số tương quan theo các mốc độ trễ:")
    print(f"   {'Độ trễ (Lag)':<15}{'Pearson r':<15}{'Đánh giá (Chuẩn >= 0.60)':<25}")
    print("   " + "-" * 55)

    check_lags = [-7, -3, -1, 0, 1, 2, 3, 5, 7, 10, 14, best_lag]
    seen = set()
    for l in sorted(check_lags):
        if l in seen:
            continue
        seen.add(l)
        r_val = float(df_corr[df_corr["lag_days"] == l]["pearson_r"].values[0])
        status = "ĐẠT (>= 0.60)" if r_val >= 0.60 else "CHƯA ĐẠT"
        note = " <-- (Độ trễ tối ưu)" if l == best_lag else ""
        print(f"   Lag {l:+2d} ngày      r = {r_val:.4f}      {status}{note}")

    print("\n" + "=" * 55)
    if best_r >= 0.60:
        print(f" KẾT LUẬN: ĐẠT TIÊU CHUẨN NGHIỆM THU (r = {best_r:.4f} >= 0.60)")
    else:
        print(f" KẾT LUẬN: CHƯA ĐẠT (r = {best_r:.4f} < 0.60)")
    print("=" * 55)

if __name__ == "__main__":
    main()
