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
from app.api.v1.cccd_ocr import router as cccd_ocr_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    """In lúc khởi động: hôm nay mấy tính năng đã chạy thật, mấy cái còn là khung.

    Dùng lifespan chứ không phải @app.on_event: starlette 1.6 đã bỏ on_event.
    """
    def ra(*d):
        print(*d, flush=True)

    that = sorted(f for f, v in TRANG_THAI_F.items() if v == "that")
    khung = sorted(f for f, v in TRANG_THAI_F.items() if v == "khung")

    ra("=" * 72)
    ra(f"  VietCraft AI Analytics  ·  {len(that)}/{len(TRANG_THAI_F)} tinh nang co code that")
    if khung:
        ra(f"  Con la khung (tra 503): {', '.join(khung)}")

    ra("-" * 72)
    try:
        from pymongo import MongoClient

        from app.core.writer import MART_SCHEMA
        cl = MongoClient(settings.MONGO_URI, serverSelectionTimeoutMS=3000)
        rong = [t for t in MART_SCHEMA if cl[settings.MONGO_DB_SEED][t].estimated_document_count() == 0]
        cl.close()
        if rong:
            ra(f"  [!] {len(rong)}/{len(MART_SCHEMA)} bang mart CON RONG: {', '.join(sorted(rong))}")
            ra("      Endpoint doc cac bang do se tra 503 mart_not_ready.")
            ra("      Khac phuc:  python -m app.core.build_marts --all")
        else:
            ra(f"  [OK] Ca {len(MART_SCHEMA)} bang mart deu co du lieu. Goi API la ra so.")
    except Exception as e:
        ra(f"  [?] Chua kiem duoc mart: {type(e).__name__}. Kiem MONGODB_URI trong app/.env.")
        ra("      API van khoi dong, nhung se tra 503 neu khong noi duoc MongoDB.")

    che_do = che_do_xac_thuc()
    ra("-" * 72)
    if che_do:
        ra(f"  [!!] XAC THUC DANG {che_do}")
        ra("       Chi dung khi dang viet tinh nang. TAT truoc khi deploy hay demo.")
    else:
        ra("  [OK] Xac thuc DANG BAT. Moi endpoint tra 401 neu khong co token.")
        ra("       Chua co SPEC-04 (JWT) thi chay thu bang: DEV_SHOP_ID=shp_00017")
    ra("  Swagger:  <dia chi uvicorn in o tren> + /docs")
    ra("=" * 72)

    yield


app = FastAPI(
    lifespan=lifespan,
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json"
)

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


TRANG_THAI_F = gan_analytics(app)

# Include routes
app.include_router(anomaly_router, prefix=f"{settings.API_V1_STR}/anomaly", tags=["Anomaly Detection"])
app.include_router(health_score_router, prefix=f"{settings.API_V1_STR}/health_score", tags=["Health Evaluation"])
app.include_router(cccd_ocr_router, prefix=f"{settings.API_V1_STR}/ocr/cccd", tags=["CCCD OCR & Verification"])




if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=settings.PORT)
