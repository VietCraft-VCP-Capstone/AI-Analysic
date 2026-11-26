from datetime import timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1 import f29_intel
from app.api.v1._template import current_shop_id
from app.core.listing_intel import embedder, image_fetch, service
from tests.listing_intel.intel_support import PID, SHOP, URLS, env  # noqa: F401

BODY = {"title": "Áo thun nam cotton cổ tròn", "description": "Áo thun mềm mại", "tags": ["áo thun"],
        "materials": ["cotton"], "category": "Áo thun", "price": 199000, "image_urls": URLS}


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(f29_intel.router)
    app.dependency_overrides[current_shop_id] = lambda: SHOP
    return TestClient(app)


def test_preview_rejects_disallowed_url(env, client, monkeypatch):
    calls = []
    monkeypatch.setattr(image_fetch, "fetch", lambda *a, **k: calls.append(a))
    r = client.post("/api/analytics/listings/intel/preview", json={**BODY, "image_urls": ["https://evil.com/a.jpg"]})
    assert r.status_code in (400, 422) or r.json()["meta"]["status"] == "insufficient_data"
    assert calls == []


def test_preview_ok_without_writes(env, client):
    r = client.post("/api/analytics/listings/intel/preview", json=BODY)
    body = r.json()
    assert r.status_code == 200 and body["meta"]["status"] == "ok"
    assert body["meta"]["model_version"].startswith("li-") and body["data"]["score"] is not None
    assert "product_id" not in body["data"] and "degraded" not in body["meta"]
    assert env["listing_intel_scores"].docs == [] and env["listing_embeddings"].docs == []


def test_other_shop_forbidden(env, client):
    r = client.get("/api/analytics/listings/64c000000000000000000003/intel")
    assert r.status_code == 403


def test_detail_and_bad_date(env, client):
    r = client.get(f"/api/analytics/listings/{PID}/intel?date=2026-11-02")
    assert r.status_code == 200 and r.json()["data"]["product_id"] == PID
    assert client.get(f"/api/analytics/listings/{PID}/intel?date=hôm-nay").status_code == 400
    far = (service.today() + timedelta(days=731)).isoformat()
    assert client.get(f"/api/analytics/listings/{PID}/intel?date={far}").status_code == 400
    assert client.get(f"/api/analytics/listings/{PID}/intel?date=2020-01-01").status_code == 400


def test_degraded_when_embedder_missing(env, client, monkeypatch):
    monkeypatch.setattr(embedder, "available", lambda: False)
    body = client.post("/api/analytics/listings/intel/preview", json=BODY).json()
    assert body["meta"]["status"] == "ok" and "model" in body["meta"]["degraded"]


def test_list_route_registered_before_detail(env, client):
    r = client.get("/api/analytics/listings/intel")
    data = r.json()["data"]
    assert r.status_code == 200 and data["total"] == 2
    assert {i["product_id"] for i in data["items"]} == {PID, "64c000000000000000000002"}
    assert set(data["items"][0]["axes"]) == {"image", "text", "tags", "market", "trend"}


def test_calendar(env, client):
    r = client.get("/api/analytics/trends/calendar", params={"category": "Áo thun"})
    events = r.json()["data"]["events"]
    assert r.status_code == 200 and events
    assert all("fashion" in e["groups"] and e["date"] >= e["prep_start"] for e in events)


def test_bundle_missing_or_sklearn_mismatch_is_insufficient(env, client, monkeypatch, tmp_path):
    import json
    import shutil

    from tests.listing_intel.intel_support import bundle_dir

    monkeypatch.setenv("LI_BUNDLE_DIR", str(tmp_path / "none"))
    assert client.post("/api/analytics/listings/intel/preview", json=BODY).json()["meta"]["status"] == "insufficient_data"
    shutil.copytree(bundle_dir(), tmp_path / "old")
    meta = json.loads((tmp_path / "old/meta.json").read_text("utf-8"))
    (tmp_path / "old/meta.json").write_text(json.dumps({**meta, "sklearn": "0.0.1"}), "utf-8")
    monkeypatch.setenv("LI_BUNDLE_DIR", str(tmp_path / "old"))
    r = client.get(f"/api/analytics/listings/{PID}/intel")
    assert r.status_code == 200 and r.json()["meta"]["status"] == "insufficient_data" and r.json()["data"] is None
