from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.api_route("/", methods=["GET", "POST"], include_in_schema=False)
async def da_go():
    raise HTTPException(
        status_code=410,
        detail={
            "error": "endpoint_removed",
            "reason": "Endpoint này phục vụ mô hình LSTM chưa train (trọng số ngẫu nhiên).",
            "replacement": "GET /api/analytics/forecast/revenue",
            "task": "API-99",
        },
    )
