import numpy as np
from typing import List, Dict, Any

class ZScoreService:
    @staticmethod
    def detect_anomalies(data: List[float], threshold: float = 2.0) -> List[Dict[str, Any]]:
        """
        Calculates Z-scores and finds data points deviating significantly from the mean.
        """
        if not data:
            return []
        
        arr = np.array(data, dtype=float)
        mean = np.mean(arr)
        std = np.std(arr)
        
        if std == 0:
            std = 1e-9 # avoid division by zero
            
        z_scores = (arr - mean) / std
        
        results = []
        for idx, (val, z) in enumerate(zip(data, z_scores)):
            is_anomaly = float(abs(z)) > threshold
            results.append({
                "index": idx,
                "value": val,
                "z_score": float(z),
                "is_anomaly": bool(is_anomaly)
            })
            
        return results
