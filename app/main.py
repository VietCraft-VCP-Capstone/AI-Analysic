import os
import sys
from pathlib import Path
from typing import Any

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
from app.api.v1.cccd_ocr import router as cccd_ocr_router
from app.api.v1.f42_smart_suggestion import router as smart_suggestion_router

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
    if os.getenv("AI_GATEWAY_SECRET", "").strip():
        ra("  [OK] Gateway BE san: BAT (AI_GATEWAY_SECRET). BE goi kem X-Shop-Id da xac thuc.")
    else:
        ra("  [!]  Gateway BE san: TAT. Dat AI_GATEWAY_SECRET giong ben BE de san goi duoc.")
    try:
        from app.core.listing_intel import embedder
        if embedder.available():
            ra(f"  [OK] Listing Intel: model ONNX san sang o {embedder.MODEL_DIR}")
        else:
            ra(f"  [!!] Listing Intel: THIEU model ONNX o {embedder.MODEL_DIR} (LI_MODEL_DIR).")
            ra("       Truc anh, thi truong va khop tu khoa chay rut gon. Tai: python -m scripts.li.fetch_models")
    except Exception as e:
        ra(f"  [!] Listing Intel: khong kiem duoc model ONNX: {type(e).__name__}")
    ra("  Swagger:  <dia chi uvicorn in o tren> + /docs")

    try:
        from app.core.f29_scheduler import start_scheduler
        start_scheduler()
        ra("  [OK] F29 scheduler: da bat (quet doi moi 60s + quet toan san 0h UTC).")
    except Exception as e:
        ra(f"  [!] F29 scheduler KHONG bat duoc: {type(e).__name__}: {e}")
    ra("=" * 72)

    yield

    try:
        from app.core.f29_scheduler import stop_scheduler
        stop_scheduler()
    except Exception:
        pass


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


@app.get("/ready")
def read_ready():
    from datetime import datetime, timezone

    from app.api.v1._live import db_live
    from app.api.v1._mart import db

    try:
        db_live().command("ping")
    except Exception as e:
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "reason": "mongo_unreachable", "detail": str(e)[:200]},
        )

    try:
        mart_db = db()
        co_mart = (
            mart_db["mart_listing_quality"].count_documents({}, limit=1) > 0
            or mart_db["listing_health"].count_documents({}, limit=1) > 0
        )
    except Exception:
        co_mart = False

    if not co_mart:
        return JSONResponse(status_code=503, content={"status": "not_ready", "reason": "mart_empty"})

    body: dict[str, Any] = {"status": "ok"}

    try:
        mart_db = db()
        latest = mart_db["listing_health_scores"].find_one({}, sort=[("computed_at", -1)])
        if latest and latest.get("computed_at"):
            raw = latest["computed_at"]
            computed_at = None
            if isinstance(raw, str):
                computed_at = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            elif isinstance(raw, datetime):
                computed_at = raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
            if computed_at is not None:
                gio_tre = (datetime.now(timezone.utc) - computed_at).total_seconds() / 3600.0
                if gio_tre > 26:
                    body["status"] = "stale"
                    body["last_run_hours_ago"] = round(gio_tre, 1)
    except Exception:
        pass

    return JSONResponse(status_code=200, content=body)


TRANG_THAI_F = gan_analytics(app)

# Include routes
app.include_router(cccd_ocr_router, prefix=f"{settings.API_V1_STR}/ocr/cccd", tags=["CCCD OCR & Verification"])
app.include_router(smart_suggestion_router)



if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=settings.PORT)
