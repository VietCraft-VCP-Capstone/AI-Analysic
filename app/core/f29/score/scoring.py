import hashlib
import json
import math
import re
from datetime import datetime
from typing import Any, Dict, FrozenSet, List, Optional, Tuple
from urllib.parse import urlparse

import numpy as np

from app.core.f29.score import text_rules
from app.core.f29.constants import review_score


def pct(value: float, peers) -> float:
    a = np.sort(np.asarray(peers, dtype=float))
    if len(a) == 0:
        return 0.5
    lo, hi = np.searchsorted(a, value, "left"), np.searchsorted(a, value, "right")
    return float((lo + hi) / (2 * len(a)))


def pct_within(values, groups) -> np.ndarray:
    values, groups = np.asarray(values, dtype=float), np.asarray(groups, dtype=str)
    out = np.full(len(values), 0.5)
    for g in np.unique(groups):
        idx = np.flatnonzero(groups == g)
        if len(idx) < 2:
            continue
        a = np.sort(values[idx])
        lo, hi = np.searchsorted(a, values[idx], "left"), np.searchsorted(a, values[idx], "right")
        out[idx] = (lo + hi - 1) / (2 * (len(idx) - 1))
    return out


def status_from_score(score: float) -> str:
    if score >= 80:
        return "good"
    if score >= 50:
        return "needs_improvement"
    return "poor"


def to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        val = float(str(value))
        if not math.isfinite(val):
            return None
        return val
    except (TypeError, ValueError):
        return None


def count_approved_tags(product: Dict[str, Any], pending_tag_ids: FrozenSet = frozenset()) -> int:
    tag_ids = product.get("tag_ids") or []
    if tag_ids:
        return sum(1 for t in tag_ids if t not in pending_tag_ids)
    return len([t for t in (product.get("tags") or []) if isinstance(t, str) and t.strip()])


def count_pending_tags(product: Dict[str, Any], pending_tag_ids: FrozenSet) -> int:
    return sum(1 for t in (product.get("tag_ids") or []) if t in pending_tag_ids)


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _images(raw: Any) -> List[Any]:
    if isinstance(raw, str):
        return [raw] if raw.strip() else []
    return raw if isinstance(raw, list) else []


def normalize_image(img: Any) -> str:
    if not img:
        return ""
    if isinstance(img, dict):
        url = str(img.get("url") or img.get("src") or img.get("secure_url") or "").strip()
    else:
        url = str(img).strip()
    if not url:
        return ""
    url_clean = url.split("?")[0].split("#")[0]
    if "/image/upload/" in url_clean:
        rest = url_clean.split("/image/upload/", 1)[1]
        parts = [p for p in rest.split("/") if p]
        while parts and ("," in parts[0] or re.match(r"^[a-z]{1,3}_", parts[0]) or re.match(r"^v\d+$", parts[0])):
            parts.pop(0)
        return re.sub(r"\.[a-zA-Z0-9]+$", "", "/".join(parts))
    try:
        p = urlparse(url_clean)
        if p.scheme and p.netloc:
            path_no_ext = re.sub(r"\.[a-zA-Z0-9]+$", "", p.path.rstrip("/"))
            return f"{p.netloc.lower()}{path_no_ext}"
    except Exception:
        pass
    return re.sub(r"\.[a-zA-Z0-9]+$", "", url_clean)


def content_hints(
    product: Dict[str, Any], pending_tag_ids: FrozenSet = frozenset()
) -> List[Dict[str, str]]:
    hints: List[Dict[str, str]] = []
    images = _images(product.get("images"))
    description = _text(product.get("description"))
    title = _text(product.get("title"))

    hints.extend(text_rules.check(title))
    conflict = text_rules.material_conflict(product)
    if conflict:
        said, named = (", ".join(x) for x in conflict)
        hints.append({"type": "warning", "field": "materials", "message":
                      f"Chất liệu không khớp tên sản phẩm: ô Chất liệu ghi “{said}”, tên ghi “{named}”"})
    if description and description.lower() == title.lower():
        hints.append({"field": "description", "message": "Mô tả đang trùng với tên sản phẩm, nên viết riêng"})
    if len({normalize_image(img) for img in images if normalize_image(img)}) < len([img for img in images if img]):
        hints.append({"field": "images", "message": "Có ảnh bị trùng, nên thay bằng ảnh góc khác"})

    return hints


def content_hash(product: Dict[str, Any]) -> str:
    content_str = f"{product.get('title')}{product.get('description')}{product.get('tags')}{product.get('images')}"
    return hashlib.md5(content_str.encode()).hexdigest()


def inputs_hash(product: Dict[str, Any], variants: List[Dict[str, Any]], reviews: Tuple[int, int],
                versions: Optional[Dict[str, Any]] = None) -> str:
    def _default(o: Any) -> Any:
        if isinstance(o, datetime):
            return o.isoformat()
        return str(o)

    payload = {
        "product": {
            "title": product.get("title"),
            "description": product.get("description"),
            "tags": product.get("tags"),
            "materials": product.get("materials"),
            "images": product.get("images"),
            "categories": product.get("categories"),
            "category_ids": [str(c) for c in (product.get("category_ids") or [])],
            "product_type": product.get("product_type"),
            "moderation_status": product.get("moderation_status"),
            "weight_g": product.get("weight_g"),
            "dimensions_cm": product.get("dimensions_cm"),
            "updated_at": product.get("updated_at"),
        },
        "variants": sorted((
            {
                "id": str(v.get("_id")),
                "is_active": v.get("is_active"),
                "stock_quantity": v.get("stock_quantity"),
                "retail_price": to_float(v.get("retail_price")),
                "base_cost": to_float(v.get("base_cost")),
            }
            for v in variants
        ), key=lambda d: d["id"]),
        "reviews": list(reviews),
        "design_placements": sorted(json.dumps(p, sort_keys=True, default=str)
                                    for p in product.get("design_placements") or []),
        "blank_id": product.get("blank_id"),
        "active_colors": sorted(v["color"] for v in variants if v.get("is_active") and v.get("color")),
        "checks": versions or {},
    }
    blob = json.dumps(payload, sort_keys=True, default=_default)
    return hashlib.md5(blob.encode()).hexdigest()


COUNTED = ("scored", "seller_missing")


def score(factors: List[Dict[str, Any]]) -> Tuple[float, Dict[str, int]]:
    counted = [f for f in factors if f["state"] in COUNTED]
    budget = sum(f["weight"] for f in counted)
    value = round(sum(f["points"] for f in counted) * 100 / budget, 1) if budget else 0.0
    return value, {"evaluated": len(counted), "total": len(factors)}


MIN_REVIEW_PEERS = 5
LEVEL_LABEL = {"category": "cùng danh mục", "group": "cùng nhóm hàng", "all": "toàn sàn"}
VALUE_KEY = {"image": "useful", "description": "words", "tags": "approved"}
DESC_INFO = ("size", "material", "not_title")


def _value(row: Dict[str, Any]) -> float:
    if row["key"] == "price":
        return 1 - row["evidence"]["pct"] / 100
    if row["key"] == "review":
        ev = row["evidence"]
        return review_score(ev["good"], ev["total"], ev["p0"], ev["m"])
    return row["evidence"].get(VALUE_KEY[row["key"]], 0)


def _sub(row: Dict[str, Any], value: float, peers: List[float]) -> float:
    if row["state"] == "seller_missing" or (row["key"] in VALUE_KEY and not value):
        return 0.0
    if row["key"] == "price":
        return value * 100
    return pct(value, peers) * 100


def _too_few_reviews(row: Dict[str, Any], peers: List[float]) -> bool:
    return row["key"] == "review" and len(peers) < MIN_REVIEW_PEERS


def rescore(row: Dict[str, Any], peers: List[float], level: str) -> Dict[str, Any]:
    if row["state"] not in COUNTED or (row["key"] == "price" and row["state"] != "scored"):
        return row
    if _too_few_reviews(row, peers):
        return {**row, "state": "not_applicable", "sub_score": None, "points": 0.0, "method": "learned",
                "reason": f"{row['reason']}; chưa đủ tin có đánh giá để so"}
    value = _value(row)
    sub = _sub(row, value, peers)
    reason = row["reason"]
    evidence = {**row["evidence"], "value": value, "peers": sorted(peers), "level": level}
    if row["key"] == "description":
        checks = row["evidence"].get("checks", {})
        info = sum(bool(checks.get(k)) for k in DESC_INFO) / len(DESC_INFO) * 100
        evidence.update(length_sub=round(sub, 1), criteria_sub=round(info, 1))
        if row["state"] == "scored":
            reason += f"; dài hơn {sub:.0f}% tin {LEVEL_LABEL[level]}"
        sub = 0.5 * sub + 0.5 * info
    elif row["state"] == "scored" and row["key"] != "price":
        reason += f"; hơn {sub:.0f}% tin {LEVEL_LABEL[level]}"
    return {**row, "sub_score": round(sub, 1), "points": round(row["weight"] * sub / 100, 1),
            "method": "learned", "reason": reason, "evidence": evidence}


def rescore_all(rows: List[Dict[str, Any]], values: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [rescore(r, values.get(r["key"], []), values["level"]) for r in rows]


def gain(row: Dict[str, Any], new_value: float) -> float:
    ev = row["evidence"]
    if "peers" not in ev or row["key"] == "price":
        return 0.0
    new = pct(new_value, ev["peers"]) * 100
    if row["key"] == "description":
        return max(0.0, round(row["weight"] * 0.5 * (new - ev.get("length_sub", 0.0)) / 100, 1))
    return max(0.0, round(row["weight"] * (new - (row["sub_score"] or 0.0)) / 100, 1))


def confidence(rows: List[Dict[str, Any]], n_peers: int) -> Dict[str, Any]:
    counted = sum(r["state"] in COUNTED for r in rows)
    image: Optional[Dict[str, Any]] = next((r for r in rows if r["key"] == "image"), None)
    unanalyzed = (image or {}).get("evidence", {}).get("unanalyzed", 0)
    if counted < 3 or unanalyzed or n_peers < 5:
        level = "Thấp"
    elif counted < len(rows) or n_peers < 10:
        level = "Vừa"
    else:
        level = "Cao"
    return {"level": level, "factors": f"{counted}/{len(rows)}", "peers": n_peers}
