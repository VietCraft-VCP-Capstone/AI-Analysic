
import os
import sys
import json
import numpy as np
import pandas as pd
from datetime import datetime, timezone
from typing import Dict, Any

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.dirname(BASE_DIR)
ROOT_DIR = os.path.dirname(APP_DIR)
sys.path.insert(0, ROOT_DIR)

from app.core.loader import get_trend_series, get_active_keywords, _get_mongo_coll
from app.config import settings


def calc_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> Dict[str, float]:
    mask = ~np.isnan(y_true) & ~np.isnan(y_pred)
    yt, yp = y_true[mask], y_pred[mask]
    if len(yt) == 0:
        return {"mae": 0.0, "rmse": 0.0, "mape": 0.0}
    mae = float(np.mean(np.abs(yt - yp)))
    rmse = float(np.sqrt(np.mean((yt - yp) ** 2)))
    # Tránh chia cho 0 với MAPE
    non_zero = yt != 0
    mape = float(np.mean(np.abs((yt[non_zero] - yp[non_zero]) / yt[non_zero])) * 100) if np.any(non_zero) else 0.0
    return {"mae": round(mae, 4), "rmse": round(rmse, 4), "mape": round(mape, 4)}


def compute_all_baselines() -> Dict[str, Any]:
    keywords = get_active_keywords()
    coll = _get_mongo_coll(settings.MONGO_DB_DATA, "trend_interest")
    
    output = {
        "metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total_keywords": len(keywords),
            "weekly_test_horizon_weeks": 12,
            "daily_test_horizon_days": 30,
            "description": "Naive benchmark baselines for Google Trends time series forecasting."
        },
        "keywords": {}
    }

    print(f"=== Đang tính Baselines cho {len(keywords)} từ khoá chuẩn ===")

    for kw in keywords:
        kw_data = {}
        
        # 1. Tính cho chuỗi Weekly (5 năm, test 12 tuần cuối)
        try:
            # Lấy dữ liệu từ Mongo hoặc fallback
            if coll is not None:
                cursor = coll.find(
                    {"keyword": kw, "granularity": "weekly", "is_anchor": False},
                    {"_id": 0, "observed_on": 1, "scaled": 1}
                ).sort("observed_on", 1)
                df_w = pd.DataFrame(list(cursor))
            else:
                df_w = pd.DataFrame()

            if not df_w.empty:
                df_w["observed_on"] = pd.to_datetime(df_w["observed_on"])
                df_w = df_w.set_index("observed_on").sort_index()
                s_w = df_w["scaled"].astype(float).asfreq("W-SUN")
            else:
                # Mock fallback dựa trên sóng tuần chuẩn
                dates = pd.date_range("2021-08-15", "2026-08-16", freq="W-SUN")
                np.random.seed(abs(hash(kw)) % (2**32))
                base = 20.0 + 10.0 * np.sin(np.linspace(0, 10 * np.pi, len(dates))) + np.random.normal(0, 3, len(dates))
                s_w = pd.Series(np.maximum(1.0, base), index=dates)

            # Split: 12 tuần cuối làm test set
            test_w = s_w.iloc[-12:]
            train_w = s_w.iloc[:-12]
            cutoff_date_w = str(train_w.index[-1].date())

            # Naive 1: Lag 1 (lấy giá trị tuần trước liền kề)
            naive1_pred_w = s_w.shift(1).loc[test_w.index].values
            # Naive 2: Lag 52 (lấy giá trị cùng kỳ 52 tuần trước)
            naive2_pred_w = s_w.shift(52).loc[test_w.index].values

            metrics_n1_w = calc_metrics(test_w.values, naive1_pred_w)
            metrics_n2_w = calc_metrics(test_w.values, naive2_pred_w)

            kw_data["weekly"] = {
                "test_cutoff_date": cutoff_date_w,
                "test_points": len(test_w),
                "naive_last_week": metrics_n1_w,
                "naive_same_period_last_year": metrics_n2_w
            }
        except Exception as e:
            kw_data["weekly"] = {"error": str(e)}

        # 2. Tính cho chuỗi Daily (90 ngày, test 30 ngày cuối)
        try:
            if coll is not None:
                cursor = coll.find(
                    {"keyword": kw, "granularity": "daily", "is_anchor": False},
                    {"_id": 0, "observed_on": 1, "scaled": 1}
                ).sort("observed_on", 1)
                df_d = pd.DataFrame(list(cursor))
            else:
                df_d = pd.DataFrame()

            if not df_d.empty:
                df_d["observed_on"] = pd.to_datetime(df_d["observed_on"])
                df_d = df_d.set_index("observed_on").sort_index()
                s_d = df_d["scaled"].astype(float).asfreq("D")
            else:
                dates_d = pd.date_range("2026-05-18", "2026-08-18", freq="D")
                np.random.seed(abs(hash(kw)) % (2**32))
                base_d = 25.0 + np.random.normal(0, 4, len(dates_d))
                s_d = pd.Series(np.maximum(1.0, base_d), index=dates_d)

            test_d = s_d.iloc[-30:]
            train_d = s_d.iloc[:-30]
            cutoff_date_d = str(train_d.index[-1].date())

            naive1_pred_d = s_d.shift(1).loc[test_d.index].values
            naive7_pred_d = s_d.shift(7).loc[test_d.index].values

            metrics_n1_d = calc_metrics(test_d.values, naive1_pred_d)
            metrics_n7_d = calc_metrics(test_d.values, naive7_pred_d)

            kw_data["daily"] = {
                "test_cutoff_date": cutoff_date_d,
                "test_points": len(test_d),
                "naive_yesterday": metrics_n1_d,
                "naive_same_day_last_week": metrics_n7_d
            }
        except Exception as e:
            kw_data["daily"] = {"error": str(e)}

        output["keywords"][kw] = kw_data

    return output


def main():
    baselines = compute_all_baselines()
    data_dir = os.path.join(APP_DIR, "data")
    os.makedirs(data_dir, exist_ok=True)
    out_path = os.path.join(data_dir, "baselines.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(baselines, f, ensure_ascii=False, indent=2)
    print(f"✓ Đã lưu bảng baselines thành công vào: {out_path}")
    print("✅ Hoàn thành Task 23 / Task 7!")



if __name__ == "__main__":
    main()
