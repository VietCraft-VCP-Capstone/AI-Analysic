import hashlib
import logging
import threading
from datetime import datetime, timezone

import numpy as np
from pymongo.errors import PyMongoError

from app.api.v1._live import db_live

SCORES = "listing_intel_scores"
EMBEDDINGS = "listing_embeddings"
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}
INDEXES = [([("product_id", 1), ("date", 1), ("model_version", 1)], {"unique": True}),
           ([("product_id", 1), ("model_version", 1), ("date", -1)], {})]
log = logging.getLogger(__name__)
_indexed: dict = {"done": False, "thread": None}


def _create_indexes(db) -> None:
    try:
        for keys, opts in INDEXES:
            db[SCORES].create_index(keys, **opts)
    except PyMongoError as exc:
        log.warning("listing intel: index creation failed, writes continue: %s", exc)


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def url_key(url: str) -> str:
    return hashlib.sha1(url.encode()).hexdigest()


def _writable():
    db = db_live()
    address = getattr(getattr(db, "client", None), "address", None)
    if not address or address[0] not in LOCAL_HOSTS:
        log.warning("listing intel: refusing write to non-local mongo %s", address)
        return None
    if not _indexed["done"]:
        _indexed["done"] = True
        _indexed["thread"] = threading.Thread(target=_create_indexes, args=(db,), daemon=True)
        _indexed["thread"].start()
    return db


def save_score(doc: dict) -> None:
    db = _writable()
    if db is not None:
        key = {k: doc[k] for k in ("product_id", "date", "model_version")}
        db[SCORES].update_one(key, {"$set": {**doc, "computed_at": _now()}}, upsert=True)


def latest_scores(product_ids, version: str) -> dict:
    out = {}
    query = {"product_id": {"$in": list(product_ids)}, "model_version": version}
    for d in db_live()[SCORES].find(query).sort("date", -1):
        out.setdefault(d["product_id"], d)
    return out


def last_computed(version: str) -> dict:
    out = {}
    rows = db_live()[SCORES].find({"model_version": version}, {"product_id": 1, "computed_at": 1, "date": 1})
    for d in rows.sort("date", -1):
        out.setdefault(d["product_id"], d.get("computed_at"))
    return out


def get_embedding(url: str):
    d = db_live()[EMBEDDINGS].find_one({"_id": url_key(url)})
    if not d or not d.get("vec"):
        return None
    return np.frombuffer(d["vec"], dtype=np.float16).astype(np.float32), d.get("metrics") or {}


def put_embedding(url: str, vec, metrics: dict) -> None:
    db = _writable()
    if db is not None:
        data = np.asarray(vec, dtype=np.float16).tobytes()
        db[EMBEDDINGS].update_one(
            {"_id": url_key(url)}, {"$set": {"url": url, "vec": data, "metrics": metrics, "updated_at": _now()}},
            upsert=True)
