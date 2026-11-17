from typing import Any, Dict, Optional

from app.core.f29 import factors, scoring, weights
from app.core.f29.calculator import HealthScoreCalculator
from app.core.f29.factors import KEYS

LEVERS = ("n_images", "description_length", "n_tags", "price")
INPUT_OF = {"image": "n_images", "description": "description_length", "tags": "n_tags", "price": "price"}


def _sub(key: str, used: Dict[str, Any], rows: Dict[str, Any], pc: Dict[str, Any]) -> float:
    if key == "price":
        ref = rows["price"]["reference"]
        if not ref["comparable"]:
            return 0.0
        return factors.price_score(used["price"], ref["price"], pc)
    return factors.ratio_score(float(used[INPUT_OF[key]]), float(rows[key]["target"]))


def preview_health(
    calc: HealthScoreCalculator, product_id: str, overrides: Dict[str, Optional[float]]
) -> Optional[Dict[str, Any]]:
    current = calc.calculate(product_id)
    if current is None or "error" in current:
        return current

    rows = {r["key"]: r for r in current["breakdown"]}
    cfg = weights.load()
    w, pc = cfg["weights"], cfg["price"]
    now_in = {"n_images": rows["image"]["value"], "description_length": rows["description"]["value"],
              "n_tags": rows["tags"]["value"], "price": rows["price"]["value"]}
    given = {k: v for k, v in overrides.items() if v is not None}
    used = {**now_in, **{k: v for k, v in given.items() if k in LEVERS}}

    unscored = {"price"} if used["price"] is not None and not rows["price"]["reference"]["comparable"] else set()
    subs: Dict[str, Optional[float]] = {}
    points: Dict[str, float] = {}
    for key in KEYS:
        if key in unscored:
            subs[key], points[key] = None, 0.0
            continue
        if key in ("review", "material"):
            subs[key], points[key] = rows[key]["sub_score"], rows[key]["points"]
            continue
        sub = _sub(key, used, rows, pc)
        subs[key], points[key] = round(sub, 1), round(w[key] * sub / 100, 1)

    scored = [k for k in KEYS if k not in unscored]
    score = round(sum(points[k] for k in scored) * 100 / sum(w[k] for k in scored), 1)
    if current.get("cap"):
        score = min(score, current["cap"]["score"])
    empty = {"image": not used["n_images"], "description": not used["description_length"],
             "tags": not used["n_tags"], "price": used["price"] is None}
    return {
        "product_id": product_id,
        "score": score,
        "status": scoring.status_from_score(score),
        "axes": subs,
        "axes_missing": [k for k in KEYS if empty.get(k, rows[k]["missing"])],
        "current_score": current["score"],
        "delta_vs_current": round(score - current["score"], 1),
        "inputs": used,
        "current_inputs": now_in,
        "ignored": [k for k in given if k not in LEVERS],
        "model_version": current["model_version"],
    }
