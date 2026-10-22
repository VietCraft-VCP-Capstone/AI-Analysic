import time
from typing import Any, List, Tuple

from app.api.v1._live import LOC_DON_THAT
from app.core.f29.scoring import to_float

GOOD_STARS = 4
P0_TTL_SECONDS = 3600
_p0_cache: dict = {}


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
    _p0_cache.clear()


def platform_p0(live_db) -> float:
    now = time.monotonic()
    if _p0_cache and now - _p0_cache["at"] < P0_TTL_SECONDS:
        return _p0_cache["value"]
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
