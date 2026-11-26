from datetime import datetime, timezone

from bson import ObjectId

from app.core import f29_scheduler
from app.core.f29.calculator import HealthScoreCalculator
from app.core.f29.constants import MODEL_VERSION
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


def _state(version):
    db = _db()
    db[f29_scheduler.STATE_COLLECTION].seed([{"_id": f29_scheduler.STATE_ID_NIGHTLY, "model_version": version}])
    return db


def test_no_rescan_after_full_scan_on_current_version():
    assert f29_scheduler.needs_full_rescan(_state(MODEL_VERSION)) is False


def test_rescan_when_full_scan_was_previous_version():
    assert f29_scheduler.needs_full_rescan(_state("health-2.2")) is True


def test_one_new_doc_does_not_skip_rescan():
    assert f29_scheduler.needs_full_rescan(_db(_doc("health-2.2", OLD), _doc(MODEL_VERSION, NEW))) is True


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
    db[f29_scheduler.STATE_COLLECTION].seed([{"_id": f29_scheduler.STATE_ID_NIGHTLY, "model_version": MODEL_VERSION}])
    f29_scheduler.scan_changed_products()
    assert db[f29_scheduler.STATE_COLLECTION].find_one({"_id": f29_scheduler.STATE_ID_MINUTE_SCAN}) is None
