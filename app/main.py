import sys
from pathlib import Path

# Thêm thư mục gốc vào sys.path để cho phép chạy trực tiếp `python app/main.py`
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.api.v1.forecasting import router as forecasting_router
from app.api.v1.anomaly import router as anomaly_router
from app.api.v1.health_score import router as health_score_router

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json"
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Health endpoint
@app.get("/health")
def read_health():
    return {"status": "ok", "service": "ai-analytics"}

# Include routes
app.include_router(forecasting_router, prefix=f"{settings.API_V1_STR}/forecasting", tags=["Forecasting"])
app.include_router(anomaly_router, prefix=f"{settings.API_V1_STR}/anomaly", tags=["Anomaly Detection"])
app.include_router(health_score_router, prefix=f"{settings.API_V1_STR}/health_score", tags=["Health Evaluation"])

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=settings.PORT)
