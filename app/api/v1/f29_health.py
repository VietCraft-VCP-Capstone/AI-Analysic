import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from typing import Optional

from fastapi import APIRouter
from bson import ObjectId
from pydantic import BaseModel, Field

from app.api.v1._live import db_live, la_shop_live
from app.api.v1._template import CurrentShop, forbidden, insufficient, not_found, ok, build_meta
from app.core.f29.calculator import HealthScoreCalculator
from app.core.f29.constants import MODEL_VERSION
from app.core.f29.ml.scorer import load_model, score_listing
from app.core.f29.preview import preview_health

router = APIRouter()
NO_SHOP = "Cần cấu hình gian hàng trước khi xem sức khoẻ listing"
NO_WEIGHTS = "Điểm sức khoẻ đang được cập nhật, vui lòng thử lại sau."


def _kiem_quyen_listing(id: str, shop_id: str) -> None:
    try:
        product_id = ObjectId(id)
    except Exception:
        not_found("listing")
    product = db_live()["products"].find_one({"_id": product_id}, {"_id": 1, "shop_id": 1})
    if not product:
        not_found("listing")
    try:
        shop_oid = ObjectId(shop_id)
    except Exception:
        forbidden()
    if product.get("shop_id") != shop_oid:
        forbidden()


class HealthPreviewBody(BaseModel):
    n_images: Optional[float] = Field(default=None, ge=0, le=50)
    description_length: Optional[float] = Field(default=None, ge=0, le=20000)
    n_tags: Optional[float] = Field(default=None, ge=0, le=50)
    price: Optional[float] = Field(default=None, ge=0, le=1e10)


@router.get("/api/analytics/listings/{id}/health", tags=["F29 · Hạt"])
def health_score(id: str, shop_id: str = CurrentShop):
    meta_args = dict(scope="listing", scope_id=id, database="vietcraft", mode="live")
    if not la_shop_live(shop_id):
        return insufficient(NO_SHOP, build_meta(**meta_args))

    _kiem_quyen_listing(id, shop_id)

    try:
        result = HealthScoreCalculator().calculate(id)
    except Exception as e:
        print(f"[f29_health] {type(e).__name__}: {e}", flush=True)
        return insufficient("Hệ thống chưa thể tính điểm cho sản phẩm này, vui lòng thử lại sau.", build_meta(**meta_args))
    if result is None:
        not_found("listing")
    if "error" in result:
        return insufficient(NO_WEIGHTS, build_meta(**meta_args))

    meta = build_meta(model_version=MODEL_VERSION, collection="products", attributed_to_live_shop=True, **meta_args)
    return ok(result, meta)


@router.post("/api/analytics/listings/{id}/health/preview", tags=["F29 · Hạt"])
def health_preview(id: str, body: HealthPreviewBody, shop_id: str = CurrentShop):
    meta_args = dict(scope="listing", scope_id=id, database="vietcraft", mode="live")
    if not la_shop_live(shop_id):
        return insufficient(NO_SHOP, build_meta(**meta_args))

    _kiem_quyen_listing(id, shop_id)

    try:
        result = preview_health(HealthScoreCalculator(), id, body.model_dump())
    except Exception as e:
        print(f"[f29_health] {type(e).__name__}: {e}", flush=True)
        return insufficient("Hệ thống chưa thể tính điểm xem trước, vui lòng thử lại sau.", build_meta(**meta_args))
    if result is None:
        return insufficient("Không đủ dữ liệu để chấm điểm sản phẩm này", build_meta(**meta_args))
    if "error" in result:
        return insufficient(NO_WEIGHTS, build_meta(**meta_args))

    meta = build_meta(model_version=result["model_version"], collection="products",
                      attributed_to_live_shop=True, **meta_args)
    return ok(result, meta)


@router.get("/api/analytics/listings/{id}/health/ml", tags=["F29 · Hạt"])
def health_ml(id: str, shop_id: str = CurrentShop):
    meta_args = dict(scope="listing", scope_id=id, database="vietcraft", mode="live")
    if not la_shop_live(shop_id):
        return insufficient("Cần cấu hình gian hàng trước khi xem sức khoẻ listing", build_meta(**meta_args))

    _kiem_quyen_listing(id, shop_id)

    result = score_listing(id)
    version = load_model()[1]["model_version"]
    if isinstance(result, str):
        return insufficient(result, build_meta(model_version=version, collection="orders", **meta_args))

    meta = build_meta(model_version=version, collection="orders", attributed_to_live_shop=True,
                      sample_size=result["peer_group"]["size"],
                      confidence="medium" if result["peer_group"]["type"] == "category" else "low", **meta_args)
    return ok(result, meta)
