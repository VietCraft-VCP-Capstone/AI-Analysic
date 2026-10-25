from datetime import datetime, timezone

from bson import ObjectId

from app.core import f29_scheduler
from app.core.f29.calculator import HealthScoreCalculator
from tests.f29.fake_mongo import make_calculator
from tests.f29.samples import NOW, PRODUCT_ID, base_product, with_id

OLD = datetime(2026, 10, 21, tzinfo=timezone.utc)
NEW = datetime(2026, 10, 22, tzinfo=timezone.utc)


def _db(*docs):
    return make_calculator(listing_health_scores=list(docs)).live_db


def _doc(version, when):
    return {"product_id": ObjectId(PRODUCT_ID), "computed_at": when, "model_version": version, "score": 50.0}


def test_needs_full_rescan_empty_db():
    assert f29_scheduler.needs_full_rescan(_db()) is True


def test_needs_full_rescan_when_latest_is_v1():
    assert f29_scheduler.needs_full_rescan(_db(_doc("health-1.0", NEW))) is True


def test_no_rescan_when_latest_is_v2():
    assert f29_scheduler.needs_full_rescan(_db(_doc("health-1.0", OLD), _doc("health-2.2", NEW))) is False


def test_recalculate_skips_error_result(monkeypatch):
    saved = []
    monkeypatch.setattr(HealthScoreCalculator, "calculate", lambda self, pid: {"error": "no_weights"})
    monkeypatch.setattr(HealthScoreCalculator, "save", lambda self, result: saved.append(result))
    assert f29_scheduler._recalculate_and_save([PRODUCT_ID], make_calculator()) == (0, True, [])
    assert saved == []


def test_scan_keeps_watermark_when_weights_missing(monkeypatch):
    calc = make_calculator(products=[with_id(base_product(updated_at=NOW))])
    db = calc.live_db
    monkeypatch.setattr(f29_scheduler, "db_live", lambda: db)
    monkeypatch.setattr(f29_scheduler, "HealthScoreCalculator", lambda: calc)
    monkeypatch.setattr(HealthScoreCalculator, "calculate", lambda self, pid: {"error": "no_weights"})
    f29_scheduler.scan_changed_products()
    assert db[f29_scheduler.STATE_COLLECTION].docs == []
