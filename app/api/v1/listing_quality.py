import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from typing import Optional
from fastapi import APIRouter
from pydantic import BaseModel

from app.api.v1._live import la_shop_live
from app.api.v1._template import CurrentShop, build_meta, forbidden, insufficient, not_found, ok
from app.api.v1.f29_health import _kiem_quyen_listing
from app.core.listing_quality.services.audit_service import AuditService

router = APIRouter()
TAG = "Listing Quality Audit"
NO_SHOP = "Cần cấu hình gian hàng trước khi xem kiểm toán chất lượng tin đăng."

class AuditRequestBody(BaseModel):
    force: Optional[bool] = False

def _meta(listing_id: str, version: str = AuditService.VERSION):
    return build_meta(
        model_version=version,
        scope="listing",
        scope_id=listing_id,
        database="vietcraft",
        collection="listing_quality_audits",
        mode="live",
        attributed_to_live_shop=True
    )

@router.get("/api/analytics/listings/{id}/quality", tags=[TAG])
def get_listing_quality(id: str, shop_id: str = CurrentShop):
    if not la_shop_live(shop_id):
        return insufficient(NO_SHOP, _meta(id))

    _kiem_quyen_listing(id, shop_id)

    svc = AuditService()
    res = svc.get_latest_audit(id)
    if res is None:
        not_found("listing")

    return ok(res.model_dump(), _meta(id, res.version))

@router.post("/api/analytics/listings/{id}/quality/audit", tags=[TAG])
def run_listing_quality_audit(id: str, body: Optional[AuditRequestBody] = None, shop_id: str = CurrentShop):
    if not la_shop_live(shop_id):
        return insufficient(NO_SHOP, _meta(id))

    _kiem_quyen_listing(id, shop_id)

    force = bool(body and body.force)
    svc = AuditService()
    res = svc.audit_listing(id, force=force)
    if res is None:
        not_found("listing")

    return ok(res.model_dump(), _meta(id, res.version))

@router.post("/api/analytics/listings/{id}/quality/recheck", tags=[TAG])
def recheck_listing_quality(id: str, shop_id: str = CurrentShop):
    if not la_shop_live(shop_id):
        return insufficient(NO_SHOP, _meta(id))

    _kiem_quyen_listing(id, shop_id)

    svc = AuditService()
    res = svc.recheck_listing(id)
    if res is None:
        not_found("listing")

    return ok(res.model_dump(), _meta(id, res.version))
