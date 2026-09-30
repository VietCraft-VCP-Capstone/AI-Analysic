"""
portrait_validation.py — API endpoint kiểm tra ảnh chân dung KYC.

Endpoint:
  POST /api/v1/portrait/validate
    - Nhận file ảnh chân dung (multipart/form-data)
    - Trả về: khuôn mặt, chất lượng, phát hiện AI, verdict

Được gọi từ Backend (Express) qua HTTP proxy.
"""

import logging

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.services.portrait_validation_service import validate_portrait

logger = logging.getLogger("portrait_validation_api")

router = APIRouter()

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

ALLOWED_CONTENT_TYPES = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
}


@router.post("/validate")
async def validate_portrait_image(
    file: UploadFile = File(..., description="Ảnh chân dung (JPG/PNG/WebP, tối đa 10MB)"),
):
    """Kiểm tra ảnh chân dung KYC.

    **Kết quả trả về:**
    - `face_detection`: Phát hiện khuôn mặt (số lượng, vị trí, tỷ lệ)
    - `quality`: Chất lượng ảnh (blur, brightness, resolution)
    - `ai_detection`: Phát hiện ảnh AI-generated (phân tích tần số, texture, noise)
    - `verdict`: Kết luận tổng hợp (PASSED / FAILED)
    - `warnings`: Danh sách cảnh báo chi tiết
    """
    # Validate content type
    content_type = (file.content_type or "").lower()
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "invalid_file_type",
                "message": f"Chỉ chấp nhận ảnh JPG, PNG, WebP. Nhận được: {content_type}",
            },
        )

    # Đọc file
    image_bytes = await file.read()

    if len(image_bytes) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "file_too_large",
                "message": f"File vượt quá giới hạn {MAX_FILE_SIZE // (1024 * 1024)}MB.",
            },
        )

    if len(image_bytes) < 1024:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "file_too_small",
                "message": "File quá nhỏ, có thể bị hỏng. Vui lòng tải lên ảnh chân dung rõ nét.",
            },
        )

    logger.info(
        f"Portrait validation request: size={len(image_bytes)} bytes, type={content_type}"
    )

    try:
        result = validate_portrait(image_bytes)
    except Exception as e:
        logger.error(f"Portrait validation failed: {type(e).__name__}: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "validation_failed",
                "message": f"Lỗi xử lý kiểm tra ảnh: {type(e).__name__}. Vui lòng thử lại.",
            },
        )

    return result
