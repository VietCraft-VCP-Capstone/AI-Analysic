import bisect
import math
from statistics import quantiles

from app.core.f29.constants import MIN_CATEGORY_SAMPLE
from app.core.f29.material import materials_of
from app.core.f29.price_ref import category_of, kind, platform_index, round_price


def price_points(pct: float) -> float:
    if 10 <= pct <= 90:
        return 20.0
    if pct < 10:
        return 20 * pct / 10
    return 20 * (100 - pct) / 10


def _peers(live_db, product: dict) -> list:
    cat = category_of(product)
    if not cat:
        return []
    me, my_shop = product.get("_id"), product.get("shop_id")
    items = platform_index(live_db)["cat"].get((kind(product), cat), [])
    return [it for it in items if it[0] != me and (not my_shop or it[1] != my_shop)]


def _empty(state: str, n: int = 0) -> dict:
    return {"state": state, "pct": None, "n": n, "level": None, "p10": None, "p90": None}


def position(live_db, product: dict, price: float | None) -> dict:
    if price is None or not price > 0:
        return _empty("seller_missing")
    peers = _peers(live_db, product)
    mats = materials_of(product)
    same = [it for it in peers if mats & it[3]]
    if len(same) >= MIN_CATEGORY_SAMPLE:
        pool, level = same, "category_material"
    elif len(peers) >= MIN_CATEGORY_SAMPLE:
        pool, level = peers, "category"
    else:
        return _empty("not_applicable", len(peers))
    logs = sorted(math.log(it[2]) for it in pool)
    x, n = math.log(price), len(logs)
    pct = 100 * (bisect.bisect_left(logs, x) + bisect.bisect_right(logs, x)) / (2 * n)
    q = quantiles(logs, n=10, method="inclusive")
    return {"state": "scored", "pct": pct, "n": n, "level": level,
            "p10": round_price(math.exp(q[0])), "p90": round_price(math.exp(q[8]))}
