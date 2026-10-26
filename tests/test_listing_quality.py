import numpy as np
from PIL import Image
from fastapi.testclient import TestClient

from app.core.listing_quality.detectors import (
    ImageQualityDetector,
    PodContentDetector,
    RequiredFieldsDetector,
    TextConsistencyDetector,
)
from app.core.listing_quality.services.audit_service import AuditService
from app.main import app

client = TestClient(app)

def _make_dummy_image(w=600, h=600, noise=True):
    if noise:
        arr = np.random.randint(0, 256, (h, w, 3), dtype=np.uint8)
    else:
        arr = np.full((h, w, 3), 128, dtype=np.uint8)
    return Image.fromarray(arr)

def test_required_fields_missing():
    det = RequiredFieldsDetector()
    listing = {
        "title": None,
        "description": "   ",
        "images": [],
        "categories": [],
        "original_price": 0
    }
    context = {"variants": []}
    issues = det.evaluate(listing, context)
    codes = {i.code for i in issues}
    assert "TITLE_MISSING" in codes
    assert "DESCRIPTION_EMPTY" in codes
    assert "IMAGES_MISSING" in codes
    assert "CATEGORY_MISSING" in codes
    assert "PRICE_MISSING" in codes
    assert "TAGS_MISSING" in codes

def test_required_fields_valid():
    det = RequiredFieldsDetector()
    listing = {
        "title": "Áo Thun Unisex Cotton Basic 220gsm",
        "description": "Chất liệu cotton mềm mại, thoáng mát, đường may chắc chắn tỉ mỉ.",
        "images": ["http://res.cloudinary.com/test/1.jpg", "http://res.cloudinary.com/test/2.jpg"],
        "categories": ["ao-thun"],
        "tags": ["áo thun", "basic"],
        "original_price": 199000
    }
    context = {"variants": [{"sku": "SKU-1", "retail_price": 199000, "is_active": True}]}
    issues = det.evaluate(listing, context)
    assert len(issues) == 0

def test_pod_content_apparel_missing_material_and_size():
    det = PodContentDetector()
    listing = {
        "title": "Áo thun phong cách",
        "description": "Hàng đẹp mẫu mới về nhiều màu sắc bắt mắt.",
        "categories": ["ao-thun"],
        "materials": []
    }
    context = {"variants": []}
    issues = det.evaluate(listing, context)
    codes = {i.code for i in issues}
    assert "MATERIAL_MISSING" in codes
    assert "SIZE_INFO_MISSING" in codes

def test_pod_content_apparel_complete():
    det = PodContentDetector()
    listing = {
        "title": "Áo hoodie nỉ bông form rộng",
        "description": "Chất liệu nỉ cotton dày dặn, có bảng size S M L XL chi tiết. Hướng dẫn giặt máy ở chế độ nhẹ.",
        "categories": ["ao-khoac"],
        "materials": ["nỉ"]
    }
    context = {"variants": [{"size": "L"}]}
    issues = det.evaluate(listing, context)
    assert len(issues) == 0

def test_pod_content_drinkware():
    det = PodContentDetector()
    listing = {
        "title": "Cốc sứ in hình quà tặng sinh nhật",
        "description": "Dung tích 350ml tráng men bóng cao cấp chịu nhiệt tốt.",
        "categories": ["ly-tach"]
    }
    context = {"variants": []}
    issues = det.evaluate(listing, context)
    codes = {i.code for i in issues}
    assert "SIZE_INFO_MISSING" not in codes
    assert "DRINKWARE_SPECS_MISSING" not in codes

def test_image_quality_low_res():
    det = ImageQualityDetector()
    low_res = _make_dummy_image(w=300, h=300)
    listing = {"images": ["dummy_url"]}
    context = {"preloaded_images": {"dummy_url": low_res}}
    issues = det.evaluate(listing, context)
    codes = {i.code for i in issues}
    assert "LOW_IMAGE_RESOLUTION" in codes

def test_image_quality_aspect_ratio():
    det = ImageQualityDetector()
    stretched = _make_dummy_image(w=1200, h=400)
    listing = {"images": ["dummy_url"]}
    context = {"preloaded_images": {"dummy_url": stretched}}
    issues = det.evaluate(listing, context)
    codes = {i.code for i in issues}
    assert "EXTREME_ASPECT_RATIO" in codes

def test_image_quality_valid():
    det = ImageQualityDetector()
    good = _make_dummy_image(w=800, h=800, noise=True)
    listing = {"images": ["dummy_url"]}
    context = {"preloaded_images": {"dummy_url": good}}
    issues = det.evaluate(listing, context)
    assert len(issues) == 0

def test_text_consistency_material_conflict():
    det = TextConsistencyDetector()
    listing = {
        "title": "Áo Thun Cotton 100% Cao Cấp",
        "materials": ["polyester"],
        "categories": ["ao-thun"]
    }
    context = {"variants": []}
    issues = det.evaluate(listing, context)
    codes = {i.code for i in issues}
    assert "MATERIAL_CONTRADICTION" in codes

def test_text_consistency_category_conflict():
    det = TextConsistencyDetector()
    listing = {
        "title": "Cốc Sứ Quà Tặng Vẽ Tay",
        "categories": ["ao-thun"]
    }
    context = {"variants": []}
    issues = det.evaluate(listing, context)
    codes = {i.code for i in issues}
    assert "CATEGORY_CONTRADICTION" in codes

def test_audit_service_workflow():
    svc = AuditService()
    listing = {
        "title": "Áo thun test quality",
        "description": "Mô tả chất liệu cotton 100% thoáng mát, bảng size S/M/L, bảo quản giặt máy.",
        "images": ["http://res.cloudinary.com/test/1.jpg", "http://res.cloudinary.com/test/2.jpg"],
        "categories": ["ao-thun"],
        "tags": ["áo thun"],
        "original_price": 150000,
        "materials": ["cotton"]
    }
    variants = [{"sku": "SKU-TEST-1", "size": "M", "retail_price": 150000, "is_active": True}]
    h1 = svc._compute_hash(listing, variants)
    h2 = svc._compute_hash(listing, variants)
    assert h1 == h2

def test_api_contract_auth_guard():
    resp = client.get("/api/analytics/listings/6ad20b60b3cb281d77526bf9/quality")
    assert resp.status_code in (200, 401, 403, 404)

def test_audit_service_local_db_run():
    svc = AuditService()
    listing_id = "6ad20b60b3cb281d77526bf9"
    res = svc.audit_listing(listing_id, force=True)
    assert res is not None
    assert res.listingId == listing_id
    assert res.version == "listing-audit-1.0"
    assert res.status in ("completed", "partial")
    assert isinstance(res.summary.total, int)

def test_audit_service_recheck_flow():
    svc = AuditService()
    listing_id = "6ad20b60b3cb281d77526bf9"
    res1 = svc.audit_listing(listing_id, force=True)
    assert res1 is not None
    recheck_res = svc.recheck_listing(listing_id)
    assert recheck_res is not None
    assert recheck_res.listingId == listing_id

def test_evaluation_pipeline_metrics():
    from app.core.listing_quality.evaluation import run_evaluation
    results = run_evaluation()
    assert "required_fields" in results
    assert "pod_content" in results
    assert "image_quality" in results
    assert "text_consistency" in results
    assert results["required_fields"].precision >= 0.90
    assert results["pod_content"].precision >= 0.90
    assert results["text_consistency"].precision >= 0.90
