import bisect
import json
import math
import threading
import time
from collections import Counter, defaultdict
from statistics import quantiles

from app.api.v1._live import LOC_SP_THAT
from app.core.f29.score import text_rules
from app.core.f29.score.text_rules import materials_of
from app.core.f29.score.scoring import to_float
from app.core.f29.shared.normalize import fold, norm
from app.core.f29.paths import DATA


GROUPS = {norm(k): v for k, v in json.loads((DATA / "category_map.json").read_text("utf-8"))["vietcraft"].items()}
MIN_PRICE = 1000.0
INDEX_TTL_SECONDS = 900
_index_cache: dict = {}
_index_lock = threading.Lock()
_materials_cache: dict = {}


def group_of(category) -> str | None:
    return GROUPS.get(norm(category)) if category else None


def round_price(x: float) -> float:
    return max(round(x, -3), MIN_PRICE)


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


HIGH_PCT = 90
FENCE = 3.0
MAX_DROP = 50.0


def price_sub(pct: float, reasons, confidence: float) -> float:
    if pct <= HIGH_PCT or reasons:
        return 100.0
    return 100.0 - MAX_DROP * min(1.0, (pct - HIGH_PCT) / (100 - HIGH_PCT)) * confidence


def trim(logs: list) -> list:
    if len(logs) < 4:
        return logs
    q1, _, q3 = quantiles(logs, n=4, method="inclusive")
    lo, hi = q1 - FENCE * (q3 - q1), q3 + FENCE * (q3 - q1)
    return [x for x in logs if lo <= x <= hi]


def _peers(live_db, product: dict) -> list:
    cat = category_of(product)
    if not cat:
        return []
    me, my_shop = product.get("_id"), product.get("shop_id")
    items = platform_index(live_db)["cat"].get((kind(product), cat), [])
    return [it for it in items if it[0] != me and (not my_shop or it[1] != my_shop)]


def _empty(state: str, n: int = 0) -> dict:
    return {"state": state, "pct": None, "n": n, "factor": None, "confidence": None, "p10": None, "p90": None}


def position(live_db, product: dict, price: float | None) -> dict:
    if price is None or not price > 0:
        return _empty("seller_missing")
    params = text_rules.price_params()
    factor = text_rules.material_price_factor(text_rules.materials_of(product))
    logs = trim(sorted(math.log(it[2] / text_rules.material_price_factor(it[3])) for it in _peers(live_db, product)))
    n = len(logs)
    if n < params["min_peers"]:
        return _empty("not_applicable", n)
    x = math.log(price / factor)
    pct = 100 * (bisect.bisect_left(logs, x) + bisect.bisect_right(logs, x)) / (2 * n)
    q = quantiles(logs, n=10, method="inclusive")
    return {"state": "scored", "pct": pct, "n": n, "factor": factor,
            "confidence": round(min(1.0, n / params["full_n"]), 2),
            "p10": round_price(math.exp(q[0]) * factor), "p90": round_price(math.exp(q[8]) * factor)}


def product_text(product: dict) -> str:
    tags = [t for t in product.get("tags") or [] if isinstance(t, str)]
    return " ".join([product.get("title") or ""] + tags)


def relevant(query, text) -> bool:
    seen = set(fold(text).split())
    need = fold(query).split()
    return bool(need) and all(w in seen for w in need)


def category_queries(live_db, category, since) -> list:
    logs = list(live_db["search_logs"].find({"created_at": {"$gte": since}}, {"keyword": 1, "clicks": 1}))
    pids = [c["product_id"] for log in logs for c in log.get("clicks") or []]
    cats = {p["_id"]: category_of(p) for p in live_db["products"].find(
        {**LOC_SP_THAT, "_id": {"$in": pids}}, {"categories": 1, "category_ids": 1})}
    grouped = defaultdict(lambda: {"searches": 0, "cats": set(), "raw": Counter()})
    for log in logs:
        key = fold(log.get("keyword"))
        if not key:
            continue
        g = grouped[key]
        g["searches"] += 1
        g["raw"][norm(log.get("keyword"))] += 1
        for c in log.get("clicks") or []:
            if cats.get(c["product_id"]):
                g["cats"].add(cats[c["product_id"]])
    rows = [{"query": g["raw"].most_common(1)[0][0], "searches": g["searches"]}
            for g in grouped.values()
            if g["searches"] >= 2 and g["cats"] and (category is None or category in g["cats"])]
    return sorted(rows, key=lambda r: (-r["searches"], r["query"]))


GENERIC = frozenset("nam nữ unisex bé trẻ em người lớn đẹp cao cấp form rộng size màu đen trắng xanh đỏ hồng vàng nâu xám be set bộ mới hot giá rẻ cho và của thời trang phong cách chính hãng in hình".split())


def about(query, product) -> bool:
    own = set(norm(" ".join([product.get("title") or "", *(product.get("tags") or [])])).split())
    words = own | set(norm(category_of(product) or "").split())
    need = norm(query).split()
    return (any(w in own and w not in GENERIC for w in need)
            and sum(w in words for w in need) * 2 >= len(need))


def zero_result_queries(live_db, product, since, limit=5) -> list:
    logs = live_db["search_logs"].find({"created_at": {"$gte": since}, "result_count": 0}, {"keyword": 1})
    grouped = defaultdict(lambda: {"searches": 0, "raw": Counter()})
    for log in logs:
        key = fold(log.get("keyword"))
        if not key:
            continue
        grouped[key]["searches"] += 1
        grouped[key]["raw"][norm(log.get("keyword"))] += 1
    rows = [{"query": q, "searches": g["searches"]}
            for g in grouped.values() if g["searches"] >= 2
            for q in [g["raw"].most_common(1)[0][0]] if about(q, product)]
    return sorted(rows, key=lambda r: (-r["searches"], r["query"]))[:limit]
