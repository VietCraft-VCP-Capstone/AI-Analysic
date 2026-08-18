import pandas as pd
import numpy as np
from statsmodels.tsa.seasonal import seasonal_decompose
from typing import Dict, List, Any

class STLService:
    @staticmethod
    def decompose(data: List[float], period: int = 7) -> Dict[str, List[float]]:
        """
        Decomposes time series data into trend, seasonal, and residual components.
        """
        if len(data) < period * 2:
            # Fallback for insufficient data points
            trend = list(pd.Series(data).rolling(window=max(3, period // 2), min_periods=1).mean().values)
            seasonal = [0.0] * len(data)
            resid = [float(data[i] - trend[i]) for i in range(len(data))]
            return {
                "trend": trend,
                "seasonal": seasonal,
                "residual": resid
            }
        
        try:
            series = pd.Series(data)
            decomposition = seasonal_decompose(series, model='additive', period=period, extrapolate_trend='freq')
            return {
                "trend": [float(v) for v in decomposition.trend.values],
                "seasonal": [float(v) for v in decomposition.seasonal.values],
                "residual": [float(v) for v in decomposition.resid.values]
            }
        except Exception as e:
            # Fallback
            mean_val = float(np.mean(data))
            return {
                "trend": [mean_val] * len(data),
                "seasonal": [0.0] * len(data),
                "residual": [float(v - mean_val) for v in data]
            }
