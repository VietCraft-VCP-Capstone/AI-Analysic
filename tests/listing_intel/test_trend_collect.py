import json
import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

ANCHOR = "quà sinh nhật"


class _Coll:
    def __init__(self, docs=None):
        self.docs = list(docs or [])

    def _match(self, d, q):
        return all(d.get(k) in v["$in"] if isinstance(v, dict) else d.get(k) == v for k, v in q.items())

    def distinct(self, field, q):
        return list({d[field] for d in self.docs if self._match(d, q)})

    def aggregate(self, pipeline):
        rows = [d for d in self.docs if self._match(d, pipeline[0]["$match"])]
        group = pipeline[1]["$group"]
        key, (name, (op, field)) = group["_id"], next((k, next(iter(v.items()))) for k, v in group.items() if k != "_id")
        out = {}
        for d in rows:
            out.setdefault(d[key[1:]] if key else None, []).append(d[field[1:]])
        fn = max if op == "$max" else lambda v: sum(v) / len(v)
        return iter([{"_id": k, name: fn(v)} for k, v in out.items()])

    def bulk_write(self, ops, ordered=False):
        for op in ops:
            key = {k: v.replace(tzinfo=None) if isinstance(v, datetime) else v for k, v in op._filter.items()}
            doc = next((d for d in self.docs if self._match(d, key)), None)
            if doc is None:
                doc = dict(key)
                self.docs.append(doc)
            doc.update(op._doc["$set"])
        return SimpleNamespace(upserted_count=len(ops), modified_count=0)

    def create_index(self, *a, **k):
        return None

    def insert_one(self, doc):
        return SimpleNamespace(inserted_id=1)

    def update_one(self, *a, **k):
        return None


class _DB:
    def __init__(self, rows):
        self.client, self.name = SimpleNamespace(address=("127.0.0.1", 27017)), "data-collection"
        self.trend_interest = _Coll(rows)

    def __getattr__(self, name):
        setattr(self, name, _Coll())
        return getattr(self, name)


def _point(kw, when, scaled):
    return {"keyword": kw, "observed_on": when, "granularity": "weekly", "geo": "VN", "scaled": scaled}


@pytest.fixture
def collector(monkeypatch, tmp_path):
    monkeypatch.chdir(os.getcwd())
    monkeypatch.setenv("MONGODB_URI", "mongodb://127.0.0.1:27017")
    monkeypatch.setenv("MONGODB_DB", "data-collection")
    from scripts.li import collect_trend_keywords as m

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    rows = [_point(ANCHOR, datetime(2026, 1, 4), 20.0), _point(ANCHOR, datetime(2026, 1, 11), 20.0),
            _point("tươi", now - timedelta(days=1), 5.0), _point("cũ", datetime(2026, 8, 16), 5.0)]
    db, fails = _DB(rows), set()
    kws = tmp_path / "kw.json"
    kws.write_text(json.dumps([ANCHOR, "tươi", "cũ", "mới 1", "mới 2", "mới 3", "mới 4"]), "utf-8")
    (tmp_path / "out").mkdir()
    (tmp_path / "out" / m.MISSING).write_text("[]", "utf-8")

    def fetch(tr, terms, timeframe):
        if fails & set(terms):
            return None
        idx = pd.date_range(end="2026-10-18", periods=52, freq="W-SUN")
        return pd.DataFrame({t: np.full(52, 10.0) for t in terms}, index=idx)

    for name, value in {"KEYWORDS": kws, "OUT": tmp_path / "out"}.items():
        monkeypatch.setattr(m, name, value)
    for name, value in {"fetch_batch": fetch, "polite_sleep": lambda: None, "make_client": lambda: None,
                        "load_checkpoint": lambda g: {}, "save_checkpoint": lambda g, d: None,
                        "clear_checkpoint": lambda g: None}.items():
        monkeypatch.setattr(m.ct, name, value)
    monkeypatch.setattr(m.ct.store_mongo, "get_db", lambda *a, **k: db)
    return m, db, fails


def test_refresh_selects_stale_and_absent_and_writes(collector):
    m, db, _ = collector
    saved = m.main(refresh=True)
    assert sorted(saved) == ["cũ", "mới 1", "mới 2", "mới 3", "mới 4"]
    cu = [d for d in db.trend_interest.docs if d["keyword"] == "cũ"]
    assert len(cu) == 52 and max(d["observed_on"] for d in cu) == datetime(2026, 10, 18)
    assert {d["scaled"] for d in cu} == {20.0}
    assert len([d for d in db.trend_interest.docs if d["keyword"] == ANCHOR]) == 2
    assert not (m.OUT / m.MISSING).exists()


def test_rate_limit_stops_and_records_missing(collector):
    m, db, fails = collector
    fails.add("mới 4")
    saved = m.main(refresh=True)
    assert saved == []
    assert json.loads((m.OUT / m.MISSING).read_text("utf-8")) == ["mới 1", "mới 2", "mới 3", "mới 4"]


def test_absent_keywords_fetched_before_stale(collector):
    m, db, fails = collector
    fails.add("cũ")
    assert m.main(refresh=True) == ["mới 1", "mới 2", "mới 3", "mới 4"]
    assert not (m.OUT / m.MISSING).exists()
