from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional

from app.services.zscore_service import (
    DEFAULT_PERIOD,
    DEFAULT_THRESHOLD,
    MAX_ANOMALY_RATE,
    ZScoreService,
)

router = APIRouter()


class AnomalyRequest(BaseModel):
    data: List[float] = Field(..., min_length=1, description="Chuỗi giá trị theo thời gian")
    dates: Optional[List[str]] = Field(
        None, description="Mốc thời gian cùng độ dài với data; có thì điểm trong cửa sổ Tết được đánh dấu"
    )
    threshold: float = Field(
        DEFAULT_THRESHOLD, gt=0,
        description="Ngưỡng điểm z hiệu chỉnh. Mặc định hiệu chuẩn bằng mô phỏng, không phải 3.5 sách giáo khoa.",
    )
    period: int = Field(
        DEFAULT_PERIOD, ge=2,
        description="Chu kỳ mùa vụ theo số điểm: 7 cho chuỗi ngày, 52 cho chuỗi tuần",
    )
    max_anomaly_rate: float = Field(MAX_ANOMALY_RATE, gt=0, le=1)
    top_n: int = Field(10, ge=1, le=100)


class AnomalyResponse(BaseModel):
    status: str
    method: str
    period: int
    threshold: float
    scale: float
    seasonality_removed: bool
    cycles_observed: float
    anomaly_count: int
    anomaly_rate: float
    calendar_sensitive_count: int
    sample_size: int
    reliability_note: str
    limitation: str
    top_anomalies: List[Dict[str, Any]]
    anomalies: List[Dict[str, Any]]


@router.post("/", response_model=AnomalyResponse)
async def detect_anomalies(payload: AnomalyRequest):
    """
    Phát hiện bất thường trên phần dư STL bằng thống kê bền vững.

    Trả kèm `status` và `reliability_note`: khi chuỗi không đủ chu kỳ mùa vụ
    hoặc tỉ lệ gắn cờ vượt ngưỡng, kết quả bị hạ cờ tin cậy thay vì trả về một
    danh sách dài giả vờ là bất thường.
    """
    try:
        result = ZScoreService.analyze(
            payload.data,
            dates=payload.dates,
            threshold=payload.threshold,
            period=payload.period,
            max_anomaly_rate=payload.max_anomaly_rate,
            top_n=payload.top_n,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return AnomalyResponse(anomalies=result["points"], **{
        k: result[k] for k in (
            "status", "method", "period", "threshold", "scale", "seasonality_removed",
            "cycles_observed", "anomaly_count", "anomaly_rate", "calendar_sensitive_count",
            "sample_size", "reliability_note", "limitation", "top_anomalies",
        )
    })
