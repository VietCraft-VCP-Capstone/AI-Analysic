import sys
from pathlib import Path
from datetime import datetime, timezone

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from typing import Optional

from fastapi import APIRouter
from bson import ObjectId
from pydantic import BaseModel, Field

from app.api.v1._live import db_live, la_shop_live
from app.api.v1._template import CurrentShop, forbidden, insufficient, meta_from_record, not_found, ok, build_meta
from app.core.f29.calculator import HealthScoreCalculator
from app.core.f29.preview import preview_health

router = APIRouter()


def _kiem_quyen_listing(id: str, shop_id: str) -> None:
    """404 nếu listing không có, 403 nếu listing thuộc shop khác."""
    try:
        product_id = ObjectId(id)
    except Exception:
        not_found("listing")
    product = db_live()["products"].find_one({"_id": product_id}, {"_id": 1, "shop_id": 1})
    if not product:
        not_found("listing")
    if product.get("shop_id") != ObjectId(shop_id):
        forbidden()


@router.get("/api/analytics/listings/{id}/health", tags=["F29 · Hạt"])
def health(id: str, shop_id: str = CurrentShop):
    """Đọc điểm sức khoẻ trực tiếp từ listing_health_scores collection."""

    if not la_shop_live(shop_id):
        return insufficient(
            "Cần cấu hình gian hàng trước khi xem sức khoẻ listing",
            build_meta(scope="listing", scope_id=id, database="vietcraft", mode="live")
        )

    _kiem_quyen_listing(id, shop_id)

    calculator = HealthScoreCalculator()
    result = calculator.calculate(id)

    if result is None:
        return insufficient(
            "Sản phẩm này không hợp lệ để chấm điểm",
            build_meta(scope="listing", scope_id=id, database="vietcraft", mode="live")
        )

    score = result.get("score")
    status = result.get("status")
    axes = result.get("axes", {})
    axes_missing = result.get("axes_missing", [])

    if score is None:
        return insufficient(
            "Không đủ dữ liệu để chấm điểm sản phẩm này",
            build_meta(
                scope="listing",
                scope_id=id,
                database="vietcraft",
                mode="live",
                attributed_to_live_shop=True,
                confidence="low"
            )
        )

    meta = build_meta(
        computed_at=result.get("computed_at"),
        model_version=result.get("model_version", "health-1.0"),
        scope="listing",
        scope_id=id,
        database="vietcraft",
        collection="products",
        mode="live",
        attributed_to_live_shop=True,
        sample_size=None,
        confidence="high" if not axes_missing else "medium"
    )

    return ok({
        "product_id": id,
        "score": score,
        "status": status,
        "axes": axes,
        "axes_missing": axes_missing,
        "todos": result.get("todos", []),
        "note": ("Trục thiếu dữ liệu bị LOẠI khỏi phép tính và trọng số chia lại cho "
                 "các trục còn lại — không cho 0 điểm, vì thiếu dữ liệu khác với kém."),
    }, meta)


class HealthPreviewBody(BaseModel):
    n_images: Optional[float] = Field(default=None, ge=0, le=50)
    description_length: Optional[float] = Field(default=None, ge=0, le=20000)
    n_tags: Optional[float] = Field(default=None, ge=0, le=50)
    in_stock_ratio_pct: Optional[float] = Field(default=None, ge=0, le=100)


@router.post("/api/analytics/listings/{id}/health/preview", tags=["F29 · Hạt"])
def health_preview(id: str, body: HealthPreviewBody, shop_id: str = CurrentShop):
    """Xem điểm nếu sửa (§4.3): chấm lại với giá trị giả định. Chỉ đọc, không ghi điểm."""
    meta_args = dict(scope="listing", scope_id=id, database="vietcraft", mode="live")
    if not la_shop_live(shop_id):
        return insufficient("Cần cấu hình gian hàng trước khi xem sức khoẻ listing", build_meta(**meta_args))

    _kiem_quyen_listing(id, shop_id)

    result = preview_health(HealthScoreCalculator(), id, body.model_dump())
    if result is None or result["score"] is None:
        return insufficient("Không đủ dữ liệu để chấm điểm sản phẩm này", build_meta(**meta_args))

    meta = build_meta(model_version=result.get("model_version") or "health-1.0",
                      collection="products", attributed_to_live_shop=True, **meta_args)
    return ok(result, meta)
