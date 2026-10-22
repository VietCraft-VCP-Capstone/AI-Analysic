import logging
from datetime import date
from typing import List, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field, field_validator

from app.api.v1._live import la_shop_live
from app.api.v1._template import CurrentShop, build_meta, insufficient, invalid_param, not_found, ok
from app.api.v1.f29_health import _kiem_quyen_listing
from app.core.listing_intel import embedder, fusion, image_fetch, live_data, service
from app.core.listing_intel.types import ListingInput

router = APIRouter()
logger = logging.getLogger(__name__)
TAG = "F29 · Listing Intelligence"
NO_SHOP = "Cần cấu hình gian hàng trước khi xem phân tích listing"
NO_MODEL = "Model phân tích listing chưa sẵn sàng, cần chạy huấn luyện trước"
DEGRADED = "Thiếu model nhúng ảnh và chữ, trục ảnh, thị trường và khớp từ khoá đang chạy ở chế độ rút gọn"
MAX_DAYS = 730


class IntelPreviewBody(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=5000)
    tags: List[str] = Field(default_factory=list, max_length=20)
    materials: List[str] = Field(default_factory=list, max_length=5)
    category: str = Field(default="", max_length=100)
    price: Optional[float] = Field(default=None, ge=0, le=1e10)
    image_urls: List[str] = Field(default_factory=list, max_length=8)

    @field_validator("tags", "materials")
    @classmethod
    def _short(cls, v):
        if any(len(x) > 40 for x in v):
            raise ValueError("mỗi mục tối đa 40 ký tự")
        return v

    @field_validator("image_urls")
    @classmethod
    def _allowed(cls, v):
        if not all(image_fetch.allowed(u) for u in v):
            raise ValueError("ảnh chỉ nhận từ res.cloudinary.com hoặc salt.tikicdn.com qua https")
        return v


def _meta(scope: str, scope_id, version: str = "unknown", **kw):
    return build_meta(model_version=version, scope=scope, scope_id=scope_id, database="vietcraft",
                      collection="listing_intel_scores", mode="live", **kw)


def _run(fn, scope: str, scope_id):
    try:
        version = fusion.load_bundle().meta["model_version"]
    except (FileNotFoundError, RuntimeError):
        return insufficient(NO_MODEL, _meta(scope, scope_id))
    except Exception:
        logger.exception("listing intel model bundle failed to load")
        return insufficient(NO_MODEL, _meta(scope, scope_id))
    meta = _meta(scope, scope_id, version, attributed_to_live_shop=scope != "draft")
    if not embedder.available():
        meta["degraded"] = DEGRADED
    return ok(fn(), meta)


def _day(value: Optional[str]) -> date:
    if not value:
        return service.today()
    try:
        day = date.fromisoformat(value)
    except ValueError:
        invalid_param("date", "YYYY-MM-DD")
    if abs((day - service.today()).days) > MAX_DAYS:
        invalid_param("date", f"YYYY-MM-DD, cách hôm nay tối đa {MAX_DAYS} ngày")
    return day


@router.get("/api/analytics/listings/intel", tags=[TAG])
def intel_list(shop_id: str = CurrentShop):
    if not la_shop_live(shop_id):
        return insufficient(NO_SHOP, _meta("shop", shop_id))
    return _run(lambda: service.shop_summary(shop_id), "shop", shop_id)


@router.get("/api/analytics/listings/{id}/intel", tags=[TAG])
def intel_detail(id: str, date: Optional[str] = None, shop_id: str = CurrentShop):
    if not la_shop_live(shop_id):
        return insufficient(NO_SHOP, _meta("listing", id))
    at = _day(date)
    _kiem_quyen_listing(id, shop_id)
    inp = live_data.load_listing(id)
    if inp is None:
        not_found("listing")
    return _run(lambda: service.analyze(inp, at, persist=at == service.today()), "listing", id)


@router.post("/api/analytics/listings/intel/preview", tags=[TAG])
def intel_preview(body: IntelPreviewBody, shop_id: str = CurrentShop):
    if not la_shop_live(shop_id):
        return insufficient(NO_SHOP, _meta("draft", None))
    inp = ListingInput(**body.model_dump(), group=live_data.group_of(body.category), seller_id=shop_id)
    return _run(lambda: service.analyze(inp, service.today(), persist=False, store_embeddings=False), "draft", None)


@router.get("/api/analytics/trends/calendar", tags=[TAG])
def trend_calendar(category: Optional[str] = None, shop_id: str = CurrentShop):
    if not la_shop_live(shop_id):
        return insufficient(NO_SHOP, _meta("shop", shop_id))
    return _run(lambda: service.calendar(shop_id, category), "shop", shop_id)
