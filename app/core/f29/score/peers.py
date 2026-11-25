import threading
import time
from typing import Any, Dict, FrozenSet, List, Tuple

from app.api.v1._live import LOC_DON_THAT, LOC_SP_THAT
from app.core.f29 import constants
from app.core.f29.score import factors
from app.core.f29.constants import MODEL_VERSION
from app.core.f29.constants import desc_words, review_score
from app.core.f29.score.price import category_of, product_group
from app.core.f29.score.scoring import count_approved_tags, to_float


GOOD_STARS = 4
P0_TTL_SECONDS = 3600
_p0_cache: dict = {}
_p0_lock = threading.Lock()


def _rated(rows) -> List[Tuple[Any, float]]:
    out = []
    for r in rows:
        rating = to_float(r.get("rating"))
        if rating is not None:
            out.append((r.get("order_id"), rating))
    return out


def _count_good(ratings: List[float]) -> Tuple[int, int]:
    return sum(r >= GOOD_STARS for r in ratings), len(ratings)


def clear_p0_cache() -> None:
    with _p0_lock:
        _p0_cache.clear()


def _aggregate_p0(live_db) -> float | None:
    try:
        coll = live_db["reviews"]
        if not hasattr(coll, "aggregate"):
            return None
        pipeline = [
            {"$match": {"rating": {"$exists": True, "$ne": None}}},
            {"$lookup": {
                "from": "orders",
                "localField": "order_id",
                "foreignField": "_id",
                "as": "order",
            }},
            {"$unwind": "$order"},
            {"$match": {
                "order.seed_ref": {"$exists": False},
                "order.is_simulated": {"$ne": True},
            }},
            {"$group": {
                "_id": None,
                "good": {"$sum": {"$cond": [{"$gte": ["$rating", GOOD_STARS]}, 1, 0]}},
                "total": {"$sum": 1},
            }},
        ]
        res = list(coll.aggregate(pipeline))
        if res and res[0].get("total"):
            return res[0]["good"] / res[0]["total"]
        return 0.0
    except Exception:
        return None


def platform_p0(live_db) -> float:
    now = time.monotonic()
    if _p0_cache and now - _p0_cache["at"] < P0_TTL_SECONDS:
        return _p0_cache["value"]
    with _p0_lock:
        now = time.monotonic()
        if _p0_cache and now - _p0_cache["at"] < P0_TTL_SECONDS:
            return _p0_cache["value"]
        agg_val = _aggregate_p0(live_db)
        if agg_val is not None:
            _p0_cache.update(value=agg_val, at=now)
            return agg_val
        real = {o["_id"] for o in live_db["orders"].find(LOC_DON_THAT, {"_id": 1})}
        rated = _rated(live_db["reviews"].find({}, {"order_id": 1, "rating": 1}))
        good, n = _count_good([r for oid, r in rated if oid in real])
        value = good / n if n else 0.0
        _p0_cache.update(value=value, at=now)
        return value


def product_counts(live_db, product_oid) -> Tuple[int, int]:
    rated = _rated(live_db["reviews"].find({"product_id": product_oid}, {"order_id": 1, "rating": 1}))
    real = {o["_id"] for o in live_db["orders"].find(
        {"_id": {"$in": [oid for oid, _ in rated]}, **LOC_DON_THAT}, {"_id": 1})}
    return _count_good([r for oid, r in rated if oid in real])


def counts_by_product(live_db, product_oids) -> dict:
    rows = list(live_db["reviews"].find({"product_id": {"$in": list(product_oids)}},
                                        {"product_id": 1, "order_id": 1, "rating": 1}))
    real = {o["_id"] for o in live_db["orders"].find(
        {"_id": {"$in": [r.get("order_id") for r in rows]}, **LOC_DON_THAT}, {"_id": 1})}
    ratings: dict = {}
    for r in rows:
        rating = to_float(r.get("rating"))
        if rating is not None and r.get("order_id") in real:
            ratings.setdefault(r["product_id"], []).append(rating)
    return {pid: _count_good(v) for pid, v in ratings.items()}


MIN_PEERS = 10
FIELDS = {"images": 1, "description": 1, "tags": 1, "tag_ids": 1, "categories": 1, "category_ids": 1}


def comparison_set(product: Dict[str, Any], peers: List[Dict[str, Any]]) -> Tuple[str, List[Dict[str, Any]]]:
    for level, key in (("category", category_of), ("group", product_group)):
        mine = key(product)
        same = [p for p in peers if mine is not None and key(p) == mine]
        if len(same) >= MIN_PEERS:
            return level, same
    return "all", peers


USEFUL_FIELDS = dict.fromkeys(("product_id", "computed_at", "factors.key", "factors.state", "factors.evidence.useful"), 1)


def stored_useful(ids: List[Any]) -> Dict[Any, int]:
    latest: Dict[Any, Dict[str, Any]] = {}
    for d in constants.store_db()["listing_health_scores"].find({"product_id": {"$in": ids}, "model_version": MODEL_VERSION},
                                                                USEFUL_FIELDS):
        if d["product_id"] not in latest or d["computed_at"] > latest[d["product_id"]]["computed_at"]:
            latest[d["product_id"]] = d
    out = {}
    for pid, d in latest.items():
        image = next((f for f in d.get("factors") or [] if f.get("key") == "image" and f.get("state") == "scored"), None)
        if image is not None and "useful" in image.get("evidence", {}):
            out[pid] = image["evidence"]["useful"]
    return out


def peer_values(live_db, product: Dict[str, Any], pending: FrozenSet, p0: float, m: float) -> Dict[str, Any]:
    everyone = list(live_db["products"].find({**LOC_SP_THAT, "_id": {"$ne": product.get("_id")}}, FIELDS))
    level, peers = comparison_set(product, everyone)
    ids = [p["_id"] for p in peers]
    counts, useful = counts_by_product(live_db, ids), stored_useful(ids)
    return {
        "level": level, "n": len(peers),
        "image": [useful.get(p["_id"], factors.image_count(p)) for p in peers],
        "description": [desc_words(p.get("description")) for p in peers],
        "tags": [count_approved_tags(p, pending) for p in peers],
        "review": [review_score(g, n, p0, m) for g, n in counts.values() if n],
    }
