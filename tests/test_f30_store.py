import pytest

from app.api.v1 import _f30_store as store
from tests.f29.fake_mongo import _FakeMongoClient


@pytest.fixture
def mart(monkeypatch):
    mart_db = _FakeMongoClient()["mart"]
    monkeypatch.setattr(store, "db", lambda: mart_db)
    return mart_db


def _ev(date: str, z: float) -> dict:
    return {"date": date, "metric": "views", "direction": "drop", "z": z,
            "expected": 10, "actual": 2, "severity": "high", "rule": "daily"}


def test_save_events_same_key_keeps_one_row(mart):
    store.save_events("s1", [_ev("2026-10-20", -2.5)], mode="live")
    store.save_events("s1", [_ev("2026-10-20", -3.5)], mode="live")
    rows = store.read_events("s1")
    assert len(rows) == 1
    assert rows[0]["z"] == -3.5
    assert rows[0]["event_date"] == "2026-10-20"


def test_latest_run_returns_newest_of_same_shop(mart):
    store.save_run("s1", "2026-10-19", "analysed", None, 40, {}, mode="live")
    store.save_run("s1", "2026-10-21", "skipped", "qua_ngan", 3, {}, mode="live")
    store.save_run("s2", "2026-10-22", "analysed", None, 40, {}, mode="live")
    run = store.latest_run("s1")
    assert run["run_date"] == "2026-10-21"
    assert run["skip_reason"] == "qua_ngan"


def test_read_events_filters_from_date_newest_first(mart):
    for d in ("2026-10-18", "2026-10-19", "2026-10-20"):
        store.save_events("s1", [_ev(d, -2.5)], mode="live")
    dates = [r["event_date"] for r in store.read_events("s1", from_date="2026-10-19")]
    assert dates == ["2026-10-20", "2026-10-19"]
