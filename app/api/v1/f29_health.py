from typing import List, Literal, Optional

from fastapi import APIRouter
from bson import ObjectId
from pydantic import BaseModel, Field

from app.api.v1._live import db_live, la_shop_live
from app.api.v1._template import CurrentShop, forbidden, insufficient, not_found, ok, build_meta
from app.core.f29 import feedback
from app.core.f29.score.calculator import HealthScoreCalculator
from app.core.f29.constants import MODEL_VERSION
from app.core.f29.score import draft
from app.core.f29.score.preview import preview_health

router = APIRouter()
NO_SHOP = "Cần cấu hình gian hàng trước khi xem độ hoàn thiện trang sản phẩm"
NO_WEIGHTS = "Độ hoàn thiện trang sản phẩm đang được cập nhật, vui lòng thử lại sau."
NO_SAVE_FEEDBACK = "Chưa lưu được phản hồi, vui lòng thử lại."


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


DRAFT_IMAGE_BUDGET = 8.0


class HealthDraftBody(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=5000)
    tags: List[str] = Field(default_factory=list, max_length=20)
    materials: List[str] = Field(default_factory=list, max_length=20)
    category: str = Field(default="", max_length=80)
    price: Optional[float] = Field(default=None, ge=0, le=1e10)
    image_urls: List[str] = Field(default_factory=list, max_length=8)


class HealthPreviewBody(BaseModel):
    n_images: Optional[float] = Field(default=None, ge=0, le=50)
    description_length: Optional[float] = Field(default=None, ge=0, le=20000)
    n_tags: Optional[float] = Field(default=None, ge=0, le=50)
    price: Optional[float] = Field(default=None, ge=0, le=1e10)


class HealthFeedbackBody(BaseModel):
    image_url: str = Field(min_length=1, max_length=2000)
    verdict: Literal["ai_wrong", "ai_right"]


def _feedback(id: str) -> list:
    try:
        return feedback.of_product(id)
    except Exception as e:
        print(f"[f29_health feedback] {type(e).__name__}: {e}", flush=True)
        return []


def _image_of(result: Optional[dict], image_url: str) -> Optional[dict]:
    rows = [r for r in (result or {}).get("factors") or [] if r.get("key") == "image"]
    images = (rows[0].get("evidence") or {}).get("images", []) if rows else []
    return next((img for img in images if img.get("url") == image_url), None)


@router.get("/api/analytics/listings/{id}/health", tags=["F29 · Hạt"])
def health_score(id: str, shop_id: str = CurrentShop):
    meta_args = dict(scope="listing", scope_id=id, database="vietcraft", mode="live")
    if not la_shop_live(shop_id):
        return insufficient(NO_SHOP, build_meta(**meta_args))

    _kiem_quyen_listing(id, shop_id)
    id = str(ObjectId(id))

    try:
        calc = HealthScoreCalculator()
        result = calc.stored_result(id)
        if result is None:
            result = calc.calculate(id)
            if result and "error" not in result:
                try:
                    calc.save(result)
                except Exception as e:
                    print(f"[f29_health save] {type(e).__name__}: {e}", flush=True)
    except Exception as e:
        print(f"[f29_health] {type(e).__name__}: {e}", flush=True)
        return insufficient("Hệ thống chưa thể tính điểm cho sản phẩm này, vui lòng thử lại sau.", build_meta(**meta_args))
    if result is None:
        not_found("listing")
    if "error" in result:
        return insufficient(NO_WEIGHTS, build_meta(**meta_args))

    meta = build_meta(model_version=MODEL_VERSION, collection="products", attributed_to_live_shop=True, **meta_args)
    return ok({**result, "feedback": _feedback(id)}, meta)


@router.post("/api/analytics/listings/{id}/health/feedback", tags=["F29 · Hạt"])
def health_feedback(id: str, body: HealthFeedbackBody, shop_id: str = CurrentShop):
    meta_args = dict(scope="listing", scope_id=id, database="vietcraft", mode="live")
    if not la_shop_live(shop_id):
        return insufficient(NO_SHOP, build_meta(**meta_args))

    _kiem_quyen_listing(id, shop_id)
    id = str(ObjectId(id))

    try:
        calc = HealthScoreCalculator()
        result = calc.stored_result(id)
        if result is None or "error" in result:
            result = calc.calculate(id)
    except Exception as e:
        print(f"[f29_health feedback] {type(e).__name__}: {e}", flush=True)
        return insufficient(NO_SAVE_FEEDBACK, build_meta(**meta_args))
    img = _image_of(result, body.image_url)
    if img is None:
        not_found("image")

    try:
        feedback.save(id, shop_id, body.image_url, body.verdict, img.get("ai"))
    except Exception as e:
        print(f"[f29_health feedback save] {type(e).__name__}: {e}", flush=True)
        return insufficient(NO_SAVE_FEEDBACK, build_meta(**meta_args))

    meta = build_meta(model_version=MODEL_VERSION, collection="f29_feedback", attributed_to_live_shop=True, **meta_args)
    return ok({"image_url": body.image_url, "verdict": body.verdict}, meta)


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


@router.post("/api/analytics/listings/{id}/sync", tags=["F29 · Hạt"])
def sync_listing_health(id: str, shop_id: str = CurrentShop):
    meta_args = dict(scope="listing", scope_id=id, database="vietcraft", mode="live")
    if not la_shop_live(shop_id):
        return insufficient(NO_SHOP, build_meta(**meta_args))

    _kiem_quyen_listing(id, shop_id)

    try:
        calc = HealthScoreCalculator()
        result = calc.calculate(id)
        if result and "error" not in result:
            try:
                calc.save(result)
            except Exception as e:
                print(f"[f29_health sync save] {type(e).__name__}: {e}", flush=True)
                return insufficient("Đã tính điểm nhưng chưa lưu được, vui lòng thử lại.", build_meta(**meta_args))
            meta = build_meta(model_version=MODEL_VERSION, collection="products", attributed_to_live_shop=True, **meta_args)
            return ok({"status": "synced", "product_id": id, "score": result.get("score")}, meta)
    except Exception as e:
        print(f"[f29_health sync] {type(e).__name__}: {e}", flush=True)
        return insufficient("Hệ thống chưa thể cập nhật điểm cho sản phẩm này", build_meta(**meta_args))

    if result is None:
        not_found("listing")
    if "error" in result:
        return insufficient(NO_WEIGHTS, build_meta(**meta_args))
    return insufficient("Không thể tính độ hoàn thiện trang sản phẩm", build_meta(**meta_args))


@router.post("/api/analytics/listings/health/draft", tags=["F29 · Hạt"])
def health_draft(body: HealthDraftBody, shop_id: str = CurrentShop):
    meta_args = dict(scope="draft", scope_id=None, database="vietcraft", mode="live")
    if not la_shop_live(shop_id):
        return insufficient(NO_SHOP, build_meta(**meta_args))
    product = draft.product(body.title, body.description, body.tags, body.materials, body.category,
                            body.image_urls, shop_id)
    try:
        result = HealthScoreCalculator().calculate_draft(product, draft.variants(body.price), DRAFT_IMAGE_BUDGET)
    except Exception as e:
        print(f"[f29_health draft] {type(e).__name__}: {e}", flush=True)
        return insufficient("Hệ thống chưa thể chấm thử bản nháp, vui lòng thử lại sau.", build_meta(**meta_args))
    if "error" in result:
        return insufficient(NO_WEIGHTS, build_meta(**meta_args))
    meta = build_meta(model_version=result["model_version"], collection="products",
                      attributed_to_live_shop=True, **meta_args)
    return ok(result, meta)
