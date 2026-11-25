from types import SimpleNamespace
from typing import Any, Dict, List

from app.core.f29.score.calculator import HealthScoreCalculator

_MISSING = object()


def _get_path(doc: Dict[str, Any], path: str) -> Any:
    cur = doc
    parts = path.split(".")
    for i, part in enumerate(parts):
        if isinstance(cur, list) and not part.isdigit():
            vals = (_get_path(x, ".".join(parts[i:])) for x in cur)
            return [v for v in vals if v is not _MISSING]
        if isinstance(cur, dict):
            if part not in cur:
                return _MISSING
            cur = cur[part]
        elif isinstance(cur, list):
            try:
                idx = int(part)
            except ValueError:
                return _MISSING
            cur = cur[idx] if 0 <= idx < len(cur) else _MISSING
        else:
            return _MISSING
    return cur


def _match_one(doc: Dict[str, Any], query: Dict[str, Any]) -> bool:
    for key, expected in (query or {}).items():
        actual = _get_path(doc, key)
        if isinstance(expected, dict) and expected and all(str(k).startswith("$") for k in expected):
            for op, arg in expected.items():
                present = actual is not _MISSING
                val = None if actual is _MISSING else actual
                if op == "$exists":
                    if present != arg:
                        return False
                elif op == "$gt":
                    if not (present and val > arg):
                        return False
                elif op == "$gte":
                    if not (present and val >= arg):
                        return False
                elif op == "$lt":
                    if not (present and val < arg):
                        return False
                elif op == "$ne":
                    if val == arg:
                        return False
                elif op == "$in":
                    if not (any(v in arg for v in val) if isinstance(val, list) else val in arg):
                        return False
                elif op == "$nin":
                    if val in arg:
                        return False
                else:
                    raise NotImplementedError(f"operator chưa hỗ trợ trong fake mongo: {op}")
            continue
        val = None if actual is _MISSING else actual
        if val != expected:
            return False
    return True


class _FakeCursor:
    def __init__(self, docs: List[Dict[str, Any]]):
        self._docs = docs

    def sort(self, key_or_list, direction=None):
        pairs = [(key_or_list, direction)] if isinstance(key_or_list, str) else list(key_or_list)
        for key, dirn in reversed(pairs):
            self._docs = sorted(self._docs, key=lambda d: (d.get(key) is not None, d.get(key)),
                                reverse=dirn == -1)
        return self

    def limit(self, n):
        self._docs = self._docs[:n]
        return self

    def __iter__(self):
        return iter(self._docs)


class _FakeCollection:
    def __init__(self):
        self.docs = []

    def seed(self, docs: List[Dict[str, Any]]):
        self.docs = [dict(d) for d in docs]
        return self

    def find(self, query=None, projection=None):
        return _FakeCursor([dict(d) for d in self.docs if _match_one(d, query or {})])

    def find_one(self, query=None, projection=None, sort=None):
        matched = [d for d in self.docs if _match_one(d, query or {})]
        if sort:
            for key, dirn in reversed(sort):
                matched = sorted(matched, key=lambda d: (d.get(key) is not None, d.get(key)),
                                 reverse=dirn == -1)
        return dict(matched[0]) if matched else None

    @staticmethod
    def _apply(doc: Dict[str, Any], update: Dict[str, Any]):
        for k, v in update.get("$set", {}).items():
            doc[k] = v
        for k, v in update.get("$setOnInsert", {}).items():
            doc.setdefault(k, v)
        for k in update.get("$unset", {}):
            doc.pop(k, None)

    def update_one(self, filt, update, upsert=False):
        for d in self.docs:
            if _match_one(d, filt):
                self._apply(d, update)
                return SimpleNamespace(matched_count=1, modified_count=1, upserted_id=None)
        if upsert:
            new_doc = {k: v for k, v in filt.items() if not isinstance(v, dict)}
            self._apply(new_doc, update)
            self.docs.append(new_doc)
            return SimpleNamespace(matched_count=0, modified_count=0, upserted_id=True)
        return SimpleNamespace(matched_count=0, modified_count=0, upserted_id=None)

    def insert_one(self, doc):
        self.docs.append(dict(doc))
        return SimpleNamespace(inserted_id=doc.get("_id"))

    def delete_many(self, filt):
        kept = [d for d in self.docs if not _match_one(d, filt)]
        deleted = len(self.docs) - len(kept)
        self.docs = kept
        return SimpleNamespace(deleted_count=deleted)

    def count_documents(self, query=None):
        return len(list(self.find(query or {})))


class _FakeDB(dict):
    def __getitem__(self, name):
        if name not in self:
            dict.__setitem__(self, name, _FakeCollection())
        return dict.__getitem__(self, name)


class _FakeMongoClient:
    def __init__(self):
        self._db = _FakeDB()

    def __getitem__(self, _name):
        return self._db


def make_calculator(**seed) -> HealthScoreCalculator:
    client = _FakeMongoClient()
    calc = HealthScoreCalculator(db_client=client)
    for coll_name, docs in seed.items():
        calc.live_db[coll_name].seed(docs)
    return calc
