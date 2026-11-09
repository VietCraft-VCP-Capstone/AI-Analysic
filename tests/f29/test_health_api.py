import pytest
from fastapi.testclient import TestClient

from app.api.v1 import f29_health
from app.core.f29.calculator import HealthScoreCalculator
from tests.f29.fake_mongo import make_calculator
from tests.f29.samples import PRODUCT_ID

SHOP_ID = "64b000000000000000000001"
SAMPLE = {
    "product_id": PRODUCT_ID, "score": 71.5, "status": "needs_improvement",
    "axes": {"image": 83.3, "description": 45.6, "tags": 100.0, "review": 0.0, "price": 42.1},
    "axes_missing": ["review"], "breakdown": [], "todos": [], "warnings": [],
    "model_version": "health-2.2", "basis": {},
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
    monkeypatch.setattr(HealthScoreCalculator, "calculate", lambda self, pid: SAMPLE)
    body = _get(client).json()
    assert body["data"]["score"] == 71.5
    assert body["meta"]["status"] == "ok"
    assert body["meta"]["model_version"] == "health-2.2"


def test_no_weights_returns_insufficient(monkeypatch, client):
    monkeypatch.setattr(HealthScoreCalculator, "calculate", lambda self, pid: {"error": "no_weights"})
    body = _get(client).json()
    assert body["data"] is None
    assert body["meta"]["status"] == "insufficient_data"
    assert body["meta"]["reason"] == "Điểm tối ưu sản phẩm đang được cập nhật, vui lòng thử lại sau."


def test_unknown_listing_404(monkeypatch, client):
    monkeypatch.setattr(HealthScoreCalculator, "calculate", lambda self, pid: None)
    assert _get(client).status_code == 404


def test_sync_health_score(monkeypatch, client):
    monkeypatch.setattr(HealthScoreCalculator, "calculate", lambda self, pid: SAMPLE)
    saved = []
    monkeypatch.setattr(HealthScoreCalculator, "save", lambda self, res: saved.append(res))
    r = client.post(f"/api/analytics/listings/{PRODUCT_ID}/sync", headers={"X-Debug-Shop-Id": SHOP_ID})
    assert r.status_code == 200
    body = r.json()
    assert body["data"]["status"] == "synced"
    assert body["data"]["score"] == 71.5
    assert len(saved) == 1

