import os
from datetime import date, datetime

from app.core.listing_intel import jobs, service
from tests.listing_intel.intel_support import env, listing  # noqa: F401


def test_nightly_recomputes_only_changed(env):
    service.analyze(listing(), date(2026, 10, 21), persist=True)
    assert jobs.nightly() == 2
    assert jobs.nightly() == 0


def test_nightly_skips_without_bundle(env, monkeypatch, tmp_path, caplog):
    monkeypatch.setenv("LI_BUNDLE_DIR", str(tmp_path))
    assert jobs.nightly() == 0
    assert "bundle not ready" in caplog.text and env["listing_intel_scores"].docs == []


def test_weekly_trends_refresh_and_errors_logged(monkeypatch, caplog):
    calls = []
    monkeypatch.setattr(jobs, "_local_mongo_up", lambda: True)
    monkeypatch.setattr(jobs.subprocess, "run", lambda cmd, **kw: calls.append(cmd) or (_ for _ in ()).throw(OSError("x")))
    jobs.weekly_trends()
    assert calls[0][-2:] == ["scripts.li.collect_trend_keywords", "--refresh"]
    assert "weekly trend collection failed" in caplog.text


def test_weekly_trends_skips_without_local_mongo(monkeypatch, caplog):
    monkeypatch.setattr(jobs, "LOCAL_MONGO", "mongodb://127.0.0.1:1")
    monkeypatch.setattr(jobs.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(AssertionError("ran")))
    with caplog.at_level("INFO", logger=jobs.__name__):
        jobs.weekly_trends()
    assert "trend collection disabled (local-only)" in caplog.text and "ERROR" not in caplog.text


class _Trends:
    def __init__(self, rows):
        self.trend_interest = self
        self.rows = rows

    def aggregate(self, pipeline):
        kws = pipeline[0]["$match"]["keyword"]["$in"]
        return [r for r in self.rows if r["_id"] in kws]


def test_stale_keywords(monkeypatch):
    monkeypatch.chdir(os.getcwd())
    monkeypatch.setenv("MONGODB_URI", "mongodb://127.0.0.1:27017")
    monkeypatch.setenv("MONGODB_DB", "data-collection")
    from scripts.li.collect_trend_keywords import stale

    db = _Trends([{"_id": "áo thun", "last": datetime(2026, 10, 18)}, {"_id": "túi tote", "last": datetime(2026, 8, 16)}])
    assert stale(db, ["áo thun", "túi tote", "mới"], now=datetime(2026, 10, 21)) == ["túi tote", "mới"]
