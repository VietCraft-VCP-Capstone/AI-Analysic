import re
from statistics import median
from typing import Any, Dict, List, Optional, Tuple

from bson import ObjectId

from app.api.v1._live import LOC_SP_THAT
from app.core.f29 import weights
from app.core.f29.constants import MIN_CATEGORY_SAMPLE
from app.core.f29.factors import LABELS, desc_words, review_score
from app.core.f29.material import has_material, material_conflict
from app.core.f29.price_ref import category_of
from app.core.f29.price_peers import HIGH_PCT, price_sub
from app.core.f29.scoring import normalize_image
from app.core.listing_quality.detectors.pod_content import PodContentDetector

DEFAULT_DIMS = {"length": 10, "width": 10, "height": 10}
DEFAULT_WEIGHT_G = 500
CARE = re.compile(r"\b(?:giặt|bảo quản|care|wash)\b", re.IGNORECASE)


def median_of(values: List[float]) -> float:
    return median(values) if values else 0


def image_urls(product: Dict[str, Any]) -> List[str]:
    raw = product.get("images")
    urls = [raw] if isinstance(raw, str) else raw if isinstance(raw, list) else []
    return [u for u in urls if isinstance(u, str) and u.strip()]


def image_count(product: Dict[str, Any]) -> int:
    return len({normalize_image(u) for u in image_urls(product)} - {""})


def _peers(live_db, product: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], bool]:
    category = category_of(product)
    coll, fields = live_db["products"], {"images": 1, "description": 1}
    not_me = {"_id": {"$ne": product.get("_id")}}
    if category is not None:
        peers = list(coll.find({**LOC_SP_THAT, **not_me, "categories.0": category}, fields))
        cat_id = ObjectId(category) if ObjectId.is_valid(category) else category
        peers = peers or list(coll.find({**LOC_SP_THAT, **not_me, "category_ids.0": cat_id}, fields))
        if len(peers) >= MIN_CATEGORY_SAMPLE:
            return peers, True
    return list(coll.find({**LOC_SP_THAT, **not_me}, fields)), False


def peer_medians(live_db, product: Dict[str, Any]) -> Tuple[float, float, bool]:
    peers, in_category = _peers(live_db, product)
    return (median_of([image_count(p) for p in peers]),
            median_of([desc_words(p.get("description")) for p in peers]), in_category)


def has_size(product: Dict[str, Any], text: str) -> bool:
    dims, weight = product.get("dimensions_cm"), product.get("weight_g")
    if isinstance(dims, dict) and dims and dims != DEFAULT_DIMS:
        return True
    if weight and weight != DEFAULT_WEIGHT_G:
        return True
    return any(re.search(p, text, re.IGNORECASE) for p in PodContentDetector.SIZE_KEYWORDS)


def _row(key: str, state: str, sub: Optional[float], method: str, reason: str,
         evidence: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    counted, weight = sub is not None, weights.load()["weights"][key]
    return {"key": key, "label": LABELS[key], "weight": weight, "state": state,
            "points": round(weight * sub / 100, 1) if counted else 0.0,
            "sub_score": round(sub, 1) if counted else None,
            "method": method, "reason": reason, "evidence": evidence or {}}


def image_row(analysis: Dict[str, Any], median_images: float, in_category: bool = False) -> Dict[str, Any]:
    state, useful = analysis["state"], analysis["useful"]
    if state == "seller_missing":
        return _row("image", state, 0.0, "heuristic", "Chưa có ảnh")
    unanalyzed = analysis.get("unanalyzed", 0)
    evidence = {"useful": useful, "unanalyzed": unanalyzed, "images": analysis.get("images", []),
                "siglip": analysis.get("method") == "ml_unvalidated"}
    if state == "technical_failure":
        return _row("image", state, None, "heuristic", "Không tải được ảnh, tạm không tính mục này", evidence)
    target = max(median_images, 1)
    reason = f"Có {useful} ảnh đạt, sản phẩm cùng loại thường có {target:g} ảnh"
    if unanalyzed:
        reason += f" ({unanalyzed} ảnh chưa phân tích được, tạm tính theo đường dẫn)"
    evidence.update(target=target, median=median_images, in_category=in_category)
    return _row("image", "scored", min(1, useful / target) * 100, "heuristic", reason, evidence)


def description_row(product: Dict[str, Any], median_words: float, in_category: bool = False) -> Dict[str, Any]:
    raw = product.get("description")
    text = raw.strip() if isinstance(raw, str) else ""
    if not text:
        return _row("description", "seller_missing", 0.0, "rule", "Chưa có mô tả",
                    {"median_words": median_words, "in_category": in_category})
    checks = {
        "words": desc_words(text) >= median_words,
        "size": has_size(product, text),
        "material": has_material(product) and material_conflict(product) is None,
        "not_title": text.lower() != str(product.get("title") or "").strip().lower(),
    }
    passed = sum(checks.values())
    evidence = {"checks": checks, "median_words": median_words, "in_category": in_category,
                "words": desc_words(text), "care": bool(CARE.search(text))}
    return _row("description", "scored", passed / len(checks) * 100, "rule",
                f"Đạt {passed}/{len(checks)} tiêu chí mô tả", evidence)


def tags_row(approved: int, pending: int, queries: List[Dict[str, Any]], method: str) -> Dict[str, Any]:
    has_tag = 100.0 if approved >= 1 else 0.0
    total = sum(q["searches"] for q in queries)
    share = sum(q["searches"] for q in queries if q["covered"]) * 100 / total if total else None
    sub = has_tag if share is None else 0.5 * has_tag + 0.5 * share
    reason = f"{approved} tag đã duyệt"
    if share is not None:
        reason += f", phủ {share:.0f}% lượt tìm trong danh mục"
    return _row("tags", "scored", sub, method, reason,
                {"approved": approved, "pending": pending, "coverage": None if share is None else round(share, 1)})


def review_row(n_good: int, n: int, p0: float, m: float) -> Dict[str, Any]:
    if n == 0:
        return _row("review", "not_applicable", None, "rule", "Chưa có đánh giá")
    return _row("review", "scored", review_score(n_good, n, p0, m), "rule",
                f"{n_good}/{n} đánh giá tốt", {"good": n_good, "total": n, "p0": p0, "m": m})


def price_reason(pct: float, n: int, factor: float = 1.0, reasons=()) -> str:
    if pct < 0.5:
        text = f"Rẻ nhất trong {n} sản phẩm cùng loại"
    elif pct > 99.5:
        text = f"Đắt nhất trong {n} sản phẩm cùng loại"
    elif pct < 50:
        text = f"Rẻ hơn {100 - pct:.0f}% trong {n} sản phẩm cùng loại"
    else:
        text = f"Đắt hơn {pct:.0f}% trong {n} sản phẩm cùng loại"
    if factor != 1.0:
        text += ", đã quy đổi theo chất liệu"
    if pct > HIGH_PCT:
        text += ", có nêu lý do giá" if reasons else ", chưa nêu lý do giá cao"
    return text


def price_row(pos: Dict[str, Any], reasons=()) -> Dict[str, Any]:
    state = pos["state"]
    if state == "seller_missing":
        return _row("price", state, 0.0, "rule", "Chưa có giá bán")
    if state == "not_applicable":
        return _row("price", state, None, "rule", "Chưa đủ sản phẩm cùng loại để so giá", {"peers": pos["n"]})
    evidence = {k: pos[k] for k in ("pct", "n", "factor", "confidence", "p10", "p90")} | {"reasons": list(reasons)}
    return _row("price", "scored", price_sub(pos["pct"], reasons, pos["confidence"]), "rule",
                price_reason(pos["pct"], pos["n"], pos["factor"], reasons), evidence)
