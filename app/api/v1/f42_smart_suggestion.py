"""
F42 · Smart Product Suggestion for Sellers (Refactored Data-Driven Engine).
Gợi ý tên sản phẩm SEO, từ khóa thị trường và khoảng giá tối ưu minh bạch.
"""

import sys
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Body

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
    targetMargin: Optional[float] = None,
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
