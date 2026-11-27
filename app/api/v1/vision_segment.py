"""Route nội bộ tách phôi khỏi nền cho mockup POD (BE VietCraft và backend xưởng in gọi)."""

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response

from app.api.v1._template import require_gateway
from app.services import segment_service

router = APIRouter(prefix="/api/internal/vision", tags=["Tách nền phôi (nội bộ)"],
                   dependencies=[Depends(require_gateway)])

MAX_FILE_SIZE = 15 * 1024 * 1024


# Hàm đồng bộ: suy luận ONNX chạy vài giây trên CPU, FastAPI đưa vào threadpool để không chặn event loop.
@router.post("/segment", responses={200: {"content": {"image/png": {}}}})
def post_segment(file: UploadFile = File(..., description="Ảnh phôi (JPG/PNG/WebP)")):
    """Trả về PNG mask xám cùng kích thước ảnh: trắng = phôi, đen = nền (gồm cả bóng đổ)."""
    if not segment_service.available():
        raise HTTPException(status_code=503, detail={
            "error": "model_missing",
            "message": "Chưa có model tách nền. Chạy: python -m scripts.seg.fetch_model",
        })
    data = file.file.read(MAX_FILE_SIZE + 1)
    if not data:
        raise HTTPException(status_code=400, detail={"error": "empty_file"})
    if len(data) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail={"error": "file_too_large"})
    try:
        png, coverage = segment_service.segment_bytes(data)
    except Exception as e:  # ảnh hỏng, định dạng lạ
        raise HTTPException(status_code=400, detail={"error": "bad_image", "message": str(e)[:200]})
    return Response(content=png, media_type="image/png", headers={
        "X-Seg-Model": segment_service.MODEL_NAME,
        "X-Seg-Coverage": f"{coverage:.4f}",
    })
