from datetime import datetime, timezone
from typing import Any, Dict, FrozenSet, List, Optional

from bson import ObjectId

from app.api.v1._live import LOC_SP_THAT
from app.core.f29 import scoring
from app.core.f29.calculator import HealthScoreCalculator

LEVERS = ("n_images", "description_length", "n_tags", "in_stock_ratio_pct")
CONTENT_LEVERS = ("n_images", "description_length", "n_tags")


def current_inputs(product: Dict[str, Any], axes: Dict[str, Optional[float]], pending_tag_ids: FrozenSet = frozenset()) -> Dict[str, Optional[float]]:
    return {
        "n_images": len(product.get("images") or []),
        "description_length": len((product.get("description") or "").strip()),
        "n_tags": scoring.count_approved_tags(product, pending_tag_ids),
        "in_stock_ratio_pct": axes.get("inventory"),
    }


def apply_overrides(
    axes: Dict[str, Optional[float]],
    inputs: Dict[str, Optional[float]],
    overrides: Dict[str, Optional[float]],
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    new_axes = dict(axes)
    used = dict(inputs)
    ignored: List[str] = []

    given = {k: v for k, v in overrides.items() if k in LEVERS and v is not None}
    for key, value in given.items():
        if key == "in_stock_ratio_pct" and axes.get("inventory") is None:
            ignored.append(key)
            continue
        used[key] = value

    content_changed = any(
        k in given and k not in ignored and given[k] != inputs[k] for k in CONTENT_LEVERS
    )
    if content_changed:
        comps = scoring.content_component_scores(
            used["n_images"], used["description_length"], used["n_tags"]
        )
        new_axes["content"] = round(scoring.content_axis_score(comps), 1)
        moment = now or datetime.now(timezone.utc)
        new_axes["freshness"] = round(scoring.freshness_score({"content_changed_at": moment}, now=moment), 1)

    if "in_stock_ratio_pct" in given and "in_stock_ratio_pct" not in ignored:
        new_axes["inventory"] = round(min(100.0, max(0.0, float(used["in_stock_ratio_pct"]))), 1)

    return {"axes": new_axes, "inputs": used, "ignored": ignored}


def preview_health(
    calc: HealthScoreCalculator, product_id: str, overrides: Dict[str, Optional[float]]
) -> Optional[Dict[str, Any]]:
    current = calc.calculate(product_id)
    if current is None:
        return None

    product = calc.live_db["products"].find_one({"_id": ObjectId(product_id), **LOC_SP_THAT})
    if product is None:
        return None

    axes = current["axes"]
    inputs_now = current_inputs(product, axes, calc.pending_tag_ids())
    applied = apply_overrides(axes, inputs_now, overrides)
    new_axes = applied["axes"]
    score = scoring.total_score(new_axes)
    current_score = current.get("score")

    delta = None
    if score is not None and current_score is not None:
        delta = round(score - current_score, 1)

    return {
        "product_id": product_id,
        "score": score,
        "status": scoring.status_from_score(score) if score is not None else None,
        "axes": new_axes,
        "axes_missing": [k for k, v in new_axes.items() if v is None],
        "current_score": current_score,
        "delta_vs_current": delta,
        "inputs": applied["inputs"],
        "current_inputs": inputs_now,
        "ignored": applied["ignored"],
        "model_version": current.get("model_version"),
    }
