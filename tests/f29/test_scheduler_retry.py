from datetime import timedelta

from bson import ObjectId

from app.core import f29_scheduler
from tests.f29.fake_mongo import make_calculator
from tests.f29.samples import NOW, PRODUCT_ID, base_product, with_id

OTHER_ID = "507f1f77bcf86cd799439012"


class _FakeCalc:
    def __init__(self, fail_ids=()):
        self.fail_ids = set(fail_ids)
        self.calls = []
        self.saved = []

    def calculate(self, pid):
        self.calls.append(pid)
        if pid in self.fail_ids:
            raise RuntimeError("boom")
        return {"product_id": pid}

    def save(self, result):
        self.saved.append(result["product_id"])


def _setup(monkeypatch, calc, **seed):
    db = make_calculator(**seed).live_db
    monkeypatch.setattr(f29_scheduler, "db_live", lambda: db)
    monkeypatch.setattr(f29_scheduler, "HealthScoreCalculator", lambda: calc)
    return db


def test_nightly_failure_is_retried_by_minute_scan(monkeypatch):
    products = [with_id(base_product()), with_id(base_product(), OTHER_ID)]
    calc = _FakeCalc(fail_ids={PRODUCT_ID})
    db = _setup(monkeypatch, calc, products=products)

    f29_scheduler.nightly_full_rescan()
    state = db[f29_scheduler.STATE_COLLECTION].find_one({"_id": f29_scheduler.STATE_ID_MINUTE_SCAN})
    assert state["failed_product_ids"] == [PRODUCT_ID]

    calc.calls.clear()
    f29_scheduler.scan_changed_products()
    assert calc.calls == [PRODUCT_ID]


def test_review_edit_triggers_rescore(monkeypatch):
    calc = _FakeCalc()
    db = _setup(
        monkeypatch,
        calc,
        products=[with_id(base_product())],
        reviews=[{
            "product_id": ObjectId(PRODUCT_ID),
            "created_at": NOW - timedelta(days=2),
            "updated_at": NOW - timedelta(minutes=10),
        }],
    )
    db[f29_scheduler.STATE_COLLECTION].seed([
        {"_id": f29_scheduler.STATE_ID_MINUTE_SCAN, "last_scan_time": NOW - timedelta(hours=1)},
    ])

    f29_scheduler.scan_changed_products()
    assert calc.calls == [PRODUCT_ID]
