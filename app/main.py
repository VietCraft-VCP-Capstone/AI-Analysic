import os
import sys
from pathlib import Path

# Thêm thư mục gốc vào sys.path để cho phép chạy trực tiếp `python app/main.py`
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.config import settings
from app.api.v1._template import che_do_xac_thuc
from app.api.v1.analytics_routes import gan_vao as gan_analytics
from app.api.v1.anomaly import router as anomaly_router
from app.api.v1.health_score import router as health_score_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    """In lúc khởi động: hôm nay mấy tính năng đã chạy thật, mấy cái còn là khung.

    Dùng lifespan chứ không phải @app.on_event: starlette 1.6 đã bỏ on_event.
    """
    # flush=True: khi stdout không phải terminal (chạy qua systemd, docker, hay
    # ghi ra file log) thì print() bị đệm, và cảnh báo tắt xác thực dưới đây có
    # thể mất trắng nếu tiến trình bị kill. Cảnh báo an toàn thì không được mất.
    that = sorted(f for f, v in TRANG_THAI_F.items() if v == "that")
    khung = sorted(f for f, v in TRANG_THAI_F.items() if v == "khung")
    print(f"[F26-F41] {len(that)} tinh nang chay that: {', '.join(that) or '(chua co)'}", flush=True)
    print(f"[F26-F41] {len(khung)} con la khung, tra 503 mart_not_ready: {', '.join(khung)}", flush=True)

    che_do = che_do_xac_thuc()
    if che_do:
        print("!" * 72, flush=True)
        print(f"!!  XAC THUC DANG {che_do}", flush=True)
        print("!!  Chi dung khi dang viet tinh nang. TAT truoc khi deploy hay demo:", flush=True)
        print("!!  bo DEV_SHOP_ID / DEV_TRUST_SHOP_HEADER khoi .env va moi truong.", flush=True)
        print("!" * 72, flush=True)
    yield


app = FastAPI(
    lifespan=lifespan,
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json"
)

# ---------------------------------------------------------------------------
# CORS — danh sách origin THẬT, không dùng "*".
#
# Bản cũ đặt allow_origins=["*"] kèm allow_credentials=True. Tổ hợp đó vừa không
# an toàn (mọi trang web đọc được dữ liệu shop của người đang đăng nhập) vừa
# KHÔNG CHẠY: trình duyệt từ chối "*" khi có credentials, nên FE thật sẽ gặp lỗi
# CORS mà không ai hiểu vì sao.
#
# Thêm origin của FE sàn vào CORS_ORIGINS trong .env, cách nhau bằng dấu phẩy.
# ---------------------------------------------------------------------------
CORS_ORIGINS = [o.strip() for o in os.getenv(
    "CORS_ORIGINS",
    "http://localhost:3000,http://localhost:5173,http://localhost:4174",
).split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


# ---------------------------------------------------------------------------
# BODY LỖI — đúng hình dạng hợp đồng, không bọc trong {"detail": ...}
#
# Mặc định FastAPI trả {"detail": <thứ bạn ném>}. Hợp đồng mục 1 ghi body phẳng:
#     {"error": "mart_not_ready", "collection": "mart_demand"}
# Lệch một lớp bọc là FE phải viết hai cách đọc. Gỡ lớp đó ở đây một lần cho cả 16.
# ---------------------------------------------------------------------------
@app.exception_handler(HTTPException)
async def _loi_theo_hop_dong(request: Request, exc: HTTPException):
    body = exc.detail if isinstance(exc.detail, dict) else {"error": str(exc.detail)}
    return JSONResponse(status_code=exc.status_code, content=body, headers=exc.headers)


@app.exception_handler(RequestValidationError)
async def _tham_so_sai(request: Request, exc: RequestValidationError):
    """422 của FastAPI -> 400 invalid_param như hợp đồng đã ghi."""
    loi = exc.errors()[0] if exc.errors() else {}
    truong = ".".join(str(x) for x in loi.get("loc", [])[1:]) or "unknown"
    return JSONResponse(status_code=400,
                        content={"error": "invalid_param", "field": truong})


@app.exception_handler(Exception)
async def _loi_khong_ngo(request: Request, exc: Exception):
    """Không để lọt nội dung lỗi gốc của Python ra ngoài (hợp đồng mục 1).

    Vẫn in đầy đủ vào log của server để còn gỡ được.
    """
    import traceback
    traceback.print_exc()
    return JSONResponse(status_code=500, content={"error": "internal_error"})


# Health endpoint
@app.get("/health")
def read_health():
    return {"status": "ok", "service": "ai-analytics"}


# ---------------------------------------------------------------------------
# 16 endpoint phân tích F26–F41.
#
# Đường dẫn theo đúng docs/API_CONTRACT.md mục 3 (`/api/analytics/...`), KHÔNG
# nằm dưới /api/v1 — hợp đồng với FE sàn đã chốt như vậy.
# ---------------------------------------------------------------------------
TRANG_THAI_F = gan_analytics(app)

# Include routes
app.include_router(anomaly_router, prefix=f"{settings.API_V1_STR}/anomaly", tags=["Anomaly Detection"])
app.include_router(health_score_router, prefix=f"{settings.API_V1_STR}/health_score", tags=["Health Evaluation"])

# ---------------------------------------------------------------------------
# API-99 — ĐÃ GỠ `forecasting_router`.
#
# app/api/v1/forecasting.py phục vụ LSTMModelService, mà app/models/lstm_model.py
# là mạng LSTM CHƯA TRAIN (trọng số ngẫu nhiên), và torch còn không có trong
# requirements.txt nên nó rơi vào nhánh dự phòng: kéo dài đường thẳng từ 2 điểm
# đầu-cuối rồi gọi đó là "dự báo".
#
# Ai mở /docs bấm thử sẽ nhận một con số trông rất hợp lý mà không có căn cứ nào.
# Đây là rủi ro uy tín lớn nhất của dự án, không phải lỗi kỹ thuật.
#
# Thay bằng: F37 `GET /api/analytics/forecast/revenue` — đọc mart `forecast_point`
# do job chạy đêm ghi, kèm dải lo95/hi95 theo BR-206 / BR-207.
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=settings.PORT)
