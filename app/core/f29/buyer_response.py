import threading
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, Optional, Tuple

from bson import ObjectId

from app.api.v1._live import LOC_SP_THAT
from app.api.v1._live_data import DON_HOP_LE

WINDOW_DAYS = 30
MIN_PRODUCT_VIEWS = 30
MIN_CATEGORY_VIEWS = 200
CATEGORY_TTL = 900
_category_cache: Dict[str, Dict[str, Any]] = {}
_category_lock = threading.Lock()


def clear_category_cache() -> None:
    with _category_lock:
        _category_cache.clear()


def window_start() -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=WINDOW_DAYS)


def _empty() -> Dict[str, int]:
    return {"views": 0, "carts": 0, "orders": 0}


def _counts(live_db, ids: Iterable[Any], since: datetime) -> Dict[str, Dict[str, int]]:
    ids = set(ids)
    keys = {str(i) for i in ids}
    ra: Dict[str, Dict[str, int]] = defaultdict(_empty)
    kinds = {"view": "views", "add_to_cart": "carts"}
    for e in live_db["product_events"].find(
            {"product_id": {"$in": list(ids)}, "created_at": {"$gte": since}},
            {"product_id": 1, "event_type": 1}):
        if e.get("event_type") in kinds:
            ra[str(e["product_id"])][kinds[e["event_type"]]] += 1
    for order in live_db["orders"].find({**DON_HOP_LE, "created_at": {"$gte": since}, "items.product_id": {"$in": list(ids)}}, {"items": 1}):
        for pid in {str(it.get("product_id")) for it in order.get("items") or []} & keys:
            ra[pid]["orders"] += 1
    return ra


def _rate(c: Dict[str, int]) -> Optional[float]:
    return (c["carts"] + c["orders"]) / c["views"] if c["views"] else None


def product_rate(live_db, product_oid: Any, since: datetime) -> Tuple[int, Optional[float]]:
    c = _counts(live_db, [product_oid], since)[str(product_oid)]
    return c["views"], _rate(c)


def category_rate(live_db, category: Optional[str], since: datetime) -> Tuple[int, Optional[float]]:
    if category is None:
        return 0, None
    now = time.monotonic()
    with _category_lock:
        hit = _category_cache.get(category)
        if hit and now - hit["at"] < CATEGORY_TTL:
            return hit["value"]
    queries = [{"categories.0": category}]
    if ObjectId.is_valid(category):
        queries.append({"category_ids.0": ObjectId(category)})
    ids = {p["_id"] for q in queries for p in live_db["products"].find({**LOC_SP_THAT, **q}, {"_id": 1})}
    ra = _counts(live_db, ids, since)
    total = _empty()
    for c in ra.values():
        for k in total:
            total[k] += c[k]
    res = (total["views"], _rate(total))
    with _category_lock:
        _category_cache[category] = {"value": res, "at": now}
    return res


def is_scored(product_views: int, cat_views: int, cat_rate: Optional[float]) -> bool:
    return product_views >= MIN_PRODUCT_VIEWS and cat_views >= MIN_CATEGORY_VIEWS and bool(cat_rate)
