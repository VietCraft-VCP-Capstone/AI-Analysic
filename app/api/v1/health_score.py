from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any
from app.services.stl_service import STLService
import numpy as np

router = APIRouter()

class HealthScoreRequest(BaseModel):
    seller_id: str
    ratings: List[float]          # Product review ratings (e.g. 1.0 to 5.0)
    cancellation_rate: float     # Order cancellation rate (0.0 to 1.0)
    orders_volume_history: List[float] # Sales volume history for trend extraction

class HealthScoreResponse(BaseModel):
    seller_id: str
    health_score: float
    rating_average: float
    trend_direction: str         # 'upward', 'downward', 'stable'
    breakdown: Dict[str, Any]

@router.post("/", response_model=HealthScoreResponse)
async def calculate_health_score(payload: HealthScoreRequest):
    try:
        # Calculate rating weight
        avg_rating = float(np.mean(payload.ratings)) if payload.ratings else 4.0
        # Normalize rating metric to 0-100 (5.0 rating = 100 points)
        rating_score = (avg_rating / 5.0) * 100.0
        
        # Calculate cancellation weight (0% cancellations = 100 points, 100% cancellations = 0 points)
        cancellation_score = (1.0 - payload.cancellation_rate) * 100.0
        
        # Trend impact check via STL decomposition
        trend_direction = "stable"
        trend_weight = 10.0
        if payload.orders_volume_history:
            stl_result = STLService.decompose(payload.orders_volume_history, period=max(2, len(payload.orders_volume_history) // 3))
            trends = stl_result["trend"]
            if len(trends) > 1:
                diff = trends[-1] - trends[0]
                if diff > 0.05 * trends[0]:
                    trend_direction = "upward"
                    trend_weight += 5.0
                elif diff < -0.05 * trends[0]:
                    trend_direction = "downward"
                    trend_weight -= 5.0

        # Weighted calculation (40% rating, 40% cancellation avoidance, 20% history volume trend)
        final_health = (rating_score * 0.4) + (cancellation_score * 0.4) + (trend_weight * 2.0)
        
        # Clamp health score to [0, 100]
        final_health = float(max(0.0, min(100.0, final_health)))

        return HealthScoreResponse(
            seller_id=payload.seller_id,
            health_score=round(final_health, 2),
            rating_average=round(avg_rating, 2),
            trend_direction=trend_direction,
            breakdown={
                "rating_score_component": round(rating_score, 2),
                "cancellation_score_component": round(cancellation_score, 2),
                "trend_weight_applied": trend_weight
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
