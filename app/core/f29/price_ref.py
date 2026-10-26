import json
import threading
import time
from pathlib import Path
from statistics import median

from app.api.v1._live import LOC_SP_THAT
from app.core.f29.price_suggest import suggest
from app.core.f29.scoring import to_float
from app.core.listing_intel.live_data import group_of

TIKI_MEDIAN = json.loads((Path(__file__).parents[1] / "listing_intel/model/reference/group_median_price.json")
                         .read_text("utf-8"))
INDEX_TTL_SECONDS = 900
_index_cache: dict = {}
_index_lock = threading.Lock()


def kind(product: dict) -> str:
    return "pod" if product.get("product_type") == "POD_TEMPLATE" else "std"


def product_price(variants: list[dict]) -> float | None:
    prices = [to_float(v.get("retail_price")) for v in variants if v.get("is_active") is not False]
    prices = sorted(p for p in prices if p and p > 0)
    return prices[len(prices) // 2] if prices else None


def category_of(product: dict) -> str | None:
    cats = product.get("categories")
    if isinstance(cats, list) and cats:
        c = cats[0]
        if isinstance(c, str) and c.strip():
            return c.strip()
    cat_ids = product.get("category_ids")
    if isinstance(cat_ids, list) and cat_ids:
        c = cat_ids[0]
        if c is not None and str(c).strip():
            return str(c).strip()
    return None


def product_group(product: dict) -> str | None:
    return group_of(category_of(product))


def clear_index_cache() -> None:
    with _index_lock:
        _index_cache.clear()


def _build_index(live_db) -> dict:
    products = list(live_db["products"].find(
        LOC_SP_THAT, {"categories": 1, "category_ids": 1, "shop_id": 1, "product_type": 1}
    ))
    variants: dict = {}
    for v in live_db["product_variants"].find(
            {"is_active": {"$ne": False}}, {"product_id": 1, "retail_price": 1, "is_active": 1}):
        pid = v.get("product_id")
        if not pid:
            continue
        variants.setdefault(pid, []).append(v)
    by_cat: dict = {}
    by_group: dict = {}
    for p in products:
        price = product_price(variants.get(p["_id"], []))
        if price is None:
            continue
        cat = category_of(p)
        sid = p.get("shop_id")
        k = kind(p)
        if cat:
            by_cat.setdefault((k, cat), []).append((p["_id"], sid, price))
        group = group_of(cat)
        if group:
            by_group.setdefault((k, group), []).append((p["_id"], sid, price))
    return {"cat": by_cat, "group": by_group}


def platform_index(live_db) -> dict:
    now = time.monotonic()
    if _index_cache and now - _index_cache["at"] < INDEX_TTL_SECONDS:
        return _index_cache["value"]
    with _index_lock:
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
        k = kind(product)
        cat = category_of(product)
        group = group_of(cat)
        me = product.get("_id")
        my_shop = product.get("shop_id")
        index = platform_index(self.live_db)
        pools = (("category", index["cat"].get((k, cat), []) if cat else []),
                 ("group", index["group"].get((k, group), []) if group else []))
        for source, pool in pools:
            prices = [
                item[2]
                for item in pool
                if item[0] != me and (not my_shop or item[1] != my_shop)
            ]
            if len(prices) >= self.params["min_peers"]:
                return {"price": median(prices), "source": source, "n": len(prices), "kind": k}
        model = suggest(product.get("title") or "", group)
        if model is not None:
            return {"price": model["mid"], "source": "model", "n": 0, "kind": k}
        return {"price": TIKI_MEDIAN[group or "all"], "source": "tiki", "n": 0, "kind": k}
