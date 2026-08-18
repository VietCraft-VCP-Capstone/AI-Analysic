from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, conlist
from typing import List
from app.models.lstm_model import LSTMModelService

router = APIRouter()

class ForecastRequest(BaseModel):
    history: List[float]
    steps: int = 5

class ForecastResponse(BaseModel):
    history: List[float]
    predictions: List[float]

@router.post("/", response_model=ForecastResponse)
async def forecast_sales(payload: ForecastRequest):
    if not payload.history:
        raise HTTPException(status_code=400, detail="History array cannot be empty")
    
    try:
        predictions = LSTMModelService.forecast(payload.history, payload.steps)
        return ForecastResponse(
            history=payload.history,
            predictions=predictions
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
