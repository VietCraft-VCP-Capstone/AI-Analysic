import threading
import time
from typing import Any, List, Tuple

from app.api.v1._live import LOC_DON_THAT
from app.core.f29.scoring import to_float

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
