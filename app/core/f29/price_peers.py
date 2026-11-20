import bisect
import math
from statistics import quantiles

from app.core.f29 import material
from app.core.f29.price_ref import category_of, kind, platform_index, round_price

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
    params = material.price_params()
    factor = material.material_price_factor(material.materials_of(product))
    logs = trim(sorted(math.log(it[2] / material.material_price_factor(it[3])) for it in _peers(live_db, product)))
    n = len(logs)
    if n < params["min_peers"]:
        return _empty("not_applicable", n)
    x = math.log(price / factor)
    pct = 100 * (bisect.bisect_left(logs, x) + bisect.bisect_right(logs, x)) / (2 * n)
    q = quantiles(logs, n=10, method="inclusive")
    return {"state": "scored", "pct": pct, "n": n, "factor": factor,
            "confidence": round(min(1.0, n / params["full_n"]), 2),
            "p10": round_price(math.exp(q[0]) * factor), "p90": round_price(math.exp(q[8]) * factor)}
