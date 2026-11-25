from typing import Any, Dict, Optional

from bson import ObjectId

from app.api.v1._live import LOC_SP_THAT
from app.core.f29.score import scoring
from app.core.f29.score import factors as f3
from app.core.f29.score import price
from app.core.f29.score.calculator import HealthScoreCalculator
from app.core.f29.checks import run
from app.core.f29.score.factors import price_reasons

LEVERS = ("n_images", "description_length", "n_tags", "price")


def _image(row: Dict[str, Any], n: int, median: float, in_category: bool) -> Dict[str, Any]:
    state = "seller_missing" if n == 0 else "scored"
    ev = row["evidence"]
    analysis = {"state": state, "useful": n, "method": row["method"], "images": ev.get("images", []),
                "unanalyzed": ev.get("unanalyzed", 0)}
    return f3.image_row(analysis, median, in_category)


def _learn(row: Dict[str, Any], old: Dict[str, Any]) -> Dict[str, Any]:
    ev = old["evidence"]
    return scoring.rescore(row, ev.get("peers", []), ev.get("level", "all"))


def _description(product: Dict[str, Any], row: Dict[str, Any], words: int, median: float,
                 in_category: bool) -> Dict[str, Any]:
    if row["state"] == "seller_missing":
        text = " ".join(f"w{i}x" for i in range(words))
        return f3.description_row({**product, "description": text}, median, in_category)
    checks = {**row["evidence"]["checks"], "words": words >= median}
    passed = sum(checks.values())
    return f3._row("description", "scored", passed / len(checks) * 100, "rule",
                   f"Đạt {passed}/{len(checks)} tiêu chí mô tả", {**row["evidence"], "checks": checks, "words": words})


def preview_health(
    calc: HealthScoreCalculator, product_id: str, overrides: Dict[str, Optional[float]]
) -> Optional[Dict[str, Any]]:
    current = calc.stored_result(product_id) or calc.calculate(product_id)
    if current is None or "error" in current:
        return current

    product = calc.live_db["products"].find_one({"_id": ObjectId(product_id), **LOC_SP_THAT})
    median_images, median_words, in_category = f3.peer_medians(calc.live_db, product)
    rows = {r["key"]: r for r in current["factors"]}
    snap = current["content_snapshot"]
    now_in = {"n_images": snap["n_images"], "description_length": snap["desc_words"],
              "n_tags": rows["tags"]["evidence"]["approved"], "price": snap["price"]}
    given = {k: v for k, v in overrides.items() if v is not None}
    levers = {k: v for k, v in given.items() if k in LEVERS}
    used = {**now_in, **levers}

    old = dict(rows)
    if "n_images" in levers:
        image = _image(rows["image"], round(levers["n_images"]), median_images, in_category)
        rows["image"] = _learn(run.apply([image], current["checks"])[0], old["image"])
    if "description_length" in levers:
        rows["description"] = _learn(_description(product, rows["description"], round(levers["description_length"]),
                                                  median_words, in_category), old["description"])
    if "n_tags" in levers:
        rows["tags"] = _learn(f3.tags_row(round(levers["n_tags"]), rows["tags"]["evidence"]["pending"],
                                          current["search"]["queries"], "rule"), old["tags"])
    if "price" in levers:
        rows["price"] = _learn(f3.price_row(price.position(calc.live_db, product, levers["price"]),
                                            price_reasons(product, calc._copied_description(product))), old["price"])

    factors = list(rows.values())
    score, coverage = scoring.score(factors)
    return {
        "product_id": product_id,
        "score": score,
        "status": scoring.status_from_score(score),
        "coverage": coverage,
        "axes": {r["key"]: r["sub_score"] for r in factors},
        "axes_missing": [r["key"] for r in factors if r["state"] != "scored"],
        "current_score": current["score"],
        "delta_vs_current": round(score - current["score"], 1),
        "inputs": used,
        "current_inputs": now_in,
        "ignored": [k for k in given if k not in LEVERS],
        "model_version": current["model_version"],
    }
