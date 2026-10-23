import math
import hashlib
import json
from datetime import datetime, timezone
from statistics import median
from typing import Any, Dict, FrozenSet, List, Optional, Tuple

from app.core.f29.constants import (
    FRESHNESS_FULL_SCORE_DAYS,
    FRESHNESS_ZERO_SCORE_DAYS,
    K_BAYESIAN_SHRINKAGE,
    MAX_TITLE_LENGTH,
    MIN_DESCRIPTION_LENGTH,
    MIN_IMAGES,
    MIN_TAGS_APPROVED,
    MIN_TITLE_LENGTH,
    WEIGHTS,
)


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


def category_key(product: Dict[str, Any]) -> Optional[Any]:
    cat_ids = product.get("category_ids") or []
    return cat_ids[0] if cat_ids else None


def median_or(values: List[float], default: float) -> float:
    return median(values) if values else default


def count_approved_tags(product: Dict[str, Any], pending_tag_ids: FrozenSet = frozenset()) -> int:
    tag_ids = product.get("tag_ids") or []
    if tag_ids:
        return sum(1 for t in tag_ids if t not in pending_tag_ids)
    return len([t for t in (product.get("tags") or []) if isinstance(t, str) and t.strip()])


def count_pending_tags(product: Dict[str, Any], pending_tag_ids: FrozenSet) -> int:
    return sum(1 for t in (product.get("tag_ids") or []) if t in pending_tag_ids)


def total_score(axes: Dict[str, Optional[float]]) -> Optional[float]:
    valid = {k: v for k, v in axes.items() if v is not None}
    if not valid:
        return None
    weights = {k: WEIGHTS[k] for k in valid}
    total_weight = sum(weights.values())
    return round(sum(valid[k] * weights[k] / total_weight for k in valid), 1)


def bayes_shrunk_rating(sum_stars: float, n: int, prior_mean: float,
                        m: int = K_BAYESIAN_SHRINKAGE) -> Optional[float]:
    if n <= 0:
        return None
    return (sum_stars + m * prior_mean) / (n + m)


def rating_axis_score(shrunk_rating: float) -> float:
    return min(100.0, max(0.0, (shrunk_rating - 1.0) / 4.0 * 100.0))


def _ratio_score(value: float, target: float) -> float:
    if value <= 0:
        return 0.0
    if value >= target:
        return 100.0
    return value / target * 100.0


def content_component_scores(n_images: Optional[float], desc_len: Optional[float],
                             n_tags: Optional[float]) -> Dict[str, float]:
    raw = {"images": (n_images, MIN_IMAGES),
           "description": (desc_len, MIN_DESCRIPTION_LENGTH),
           "tags": (n_tags, MIN_TAGS_APPROVED)}
    return {k: _ratio_score(v, target) for k, (v, target) in raw.items() if v is not None}


def content_axis_score(components: Dict[str, float]) -> Optional[float]:
    if not components:
        return None
    return min(100.0, max(0.0, sum(components.values()) / len(components)))


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
    try:
        from urllib.parse import urlparse
        p = urlparse(url)
        if p.scheme and p.netloc:
            return f"{p.netloc.lower()}{p.path.rstrip('/')}"
    except Exception:
        pass
    return url


def content_score(
    product: Dict[str, Any], pending_tag_ids: FrozenSet = frozenset()
) -> Tuple[Optional[float], List[Dict[str, str]]]:
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

    n_tags = count_approved_tags(product, pending_tag_ids)
    score = content_axis_score(content_component_scores(len(images), len(description), n_tags))
    return score, hints


def inventory_score(product: Dict[str, Any], variants: List[Dict[str, Any]]) -> Optional[float]:
    if not product or product.get("product_type") != "READY_TO_SHIP":
        return None

    active = [v for v in variants if v.get("is_active", True)]
    if not active:
        return None

    in_stock = sum(1 for v in active if int(v.get("stock_quantity") or 0) > 0)
    return in_stock / len(active) * 100.0


def freshness_score(product: Dict[str, Any], now: Optional[datetime] = None) -> float:
    now = now or datetime.now(timezone.utc)

    changed_at = product.get("content_changed_at") or product.get("updated_at")
    if not changed_at:
        return 100.0

    if isinstance(changed_at, str):
        try:
            changed_at = datetime.fromisoformat(changed_at.replace('Z', '+00:00'))
        except Exception:
            return 100.0

    if not isinstance(changed_at, datetime):
        return 100.0

    if changed_at.tzinfo is None:
        changed_at = changed_at.replace(tzinfo=timezone.utc)

    days_since_change = (now - changed_at).days

    if days_since_change <= FRESHNESS_FULL_SCORE_DAYS:
        return 100.0
    if days_since_change >= FRESHNESS_ZERO_SCORE_DAYS:
        return 0.0
    fraction = (days_since_change - FRESHNESS_FULL_SCORE_DAYS) / (
        FRESHNESS_ZERO_SCORE_DAYS - FRESHNESS_FULL_SCORE_DAYS
    )
    return 100.0 * (1.0 - fraction)


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
