import json

import pytest
from bson import ObjectId
from fastapi import HTTPException

from app.api.v1 import _f30_store as store
from app.api.v1 import f30_alerts
from app.api.v1._f30_store import save_events, save_run
from app.api.v1.f30_alerts import alerts
from tests.f29.fake_mongo import _FakeMongoClient

SHOP = str(ObjectId())
DEN = "2026-10-20"
MUC = {"id", "date", "metric", "direction", "rule", "z", "expected", "actual", "change_pct",
       "severity", "calendar_sensitive", "confidence", "top_listings"}


@pytest.fixture
def db(monkeypatch):
    fake = _FakeMongoClient()["vietcraft"]
    monkeypatch.setattr(store, "db", lambda: fake)
    monkeypatch.setattr(f30_alerts, "db", lambda: fake)
    return fake


def _su_kien(shop=SHOP):
    return {"id": f"{shop}:revenue:{DEN}", "date": DEN, "metric": "revenue", "direction": "drop",
            "rule": "daily", "z": -2.84, "expected": 1940000, "actual": 520000, "change_pct": -73.2,
            "severity": "low", "calendar_sensitive": False, "confidence": "ok", "top_listings": []}


def test_shop_sach_da_chay_khong_co_canh_bao(db):
    save_run(SHOP, DEN, "analysed", None, 120, {}, mode="live")
    r = alerts(shop_id=SHOP, period="90d")
    assert r["data"]["shop_was_analysed"] is True and r["data"]["alerts"] == []
    assert r["meta"]["source"]["mode"] == "live" and r["meta"]["model_version"]


def test_chua_chay_bao_ly_do(db):
    r = alerts(shop_id=SHOP, period="90d")
    assert r["data"]["shop_was_analysed"] is False and r["data"]["skip_reason"] == "chua_chay"
    assert r["data"]["limitation"]


def test_canh_bao_dung_hop_dong(db):
    save_run(SHOP, DEN, "analysed", None, 120, {}, mode="live")
    save_events(SHOP, [{**_su_kien(), "mode": "live"}], mode="live")
    item = alerts(shop_id=SHOP, period="30d")["data"]["alerts"][0]
    assert set(item) == MUC and item["date"] == DEN


def test_period_sai_tra_400(db):
    with pytest.raises(HTTPException) as e:
        alerts(shop_id=SHOP, period="bad")
    assert e.value.status_code == 400


def test_khong_con_nguong_cu(db):
    save_run(SHOP, DEN, "analysed", None, 120, {}, mode="live")
    r = alerts(shop_id=SHOP, period="90d")
    assert "7,38" not in json.dumps(r, ensure_ascii=False)
    assert r["data"]["threshold"]["z"] == 2.0


def test_mart_mau_rong_tra_503(db):
    with pytest.raises(HTTPException) as e:
        alerts(shop_id="shp_00017", period="90d")
    assert e.value.status_code == 503
