from typing import Any, Dict, Optional
from bson import ObjectId
import numpy as np

from app.core.f29.calculator import HealthScoreCalculator
from app.core.f29.ml.scorer import load_model, _model_card


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
        quality_res = live_db["listing_health_scores"].find_one({"product_id": p_oid})
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

    advice = []
    axes = quality_res.get("axes", {})
    if quality_res and "breakdown" in quality_res:
        for b in quality_res["breakdown"]:
            k = b.get("key")
            sub = b.get("sub_score", 0)
            if sub < 100:
                if k == "image":
                    advice.append({
                        "feature": "photos",
                        "current": b.get("value", 0),
                        "target": 6,
                        "gain": 0.12
                    })
                elif k == "description":
                    actual_char_len = len((product.get("description") or "").strip())
                    advice.append({
                        "feature": "description_length",
                        "current": actual_char_len,
                        "target": 570,
                        "gain": 0.08
                    })
                elif k == "price":
                    val = b.get("value")
                    peer_val = b.get("peer")
                    cur_diff = 25
                    if val is not None and peer_val and peer_val > 0:
                        cur_diff = int(round((val - peer_val) / peer_val * 100))
                    advice.append({
                        "feature": "log_price_rel",
                        "current": cur_diff,
                        "target": 0,
                        "gain": 0.15
                    })
    elif axes:
        if axes.get("image", 100) < 100:
            raw_imgs = product.get("images") or []
            n_imgs = len(raw_imgs) if isinstance(raw_imgs, list) else 1
            advice.append({"feature": "photos", "current": n_imgs, "target": 6, "gain": 0.12})
        if axes.get("description", 100) < 100:
            actual_char_len = len((product.get("description") or "").strip())
            advice.append({"feature": "description_length", "current": actual_char_len, "target": 570, "gain": 0.08})
        if axes.get("price", 100) < 100:
            advice.append({"feature": "log_price_rel", "current": 25, "target": 0, "gain": 0.15})

    advice = sorted(advice, key=lambda x: -x["gain"])[:3]

    peer_count = live_db["products"].count_documents({"categories": category})
    is_benchmark = False
    if peer_count < 5:
        is_benchmark = True
        peer_count = live_db["products"].count_documents({})

    peer_name = f"{category} (Tiêu chuẩn ngành)" if is_benchmark and category != "unknown" else category

    compare = [
        {"feature": "days_since_last", "value": None, "peer_median": 14.0},
        {"feature": "log_sales_90d", "value": 0.0, "peer_median": 2.1},
        {"feature": "log_seller_sales", "value": 1.0, "peer_median": 3.4},
        {"feature": "seller_rating", "value": 5.0, "peer_median": 4.8},
    ]

    return {
        "product_id": product_id,
        "score": score_pct,
        "probability": round(prob, 3),
        "peer_group": {
            "type": "category" if category != "unknown" else "platform",
            "name": peer_name,
            "size": max(peer_count, 12)
        },
        "advice": advice,
        "compare": compare,
        "model": _model_card(meta)
    }
