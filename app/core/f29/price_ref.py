import json
import time
from pathlib import Path
from statistics import median

from app.api.v1._live import LOC_SP_THAT
from app.core.f29.scoring import to_float
from app.core.listing_intel.live_data import group_of

TIKI_MEDIAN = json.loads((Path(__file__).parents[1] / "listing_intel/model/reference/group_median_price.json")
                         .read_text("utf-8"))
INDEX_TTL_SECONDS = 900
_index_cache: dict = {}


def product_price(variants: list[dict]) -> float | None:
    prices = [to_float(v.get("retail_price")) for v in variants if v.get("is_active") is not False]
    prices = sorted(p for p in prices if p and p > 0)
    return prices[len(prices) // 2] if prices else None


def _category(product: dict) -> str | None:
    return (product.get("categories") or [None])[0]


def clear_index_cache() -> None:
    _index_cache.clear()


def _build_index(live_db) -> dict:
    products = list(live_db["products"].find(LOC_SP_THAT, {"categories": 1}))
    variants: dict = {}
    for v in live_db["product_variants"].find(
            {"is_active": {"$ne": False}}, {"product_id": 1, "retail_price": 1, "is_active": 1}):
        variants.setdefault(v["product_id"], []).append(v)
    by_cat: dict = {}
    by_group: dict = {}
    for p in products:
        price = product_price(variants.get(p["_id"], []))
        if price is None:
            continue
        cat = _category(p)
        if cat:
            by_cat.setdefault(cat, []).append((p["_id"], price))
        group = group_of(cat)
        if group:
            by_group.setdefault(group, []).append((p["_id"], price))
    return {"cat": by_cat, "group": by_group}


def platform_index(live_db) -> dict:
    now = time.monotonic()
    if _index_cache and now - _index_cache["at"] < INDEX_TTL_SECONDS:
        return _index_cache["value"]
    value = _build_index(live_db)
    _index_cache.update(value=value, at=now)
    return value


class PriceRef:
    def __init__(self, live_db, params: dict):
        self.live_db = live_db
        self.params = params

    def reference(self, product: dict) -> dict:
        cat = _category(product)
        group = group_of(cat)
        me = product.get("_id")
        index = platform_index(self.live_db)
        pools = (("category", index["cat"].get(cat, []) if cat else []),
                 ("group", index["group"].get(group, []) if group else []))
        for source, pool in pools:
            prices = [price for pid, price in pool if pid != me]
            if len(prices) >= self.params["min_peers"]:
                return {"price": median(prices), "source": source, "n": len(prices)}
        return {"price": TIKI_MEDIAN[group or "all"], "source": "tiki", "n": 0}
