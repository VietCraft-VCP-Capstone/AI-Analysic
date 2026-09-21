"""
health_score.py — F29: chấm điểm sức khoẻ shop.

Bản trước có ba lỗi, đều đã sửa:

1. Trọng số không cộng thành 100. Thành phần xu hướng tính bằng
   `trend_weight * 2.0` với `trend_weight` chạy 5–15, tức đóng góp 10–30 điểm
   và KHÔNG BAO GIỜ về 0. Hệ quả: shop 0 sao, huỷ 100% đơn, xu hướng giảm vẫn
   được 10/100. Ca "tăng" thì tổng lên 110 rồi bị kẹp về 100, làm phần thưởng
   xu hướng mất tác dụng ở nhóm shop tốt.

2. Thiếu đánh giá thì mặc định 4.0 sao — tức "không có dữ liệu = tốt". Shop
   không có đánh giá nào, huỷ 100% đơn vẫn được 42/100. Đây là vi phạm thẳng
   nguyên tắc số một của dự án: THIẾU ≠ 0, và cũng ≠ TỐT. Thiếu thì phải nói
   là thiếu.

3. Không kiểm đầu vào. `cancellation_rate = 5.0` hay `ratings = [99]` đều lọt.

Thiết kế hiện tại: ba thành phần đều chuẩn hoá về thang 0–100, trọng số cộng
đúng 1.0, nên điểm tổng tự nằm trong [0, 100] mà không cần kẹp.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional

import numpy as np

from app.services.stl_service import STLService

router = APIRouter()

# Trọng số cộng đúng 1.0. Đổi ở đây thì đổi cả docs/HEALTH_SPEC.md.
W_RATING = 0.40
W_CANCELLATION = 0.40
W_TREND = 0.20

# Số điểm lịch sử tối thiểu để STL nói được điều gì có nghĩa.
MIN_TREND_POINTS = 6

# Ngưỡng coi là có xu hướng: lệch quá 5% so với điểm đầu của thành phần trend.
TREND_DELTA = 0.05

TREND_SCORE = {"upward": 100.0, "stable": 50.0, "downward": 0.0}


class HealthScoreRequest(BaseModel):
    seller_id: str = Field(..., min_length=1)
    ratings: List[float] = Field(
        default_factory=list,
        description="Điểm đánh giá 1.0–5.0. Rỗng thì trả insufficient_data, KHÔNG mặc định 4.0.",
    )
    cancellation_rate: float = Field(
        ..., ge=0.0, le=1.0, description="Tỉ lệ huỷ đơn, 0.0–1.0"
    )
    orders_volume_history: List[float] = Field(
        default_factory=list,
        description=f"Lịch sử sản lượng. Dưới {MIN_TREND_POINTS} điểm thì xu hướng bị bỏ qua.",
    )


class HealthScoreResponse(BaseModel):
    seller_id: str
    status: str                       # "ok" | "insufficient_data"
    health_score: Optional[float]     # None khi thiếu dữ liệu — không trả 0
    rating_average: Optional[float]
    trend_direction: str              # "upward" | "downward" | "stable" | "unknown"
    breakdown: Dict[str, Any]
    limitation: str


def _trend_direction(history: List[float]) -> str:
    """Hướng xu hướng từ phân rã STL. Trả 'unknown' khi chuỗi quá ngắn."""
    if len(history) < MIN_TREND_POINTS:
        return "unknown"
    try:
        period = max(2, len(history) // 3)
        trend = STLService.decompose(history, period=period)["trend"]
    except Exception:
        return "unknown"

    if len(trend) < 2:
        return "unknown"

    first = float(trend[0])
    if first == 0 or not np.isfinite(first):
        return "unknown"

    diff = float(trend[-1]) - first
    if diff > TREND_DELTA * abs(first):
        return "upward"
    if diff < -TREND_DELTA * abs(first):
        return "downward"
    return "stable"


@router.post("/", response_model=HealthScoreResponse)
async def calculate_health_score(payload: HealthScoreRequest):
    # Không có đánh giá thì không chấm được. Nói thẳng thay vì đoán 4.0 sao.
    if not payload.ratings:
        return HealthScoreResponse(
            seller_id=payload.seller_id,
            status="insufficient_data",
            health_score=None,
            rating_average=None,
            trend_direction="unknown",
            breakdown={"reason": "Chưa có đánh giá nào cho shop này."},
            limitation=(
                "Không chấm điểm khi chưa có đánh giá. Điểm sức khoẻ thiếu trục "
                "chất lượng sẽ gây hiểu nhầm, nên trả null thay vì một con số."
            ),
        )

    if any((not np.isfinite(r)) or r < 0.0 or r > 5.0 for r in payload.ratings):
        raise HTTPException(
            status_code=422, detail="Mọi điểm đánh giá phải là số hữu hạn trong khoảng 0.0–5.0"
        )

    avg_rating = float(np.mean(payload.ratings))
    rating_score = (avg_rating / 5.0) * 100.0
    cancellation_score = (1.0 - payload.cancellation_rate) * 100.0

    direction = _trend_direction(payload.orders_volume_history)

    if direction == "unknown":
        # Thiếu trục xu hướng thì chia lại trọng số cho hai trục còn lại,
        # thay vì tặng điểm mặc định cho một thứ chưa đo được.
        denom = W_RATING + W_CANCELLATION
        score = (rating_score * W_RATING + cancellation_score * W_CANCELLATION) / denom
        trend_component = None
        limitation = (
            f"Lịch sử sản lượng dưới {MIN_TREND_POINTS} điểm nên bỏ qua trục xu hướng; "
            "điểm tính lại trên hai trục còn lại."
        )
    else:
        trend_component = TREND_SCORE[direction]
        score = (
            rating_score * W_RATING
            + cancellation_score * W_CANCELLATION
            + trend_component * W_TREND
        )
        limitation = "Điểm tính trên dữ liệu do bên gọi cung cấp, chưa đối chiếu với dữ liệu sàn."

    return HealthScoreResponse(
        seller_id=payload.seller_id,
        status="ok",
        health_score=round(float(score), 2),
        rating_average=round(avg_rating, 2),
        trend_direction=direction,
        breakdown={
            "rating": {"score": round(rating_score, 2), "weight": W_RATING},
            "cancellation": {"score": round(cancellation_score, 2), "weight": W_CANCELLATION},
            "trend": {
                "score": trend_component,
                "weight": 0.0 if trend_component is None else W_TREND,
                "direction": direction,
            },
            "n_ratings": len(payload.ratings),
            "n_history_points": len(payload.orders_volume_history),
        },
        limitation=limitation,
    )
