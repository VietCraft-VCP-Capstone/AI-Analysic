import hashlib
import json
import math
import re
from datetime import datetime
from typing import Any, Dict, FrozenSet, List, Optional
from urllib.parse import urlparse

from app.core.f29.constants import MAX_TITLE_LENGTH, MIN_TITLE_LENGTH


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

    if len(title) < MIN_TITLE_LENGTH or len(title) > MAX_TITLE_LENGTH:
        hints.append({"field": "title", "message":
                      f"Tên sản phẩm dài {len(title)} ký tự, nên trong khoảng {MIN_TITLE_LENGTH}-{MAX_TITLE_LENGTH} ký tự"})
    if description and description.lower() == title.lower():
        hints.append({"field": "description", "message": "Mô tả đang trùng với tên sản phẩm, nên viết riêng"})
    if len({normalize_image(img) for img in images if normalize_image(img)}) < len([img for img in images if img]):
        hints.append({"field": "images", "message": "Có ảnh bị trùng, nên thay bằng ảnh góc khác"})

    return hints


def content_hash(product: Dict[str, Any]) -> str:
    content_str = f"{product.get('title')}{product.get('description')}{product.get('tags')}{product.get('images')}"
    return hashlib.md5(content_str.encode()).hexdigest()


def inputs_hash(product: Dict[str, Any], variants: List[Dict[str, Any]], n_reviews: int) -> str:
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
        "n_reviews": n_reviews,
    }
    blob = json.dumps(payload, sort_keys=True, default=_default)
    return hashlib.md5(blob.encode()).hexdigest()
