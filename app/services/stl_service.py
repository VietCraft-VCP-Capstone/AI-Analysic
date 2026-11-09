import pandas as pd
import numpy as np
from statsmodels.tsa.seasonal import STL
from typing import Dict, List, Union


class STLService:
    @staticmethod
    def decompose(data: List[float], period: int = 7, robust: bool = True) -> Dict[str, List[float]]:
        """
        Phân rã chuỗi thời gian thành 3 thành phần: Trend (Xu hướng), Seasonal (Mùa vụ), Residual (Phần dư).
        """
        n = len(data)
        if n == 0:
            return {"trend": [], "seasonal": [], "residual": []}

        clean_data = [float(x) if (x is not None and not np.isnan(x)) else 0.0 for x in data]
        if n < max(4, period * 2):
            window_size = max(2, min(n, period // 2))
            trend = list(pd.Series(clean_data).rolling(window=window_size, min_periods=1, center=True).mean().values)
            seasonal = [0.0] * n
            resid = [float(clean_data[i] - trend[i]) for i in range(n)]
            return {
                "trend": [round(float(v), 4) for v in trend],
                "seasonal": seasonal,
                "residual": [round(float(v), 4) for v in resid]
            }

        try:
            series = pd.Series(clean_data)
            seasonal_win = period + 1 if (period % 2 == 0) else max(7, period)
            
            stl_model = STL(series, period=period, seasonal=seasonal_win, robust=robust)
            res = stl_model.fit()

            return {
                "trend": [round(float(v), 4) for v in res.trend.values],
                "seasonal": [round(float(v), 4) for v in res.seasonal.values],
                "residual": [round(float(v), 4) for v in res.resid.values]
            }
        except Exception as e:
            mean_val = float(np.mean(clean_data))
            return {
                "trend": [round(mean_val, 4)] * n,
                "seasonal": [0.0] * n,
                "residual": [round(float(v - mean_val), 4) for v in clean_data],
                "fallback": True,
            }


if __name__ == "__main__":
    print("=== TỰ KIỂM TRA MODULE STL_SERVICE.PY (LOESS) ===")
    np.random.seed(42)
    t = np.linspace(0, 10, 100)
    trend_true = 2.0 * t + 10.0
    season_true = 5.0 * np.sin(2 * np.pi * np.arange(100) / 7)
    noise = np.random.normal(0, 1, 100)
    data = (trend_true + season_true + noise).tolist()

    res = STLService.decompose(data, period=7, robust=True)
    assert len(res["trend"]) == 100
    assert len(res["seasonal"]) == 100
    assert len(res["residual"]) == 100

    reconstructed = np.array(res["trend"]) + np.array(res["seasonal"]) + np.array(res["residual"])
    max_diff = np.max(np.abs(reconstructed - np.array(data)))
    print(f"✓ Độ lệch tái cấu trúc (Trend + Seasonal + Resid vs Data): {max_diff:.6f}")
    assert max_diff < 1e-3, "Phân rã STL Loess bị sai tổng!"

    print("✅ TẤT CẢ SELF-CHECKS CỦA STL_SERVICE.PY ĐÃ PASS!")
