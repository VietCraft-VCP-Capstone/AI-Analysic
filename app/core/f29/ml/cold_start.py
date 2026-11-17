from typing import Any, Dict, Optional
from bson import ObjectId
import numpy as np

from app.api.v1._live import LOC_SP_THAT
from app.core.f29 import weights
from app.core.f29.calculator import HealthScoreCalculator
from app.core.f29.ml.scorer import load_model, _model_card


LEVERS = {"image": "photos", "description": "description_words", "tags": "tags"}


def _sigmoid(x: float) -> float:
    return float(1.0 / (1.0 + np.exp(-x)))


def _advice(product: dict, quality_res: dict, base_logit: float) -> list:
    try:
        cfg = weights.load()
    except RuntimeError:
        return []
    t, w = cfg["targets"], cfg["weights"]
    target = {"image": t["image"], "description": t.get("description_words", t["description"]), "tags": t["tags"]}
    axes = quality_res.get("axes") or {b.get("key"): b.get("sub_score") for b in quality_res.get("breakdown") or []}
    out = []
    for key, feature in LEVERS.items():
        sub = axes.get(key)
        if sub is None or sub >= 100:
            continue
        gain = _sigmoid(base_logit + 0.025 * w[key] * (100 - sub) / 100) - _sigmoid(base_logit)
        current = int(sub * target[key] / 100 + 0.5)
        out.append({"feature": feature, "current": current, "target": target[key], "gain": round(gain, 3)})
    return sorted(out, key=lambda a: -a["gain"])[:3]


def estimate_cold_start_propensity(product_id: str, live_db) -> Optional[Dict[str, Any]]:
    try:
        p_oid = ObjectId(product_id)
    except Exception:
        return None

    product = live_db["products"].find_one({"_id": p_oid})
    if not product:
        return None

    quality_res = None
    try:
        quality_res = live_db["listing_health_scores"].find_one(
            {"product_id": p_oid}, sort=[("date", -1), ("computed_at", -1)]
        )
    except Exception:
        pass

    if not quality_res:
        try:
            quality_res = live_db["product_health_scores"].find_one({"product_id": p_oid}, sort=[("date", -1)])
        except Exception:
            pass

    if not quality_res:
        try:
            calc = HealthScoreCalculator(live_db.client if hasattr(live_db, "client") else None)
            quality_res = calc.calculate(product_id)
        except Exception:
            pass

    quality_res = quality_res or {}
    try:
        raw_score = quality_res.get("score")
        quality_score = float(raw_score) if raw_score is not None else 50.0
    except Exception:
        quality_score = 50.0

    metrics = list(live_db["product_daily_metrics"].aggregate([
        {"$match": {"product_id": p_oid}},
        {"$group": {"_id": "$product_id", "views": {"$sum": "$views"}, "carts": {"$sum": "$add_to_carts"}}}
    ]))
    views = metrics[0].get("views", 0) if metrics else 0
    carts = metrics[0].get("carts", 0) if metrics else 0

    category = (product.get("categories") or ["Thủ công mỹ nghệ"])[0]

    _, meta = load_model()

    base_logit = -2.8 + 0.025 * quality_score
    if views > 0:
        cart_rate = carts / views
        base_logit += 0.3 * np.log1p(views) + 1.2 * cart_rate

    prob = float(1.0 / (1.0 + np.exp(-base_logit)))
    prob = max(0.15, min(0.95, prob))
    score_pct = int(round(prob * 100))

    advice = _advice(product, quality_res, base_logit)

    peer_count = live_db["products"].count_documents({**LOC_SP_THAT, "categories": category})
    by_category = peer_count >= 5
    if not by_category:
        peer_count = live_db["products"].count_documents(LOC_SP_THAT)

    return {
        "product_id": product_id,
        "method": "cold_start",
        "score": score_pct,
        "probability": round(prob, 3),
        "peer_group": {
            "type": "category" if by_category else "platform",
            "name": category if by_category else "Toàn sàn",
            "size": peer_count
        },
        "advice": advice,
        "compare": [],
        "model": _model_card(meta)
    }
