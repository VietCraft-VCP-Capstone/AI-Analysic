import pytest
from fastapi.testclient import TestClient

from app.api.v1 import f29_health
from app.core.f29 import image_check
from app.core.f29.calculator import HealthScoreCalculator
from app.core.f29.constants import MODEL_VERSION
from tests.f29.fake_mongo import make_calculator
from tests.f29.samples import PRODUCT_ID, base_product, with_id

SHOP_ID = "64b000000000000000000001"
PRICED = [{"is_active": True, "stock_quantity": 10, "retail_price": "150000", "base_cost": "80000"}]


def _priced(product):
    return [{**v, "product_id": product["_id"]} for v in PRICED]
SAMPLE = {
    "product_id": PRODUCT_ID, "score": 71.5, "status": "needs_improvement",
    "axes": {"image": 83.3, "description": 45.6, "tags": 100.0, "review": 0.0, "price": 42.1},
    "axes_missing": ["review"], "breakdown": [], "todos": [], "warnings": [],
    "model_version": MODEL_VERSION, "basis": {},
}


@pytest.fixture
def client(monkeypatch):
    from app.main import app
    monkeypatch.setenv("DEV_TRUST_SHOP_HEADER", "1")
    monkeypatch.setenv("DEV_SHOP_ID", "")
    monkeypatch.setattr(f29_health, "la_shop_live", lambda shop: True)
    monkeypatch.setattr(f29_health, "_kiem_quyen_listing", lambda id, shop: None)
    monkeypatch.setattr(f29_health, "HealthScoreCalculator", make_calculator)
    return TestClient(app, raise_server_exceptions=False)


def _get(client):
    return client.get(f"/api/analytics/listings/{PRODUCT_ID}/health", headers={"X-Debug-Shop-Id": SHOP_ID})


def test_returns_health_score(monkeypatch, client):
    monkeypatch.setattr(HealthScoreCalculator, "calculate", lambda self, pid, **kw: SAMPLE)
    body = _get(client).json()
    assert body["data"]["score"] == 71.5
    assert body["meta"]["status"] == "ok"
    assert body["meta"]["model_version"] == MODEL_VERSION


def test_cache_miss_get_uses_full_image_budget(monkeypatch, client):
    seen = {}

    def spy(self, pid, image_budget=20.0):
        seen["budget"] = image_budget
        return SAMPLE

    monkeypatch.setattr(HealthScoreCalculator, "calculate", spy)
    _get(client)
    assert seen["budget"] == 20.0


def test_no_weights_returns_insufficient(monkeypatch, client):
    monkeypatch.setattr(HealthScoreCalculator, "calculate", lambda self, pid, **kw: {"error": "no_weights"})
    body = _get(client).json()
    assert body["data"] is None
    assert body["meta"]["status"] == "insufficient_data"
    assert body["meta"]["reason"] == "Độ hoàn thiện trang sản phẩm đang được cập nhật, vui lòng thử lại sau."


def test_unknown_listing_404(monkeypatch, client):
    monkeypatch.setattr(HealthScoreCalculator, "calculate", lambda self, pid, **kw: None)
    assert _get(client).status_code == 404


def test_sync_health_score(monkeypatch, client):
    monkeypatch.setattr(HealthScoreCalculator, "calculate", lambda self, pid, **kw: SAMPLE)
    saved = []
    monkeypatch.setattr(HealthScoreCalculator, "save", lambda self, res: saved.append(res))
    r = client.post(f"/api/analytics/listings/{PRODUCT_ID}/sync", headers={"X-Debug-Shop-Id": SHOP_ID})
    assert r.status_code == 200
    body = r.json()
    assert body["data"]["status"] == "synced"
    assert body["data"]["score"] == 71.5
    assert len(saved) == 1


def _shared(monkeypatch, **seed):
    calc = make_calculator(**seed)
    monkeypatch.setattr(f29_health, "HealthScoreCalculator", lambda: calc)
    return calc


def _boom(*args, **kwargs):
    raise AssertionError("must not recompute")


def test_get_returns_stored_doc_without_recomputing(monkeypatch, client):
    product = with_id(base_product())
    calc = _shared(monkeypatch, products=[product], product_variants=_priced(product))
    first = calc.calculate(PRODUCT_ID)
    calc.save(first)
    monkeypatch.setattr(image_check, "analyze", _boom)
    monkeypatch.setattr(HealthScoreCalculator, "calculate", _boom)
    body = _get(client).json()
    assert body["data"]["score"] == first["score"] and body["data"]["product_id"] == PRODUCT_ID
    assert body["meta"]["status"] == "ok"


def test_get_recomputes_and_saves_when_images_change(monkeypatch, client):
    product = with_id(base_product())
    calc = _shared(monkeypatch, products=[product], product_variants=_priced(product))
    calc.save(calc.calculate(PRODUCT_ID))
    old_hash = calc.live_db["listing_health_scores"].docs[0]["inputs_hash"]
    calc.live_db["products"].docs[0]["images"] = ["new.jpg"]
    assert _get(client).json()["data"]["product_id"] == PRODUCT_ID
    assert calc.live_db["listing_health_scores"].docs[0]["inputs_hash"] != old_hash
