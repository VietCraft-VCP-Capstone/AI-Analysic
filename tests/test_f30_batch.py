from datetime import datetime

import numpy as np
import pytest
from bson import ObjectId
from fastapi.testclient import TestClient

from app.api.v1 import _f30_store as store
from app.api.v1 import _live_data, f30_internal
from app.api.v1._live_data import GIO_VN, cac_ngay, oid
from app.core import f30_batch
from app.core.f30_batch import analyse_shop
from app.main import app
from tests.f29.fake_mongo import _FakeMongoClient

RUN = "2026-10-20"
DAYS = cac_ngay(120, RUN)
SHOP = ObjectId()
PID = ObjectId()


def _data(revenue, orders, views=None):
    n = len(DAYS)
    v = np.full(n, 20.0) if views is None else np.array(views, dtype=float)
    return {"titles": {str(PID): "Áo thun"},
            "views": {str(PID): v},
            "revenue": {str(PID): np.array(revenue, dtype=float)},
            "orders": {str(PID): np.array(orders, dtype=float)}}


def _run_t(data):
    return analyse_shop(str(SHOP), data, DAYS, [len(DAYS) - 1])


def test_shop_deu_dat_khong_co_su_kien():
    events, info = _run_t(_data([100_000.0] * 120, [1.0] * 120))
    assert info["status"] == "analysed" and events == []
    assert info["metrics"]["revenue"]["expected"] == 100_000


def test_shop_ngung_ban_7_ngay_bao_zero_run():
    rev = [100_000.0] * 113 + [0.0] * 7
    events, info = _run_t(_data(rev, [1.0] * 113 + [0.0] * 7))
    rev_ev = [e for e in events if e["metric"] == "revenue"]
    assert rev_ev and rev_ev[0]["rule"] == "zero_run" and rev_ev[0]["direction"] == "drop"
    assert rev_ev[0]["date"] == RUN and rev_ev[0]["top_listings"][0]["listing_id"] == f"live_{PID}"
    assert info["metrics"]["revenue"]["actual"] == 0


def test_shop_it_lich_su_bi_bo_qua():
    rev = [0.0] * 110 + [100_000.0] * 10
    events, info = _run_t(_data(rev, [0.0] * 110 + [1.0] * 10, views=[0.0] * 110 + [5.0] * 10))
    assert events == [] and info == {"status": "skipped", "skip_reason": "qua_ngan",
                                     "history_days": 10, "metrics": {}}


def test_shop_khong_san_pham():
    data = {**_data([0.0] * 120, [0.0] * 120), "titles": {}}
    _, info = _run_t(data)
    assert info["skip_reason"] == "khong_co_san_pham"


@pytest.fixture
def live_db(monkeypatch):
    fake = _FakeMongoClient()["vietcraft"]
    monkeypatch.setattr(_live_data, "db_live", lambda: fake)
    mart = _FakeMongoClient()["mart"]
    monkeypatch.setattr(store, "db", lambda: mart)
    fake["products"].seed([{"_id": PID, "shop_id": SHOP, "title": "Áo thun", "status": "PUBLISHED"}])
    fake["orders"].seed([{"_id": ObjectId(), "shop_id": oid(str(SHOP)), "items": [
        {"product_id": PID, "quantity": 1, "retail_price": 100000.0}],
        "created_at": datetime.fromisoformat(d).replace(hour=12, tzinfo=GIO_VN),
        "payment_status": "PAID", "order_status": "DELIVERED"} for d in DAYS[:113]])
    return mart


def test_run_live_luu_su_kien_va_run(live_db):
    out = f30_batch.run_live(RUN)
    assert out["shops_total"] == 1 and out["shops_analysed"] == 1
    assert [(e["metric"], e["rule"], e["shop_id"]) for e in out["events"]] == \
        [("revenue", "zero_run", str(SHOP))]
    assert store.latest_run(str(SHOP))["status"] == "analysed"
    assert len(store.read_events(str(SHOP))) == 1


@pytest.fixture
def gateway(monkeypatch):
    monkeypatch.setenv("AI_GATEWAY_SECRET", "bi-mat")
    monkeypatch.setattr(f30_internal, "run_live",
                        lambda run_date, backfill_days: {"run_date": run_date, "events": []})
    return TestClient(app, raise_server_exceptions=False)


def test_endpoint_thieu_hoac_sai_secret_bi_401(gateway):
    assert gateway.post("/api/internal/f30/run", json={}).status_code == 401
    bad = {"X-Gateway-Secret": "sai"}
    assert gateway.post("/api/internal/f30/run", json={}, headers=bad).status_code == 401


def test_endpoint_dung_secret_chay_va_kiem_tham_so(gateway):
    good = {"X-Gateway-Secret": "bi-mat"}
    r = gateway.post("/api/internal/f30/run", json={"run_date": RUN}, headers=good)
    assert r.status_code == 200 and r.json()["data"]["run_date"] == RUN
    assert gateway.post("/api/internal/f30/run", json={"run_date": "2026-13-45"},
                        headers=good).status_code == 400
    assert gateway.post("/api/internal/f30/run", json={"backfill_days": 91},
                        headers=good).status_code == 400
