import logging
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.services.cccd_ocr_service import scan_cccd

logger = logging.getLogger("cccd_ocr_api")

router = APIRouter()

MAX_FILE_SIZE = 10 * 1024 * 1024

ALLOWED_CONTENT_TYPES = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
}


@router.post("/")
async def ocr_cccd(
    file: UploadFile = File(..., description="Ảnh CCCD (JPG/PNG/WebP, tối đa 10MB)"),
    side: str = Form("front", description="Mặt của CCCD: 'front' hoặc 'back'"),
):
    if side not in ("front", "back"):
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_param", "field": "side",
                    "message": "Tham số 'side' phải là 'front' hoặc 'back'."},
        )

    content_type = (file.content_type or "").lower()
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_file_type",
                    "message": f"Chỉ chấp nhận ảnh JPG, PNG, WebP. Nhận được: {content_type}"},
        )

    image_bytes = await file.read()

    if len(image_bytes) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail={"error": "file_too_large",
                    "message": f"File vượt quá giới hạn {MAX_FILE_SIZE // (1024*1024)}MB."},
        )

    if len(image_bytes) < 1024:
        raise HTTPException(
            status_code=400,
            detail={"error": "file_too_small",
                    "message": "File quá nhỏ, có thể bị hỏng. Vui lòng tải lên ảnh CCCD rõ nét."},
        )

    logger.info(f"OCR CCCD request: side={side}, size={len(image_bytes)} bytes, type={content_type}")

    try:
        result = scan_cccd(image_bytes, side=side)
    except Exception as e:
        logger.error(f"OCR CCCD failed: {type(e).__name__}: {e}")
        raise HTTPException(
            status_code=500,
            detail={"error": "ocr_failed",
                    "message": f"Lỗi xử lý OCR: {type(e).__name__}. Vui lòng thử lại."},
        )

    return result
