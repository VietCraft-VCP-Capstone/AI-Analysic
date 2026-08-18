from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any
from app.services.zscore_service import ZScoreService

router = APIRouter()

class AnomalyRequest(BaseModel):
    data: List[float]
    threshold: float = 2.0

class AnomalyResponse(BaseModel):
    anomalies: List[Dict[str, Any]]

@router.post("/", response_model=AnomalyResponse)
async def detect_anomalies(payload: AnomalyRequest):
    if not payload.data:
        raise HTTPException(status_code=400, detail="Data series cannot be empty")
        
    try:
        anomalies = ZScoreService.detect_anomalies(payload.data, payload.threshold)
        return AnomalyResponse(anomalies=anomalies)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
