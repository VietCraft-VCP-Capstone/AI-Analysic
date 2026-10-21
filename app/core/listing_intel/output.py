import math
from datetime import date, datetime

import numpy as np

from . import fusion

AXES = ("image", "text", "tags", "market", "trend")
FLAT = 0.05


def jsonable(obj):
    if isinstance(obj, dict):
        return {str(k): jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [jsonable(v) for v in obj]
    if isinstance(obj, np.generic):
        obj = obj.item()
    if isinstance(obj, float):
        return round(obj, 4) if math.isfinite(obj) else None
    if isinstance(obj, datetime) and obj.tzinfo is None:
        return obj.isoformat() + "Z"
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    return obj


def _r(x, nd=1):
    return None if x is None or not math.isfinite(x) else round(float(x), nd)


def _axis(res, evidence) -> dict:
    out = {"score": _r(res.score), "evidence": evidence, "metrics": res.features, "issues": res.issues}
    return {**out, "missing_reason": res.missing_reason} if res.missing_reason else out


def _trained_on(t) -> str:
    if isinstance(t, str) or not t:
        return t or ""
    parts = ", ".join(f"{s}: {v['rows']} dòng" for s, v in (t.get("by_source") or {}).items())
    return f"{t.get('rows')} listing ({parts}), {t.get('split', '')}, {t.get('date', '')}".strip(", ")


def model_card(meta: dict) -> dict:
    test = (meta.get("metrics") or {}).get("test") or {}
    ci = test.get("auc_ci95") or [None, None]
    best = meta.get("best_baseline") or {}
    return {"version": meta.get("model_version"), "auc": test.get("roc_auc"), "auc_ci95": [ci[0], ci[1]],
            "best_baseline": {"name": best.get("name") or "", "auc": best.get("auc")},
            "trained_on": _trained_on(meta.get("trained_on"))}


def direction(timeline: list[dict]):
    if not timeline:
        return None
    d = timeline[-1]["demand_factor"] - timeline[0]["demand_factor"]
    return "up" if d > FLAT else "down" if d < -FLAT else "flat"


def listing_intel(parts, base, timeline, material, advice, evidence, at) -> dict:
    inp, h = parts["inp"], parts["feats"]["trend_factor"]
    return jsonable({
        "score": float(np.clip(base * h, 0, 100)),
        "base": base,
        "demand_factor": h,
        "score_timeline": timeline,
        "axes": {a: _axis(parts["results"][a], evidence.get(a, "practice")) for a in AXES},
        "material": material,
        "keywords": parts["keywords"],
        "tags": parts["verdicts"],
        "suggested_tags": parts["suggestions"],
        "images": parts["images"],
        "market": parts["market"],
        "advice": advice,
        "peers": parts["peers"],
        "model": model_card(fusion.load_bundle().meta),
        "title": inp.title,
        "thumbnail": (inp.image_urls or [None])[0],
        **({"product_id": inp.product_id} if inp.product_id else {}),
        "date": at,
        "capped_reason": None if inp.image_urls else "no_images",
    })


def score_doc(out: dict) -> dict:
    return {
        "product_id": out["product_id"], "date": out["date"], "model_version": out["model"]["version"],
        "score": out["score"], "base": out["base"], "demand_factor": out["demand_factor"],
        "axes": {a: out["axes"][a]["score"] for a in AXES},
        "trend_direction": direction(out["score_timeline"]),
        "title": out["title"], "thumbnail": out["thumbnail"],
    }
