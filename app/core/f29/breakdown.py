from typing import Any, Dict, List, Tuple

from app.core.f29.constants import FACTOR_WEIGHT

COUNTED = ("scored", "seller_missing")


def score(factors: List[Dict[str, Any]]) -> Tuple[float, Dict[str, int]]:
    counted = [f for f in factors if f["state"] in COUNTED]
    n = len(counted)
    points = sum(f["points"] for f in counted)
    value = round(points * 100 / (FACTOR_WEIGHT * n), 1) if n else 0.0
    return value, {"evaluated": n, "total": len(factors)}
