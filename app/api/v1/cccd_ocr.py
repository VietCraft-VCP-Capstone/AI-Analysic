import hmac
import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile

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


def verify_gateway_secret(
    x_gateway_secret: Optional[str] = Header(default=None, alias="X-Gateway-Secret"),
) -> None:
    """Xác thực bảo vệ endpoint nội bộ: Chỉ cho phép Backend VietCraft gọi qua X-Gateway-Secret."""
    dev_mode = (
        os.getenv("DEV_TRUST_SHOP_HEADER", "").strip() == "1"
        or os.getenv("DEV_DISABLE_AUTH", "").strip() == "1"
    )
    expected_secret = os.getenv("AI_GATEWAY_SECRET", "").strip()

    if not expected_secret:
        if dev_mode:
            return
        logger.warning("[CCCD OCR Security] AI_GATEWAY_SECRET chưa được cấu hình. Từ chối yêu cầu để đảm bảo an toàn PII.")
        raise HTTPException(
            status_code=503,
            detail={
                "error": "gateway_secret_not_configured",
                "message": "Dịch vụ AI chưa cấu hình AI_GATEWAY_SECRET bảo vệ endpoint OCR nội bộ.",
            },
        )

    if not x_gateway_secret or not hmac.compare_digest(x_gateway_secret.encode("utf-8"), expected_secret.encode("utf-8")):
        logger.warning("[CCCD OCR Security] Từ chối request: X-Gateway-Secret không hợp lệ hoặc bị thiếu.")
        raise HTTPException(
            status_code=401,
            detail={"error": "unauthorized", "message": "Yêu cầu quyền truy cập nội bộ hợp lệ (X-Gateway-Secret)."},
        )


@router.post("/", dependencies=[Depends(verify_gateway_secret)])
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

    # Đọc stream theo chunk 64KB có giới hạn để ngăn chặn cạn kiệt RAM do file quá lớn
    chunk_size = 64 * 1024
    total_read = 0
    chunks = []
    while True:
        chunk = await file.read(chunk_size)
        if not chunk:
            break
        total_read += len(chunk)
        if total_read > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=400,
                detail={"error": "file_too_large",
                        "message": f"File vượt quá giới hạn cho phép {MAX_FILE_SIZE // (1024*1024)}MB."},
            )
        chunks.append(chunk)

    image_bytes = b"".join(chunks)

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
