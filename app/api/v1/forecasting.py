"""
forecasting.py — ĐÃ VÔ HIỆU HOÁ (API-99, 21/09/2026).

Router này từng phục vụ `POST /api/v1/forecasting/` bằng LSTMModelService.
`app/models/lstm_model.py` là mạng LSTM **CHƯA TRAIN** — trọng số khởi tạo ngẫu
nhiên. Và torch không có trong requirements.txt, nên trên máy cài đúng
requirements nó luôn rơi vào nhánh dự phòng: kéo dài một đường thẳng nối điểm
đầu với điểm cuối rồi trả về như thể đó là dự báo.

Số trông rất hợp lý mà không có căn cứ nào. Ai mở Swagger `/docs` bấm thử — kể cả
hội đồng — đều nhận được số đó. Rủi ro uy tín, không phải lỗi kỹ thuật.

ĐÃ GỠ khỏi `app/main.py`. File giữ lại để quyết định này không bị ai vô tình
đảo ngược: nếu có người include_router lại, handler dưới đây trả 410 kèm lý do
thay vì trả số.

Thay thế: **F37** `GET /api/analytics/forecast/revenue` — đọc mart `forecast_point`
do job chạy đêm ghi, kèm dải `lo95`/`hi95` (BR-206, BR-207).
Chọn mô hình nào cho F37 là việc của SPEC-03 (hạn 29/09).
"""

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
