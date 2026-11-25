from typing import Any, Dict, List, Tuple

COUNTED = ("scored", "seller_missing")


def score(factors: List[Dict[str, Any]]) -> Tuple[float, Dict[str, int]]:
    counted = [f for f in factors if f["state"] in COUNTED]
    budget = sum(f["weight"] for f in counted)
    value = round(sum(f["points"] for f in counted) * 100 / budget, 1) if budget else 0.0
    return value, {"evaluated": len(counted), "total": len(factors)}
