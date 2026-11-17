import json
import threading
import time
from pathlib import Path
from statistics import median, quantiles

from app.api.v1._live import LOC_SP_THAT
from app.core.f29.material import materials_of
from app.core.f29.price_suggest import suggest, round_price
from app.core.f29.scoring import to_float
from app.core.listing_intel.live_data import group_of

TIKI_MEDIAN = json.loads((Path(__file__).parents[1] / "listing_intel/model/reference/group_median_price.json")
                         .read_text("utf-8"))
INDEX_TTL_SECONDS = 900
_index_cache: dict = {}
_index_lock = threading.Lock()
_materials_cache: dict = {}


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
        _materials_cache.clear()


def _cached_materials(product: dict) -> frozenset:
    sig = (product.get("title"), repr(product.get("materials")))
    hit = _materials_cache.get(product["_id"])
    if hit is None or hit[0] != sig:
        hit = _materials_cache[product["_id"]] = (sig, materials_of(product))
    return hit[1]


def _build_index(live_db) -> dict:
    products = list(live_db["products"].find(
        LOC_SP_THAT, {"categories": 1, "category_ids": 1, "shop_id": 1, "product_type": 1, "title": 1, "materials": 1}
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
        item = (p["_id"], sid, price, _cached_materials(p))
        if cat:
            by_cat.setdefault((k, cat), []).append(item)
        group = group_of(cat)
        if group:
            by_group.setdefault((k, group), []).append(item)
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


def _sample(prices: list[float], cap: int = 80) -> list[float]:
    ordered = sorted(prices)
    if len(ordered) <= cap:
        return ordered
    return [ordered[round(i * (len(ordered) - 1) / (cap - 1))] for i in range(cap)]


def _from_pool(prices: list[float], source: str, k: str, mats: list[str]) -> dict:
    q1, _, q3 = quantiles(prices, n=4, method="inclusive")
    return {"price": median(prices), "source": source, "n": len(prices), "kind": k,
            "comparable": source == "material", "low": round_price(q1), "high": round_price(q3), "materials": mats,
            "prices": _sample(prices)}


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
        mats = materials_of(product)
        index = platform_index(self.live_db)

        def others(pool):
            return [it for it in pool if it[0] != me and (not my_shop or it[1] != my_shop)]

        cat_pool = others(index["cat"].get((k, cat), [])) if cat else []
        same = [it for it in cat_pool if it[3] & mats]
        pools = (("material", same), ("category", cat_pool),
                 ("group", others(index["group"].get((k, group), [])) if group else []))
        for source, pool in pools:
            if len(pool) >= self.params["min_peers"]:
                shared = sorted(mats & frozenset().union(*(it[3] for it in pool))) if source == "material" else []
                return {**_from_pool([it[2] for it in pool], source, k, shared), "same_n": len(same)}
        base = {"n": 0, "kind": k, "comparable": False, "materials": [], "same_n": len(same),
                "prices": _sample([it[2] for it in cat_pool])}
        model = suggest(product.get("title") or "", group, mats)
        if model is not None:
            return {"price": model["mid"], "source": "model", "low": model["low"], "high": model["high"],
                    "material_factor": model.get("material_factor", 1.0), **base}
        return {"price": TIKI_MEDIAN[group or "all"], "source": "tiki", "low": None, "high": None, **base}
