"""
F42 · Smart Product Suggestion for Sellers (Refactored Data-Driven Engine).
Gợi ý tên sản phẩm SEO, từ khóa thị trường và khoảng giá tối ưu minh bạch.
"""

import sys
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field

from fastapi import APIRouter, Body, Query

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.api.v1._template import CurrentShop, ok
from app.services.f42 import F42Orchestrator
from app.services.f42.schemas import SuggestionRequest

router = APIRouter()


@router.post("/api/v1/product/smart-suggestion", tags=["F42 · Smart Product Assistant"])
def post_smart_suggestion(
    payload: Optional[SuggestionRequest] = Body(default=None),
    shop_id: str = CurrentShop
):
    req = payload or SuggestionRequest()
    result = F42Orchestrator.execute(req)
    return ok(result.model_dump())


@router.get("/api/v1/product/smart-suggestion", tags=["F42 · Smart Product Assistant"])
def get_smart_suggestion(
    categoryId: Optional[str] = None,
    categoryName: Optional[str] = None,
    productType: Optional[str] = None,
    keywords: Optional[str] = None,
    title: Optional[str] = None,
    material: Optional[str] = None,
    blankCost: Optional[float] = None,
    targetMargin: Optional[float] = Query(default=None, ge=0, le=3),
    shop_id: str = CurrentShop
):
    req = SuggestionRequest(
        categoryId=categoryId,
        categoryName=categoryName,
        productType=productType,
        keywords=keywords or title,
        title=title or keywords,
        material=material,
        blankCost=blankCost,
        targetMargin=targetMargin
    )
    result = F42Orchestrator.execute(req)
    return ok(result.model_dump())


class RecognizeImageRequest(BaseModel):
    image_base64: Optional[str] = Field(None, description="1 ảnh base64 / data URL (client cũ)")
    images: Optional[List[str]] = Field(None, description="Tối đa 6 ảnh cùng sản phẩm (các màu khác nhau)")
    mime_type: Optional[str] = None


@router.post("/api/v1/product/recognize-image", tags=["F42 · Smart Product Assistant"])
def recognize_image(payload: RecognizeImageRequest, shop_id: str = CurrentShop):
    """Ảnh sản phẩm → tên gợi ý, loại, danh mục của sàn, chất liệu/màu nhìn thấy. Seller xác nhận trước khi dùng."""
    from fastapi import HTTPException
    from app.services.f42.image_recognizer import ImageInputError, recognize_product_image
    from app.services.f42.orchestrator import _get_categories, _get_live_db

    categories = [str(c.get("name")) for c in _get_categories(_get_live_db()) if c.get("name")]
    try:
        result = recognize_product_image(payload.images or ([payload.image_base64] if payload.image_base64 else []),
                                         payload.mime_type or "", categories)
    except ImageInputError as exc:
        raise HTTPException(status_code=400, detail={"error": "invalid_image", "message": str(exc)})
    if result.get("error"):
        raise HTTPException(status_code=503, detail={"error": "ai_unavailable", "message": result["error"]})
    return ok(result)
