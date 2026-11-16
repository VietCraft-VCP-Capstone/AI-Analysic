import hashlib
import math
from datetime import datetime, timezone
from statistics import median
from typing import Any, Dict, FrozenSet, List, Optional, Tuple
from zoneinfo import ZoneInfo

from bson import ObjectId
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError

from app.api.v1._live import LOC_SP_THAT, db_live
from app.config import settings
from app.core.f29 import basis, breakdown, category_check, factors, material, review_stats, scoring, weights
from app.core.f29.constants import BLOCKER_CAP, BLOCKER_FIELDS, MODEL_VERSION
from app.core.f29.factors import KEYS
from app.core.f29.price_ref import PriceRef, category_of, product_price
from app.core.f29.todos import build_todos, build_warnings, content_peer_stats, price_check

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _median(values: List[int]) -> Optional[float]:
    return median(values) if values else None


class HealthScoreCalculator:
    def __init__(self, db_client: Optional[MongoClient] = None):
        if db_client is not None:
            self.client = db_client
            self.live_db = db_client[settings.MONGO_DB_LIVE]
        else:
            self.client = None
            self.live_db = db_live()
        self._pending_tags: Optional[FrozenSet] = None
        self._peers: Dict[Any, Tuple[List[int], List[int], List[int], bool]] = {}
        self._price_ref: Optional[PriceRef] = None
        self._categories: Optional[List[str]] = None

    def category_names(self) -> List[str]:
        if self._categories is None:
            self._categories = [c["name"] for c in self.live_db["categories"].find({}, {"name": 1})
                                if isinstance(c.get("name"), str)]
        return self._categories

    def _category_hint(self, product: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        cats = product.get("categories")
        current = cats[0] if isinstance(cats, list) and cats and isinstance(cats[0], str) else None
        better = category_check.better_category(product.get("title") or "", current, self.category_names())
        if not better:
            return None
        return {"type": "info", "field": "categories", "current_value": current, "target": better, "impact": 0,
                "message": f"Có danh mục “{better}” khớp với tên sản phẩm hơn “{current}”, đổi để khách lọc tìm thấy và so sánh đúng hơn"}

    def pending_tag_ids(self) -> FrozenSet:
        if self._pending_tags is None:
            tags = self.live_db["tags"]
            self._pending_tags = frozenset(
                t["_id"] for field in ("status", "review_status") for t in tags.find({field: "pending"}, {"_id": 1}))
        return self._pending_tags

    def _get_status_from_score(self, score: float) -> str:
        return scoring.status_from_score(score)

    def _get_content_hints(self, product: Dict[str, Any]) -> List[Dict[str, str]]:
        return scoring.content_hints(product, self.pending_tag_ids())

    def _get_warnings(self, product: Dict[str, Any], variants: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return build_warnings(product, variants)

    def _peer_stats(self, cat_key: Any) -> Tuple[List[int], List[int], List[int], bool]:
        if cat_key not in self._peers:
            self._peers[cat_key] = content_peer_stats(self.live_db, cat_key, self.pending_tag_ids())
        return self._peers[cat_key]

    def _reference(self, product: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        if self._price_ref is None:
            self._price_ref = PriceRef(self.live_db, params)
        return self._price_ref.reference(product)

    def _compute_inputs_hash(
        self, product: Dict[str, Any], variants: List[Dict[str, Any]], n_reviews: int
    ) -> str:
        return scoring.inputs_hash(product, variants, n_reviews)

    def _rows(self, product: Dict[str, Any], variants: List[Dict[str, Any]], cfg: Dict[str, Any],
              reviews: Tuple[int, int]) -> Tuple[List[Dict[str, Any]], float]:
        t, pc = cfg["targets"], cfg["price"]
        pending = self.pending_tag_ids()
        n_good, n_reviews = reviews
        raw_imgs = product.get("images")
        if isinstance(raw_imgs, str) and raw_imgs.strip():
            imgs = [raw_imgs]
        elif isinstance(raw_imgs, list):
            imgs = raw_imgs
        else:
            imgs = []
        unique_imgs = {scoring.normalize_image(img) for img in imgs if scoring.normalize_image(img)}
        n_images = len(unique_imgs)
        raw_desc = product.get("description")
        desc_w = factors.desc_words(raw_desc)
        target_desc = t.get("description_words", t["description"])
        n_tags = scoring.count_approved_tags(product, pending)
        price = product_price(variants)
        has_mat = material.has_material(product)
        ref = self._reference(product, pc)
        img_peers, desc_peers, tag_peers, _ = self._peer_stats(category_of(product))
        p0 = review_stats.platform_p0(self.live_db)
        m = float(cfg["review"]["m"])

        price_target, full = None, None
        if ref["comparable"]:
            full = {"low": math.ceil(ref["price"] * float(pc["low_full"]) / 1000) * 1000,
                    "high": math.floor(ref["price"] * float(pc["full_at"]) / 1000) * 1000}
            low = price is not None and price < ref["price"] * float(pc["low_full"])
            price_target = ref["price"] * float(pc["low_full"] if low else pc["full_at"])

        values = {"image": n_images, "description": desc_w, "tags": n_tags,
                  "material": int(has_mat), "review": n_reviews, "price": price}
        targets = {"image": t["image"], "description": target_desc, "tags": t["tags"],
                   "material": 1, "review": None, "price": price_target}
        peers = {"image": _median(img_peers), "description": _median(desc_peers),
                 "tags": _median(tag_peers), "material": None, "review": None, "price": ref["price"]}
        subs = {
            "image": factors.ratio_score(float(n_images), float(t["image"])),
            "description": factors.ratio_score(float(desc_w), float(target_desc)),
            "tags": factors.ratio_score(float(n_tags), float(t["tags"])),
            "material": 100.0 if has_mat else 0.0,
            "review": factors.review_score(n_good, n_reviews, p0, m),
            "price": factors.price_score(price, ref["price"], pc) if ref["comparable"] else 0.0,
        }
        unscored = {"price"} if price is not None and not ref["comparable"] else set()
        missing = {k for k in KEYS if not values[k]}
        extra = {"tags": {"pending": scoring.count_pending_tags(product, pending)},
                 "review": {"n_good": n_good, "p0": p0, "m": m},
                 "price": {"reference": ref, "full": full,
                           "suggestion": {"low": ref["low"], "high": ref["high"]} if ref["low"] else None}}
        return breakdown.build(subs, values, targets, peers, missing, cfg["weights"], extra, unscored)

    def calculate(self, product_id: str) -> Optional[Dict[str, Any]]:
        try:
            product_oid = ObjectId(product_id)
        except Exception:
            return None
        try:
            cfg = weights.load()
        except RuntimeError:
            return {"error": "no_weights"}

        product = self.live_db["products"].find_one({"_id": product_oid, **LOC_SP_THAT})
        if not product:
            return None

        now_utc = datetime.now(timezone.utc)
        now_vn = datetime.now(VN_TZ)
        variants = list(self.live_db["product_variants"].find(
            {"product_id": product_oid},
            {"is_active": 1, "stock_quantity": 1, "retail_price": 1, "base_cost": 1},
        ))
        n_good, n_reviews = review_stats.product_counts(self.live_db, product_oid)
        rows, score = self._rows(product, variants, cfg, (n_good, n_reviews))
        infos = [{"type": h.get("type", "info"), "field": h["field"], "message": h["message"], "current_value": None,
                  "target": h.get("target"), "impact": 0} for h in self._get_content_hints(product)]
        price_warning = price_check(next(r for r in rows if r["key"] == "price"))
        category_hint = self._category_hint(product)
        warnings = (self._get_warnings(product, variants) + ([price_warning] if price_warning else [])
                    + infos + ([category_hint] if category_hint else []))
        blockers = sorted({w["field"] for w in warnings if w["type"] == "warning" and w["field"] in BLOCKER_FIELDS})
        cap = {"score": BLOCKER_CAP, "raw": score, "fields": blockers} if blockers and score > BLOCKER_CAP else None
        if cap:
            score = BLOCKER_CAP

        raw_imgs = product.get("images")
        thumb = raw_imgs[0] if isinstance(raw_imgs, list) and raw_imgs else (raw_imgs if isinstance(raw_imgs, str) else None)
        return {
            "product_id": product_id,
            "title": product.get("title") or "",
            "thumbnail": thumb,
            "date": now_vn.date().isoformat(),
            "score": score,
            "status": self._get_status_from_score(score),
            "axes": {r["key"]: r["sub_score"] for r in rows},
            "axes_missing": [r["key"] for r in rows if r["missing"]],
            "breakdown": rows,
            "todos": build_todos(rows),
            "warnings": warnings,
            "cap": cap,
            "computed_at": now_utc.isoformat().replace("+00:00", "Z"),
            "model_version": MODEL_VERSION,
            "content_hash": scoring.content_hash(product),
            "inputs_hash": self._compute_inputs_hash(product, variants, n_reviews),
            "basis": basis.build(cfg),
        }

    def save(self, result: Optional[Dict[str, Any]]) -> Optional[str]:
        if not result or result.get("product_id") is None:
            return None

        try:
            product_oid = ObjectId(result["product_id"])
        except Exception:
            return None

        try:
            date_dt = datetime.strptime(result["date"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except Exception:
            date_dt = datetime.now(timezone.utc)

        computed_at_raw = result.get("computed_at")
        try:
            computed_at_dt = _parse_iso(computed_at_raw) if computed_at_raw else datetime.now(timezone.utc)
        except Exception:
            computed_at_dt = datetime.now(timezone.utc)

        now = datetime.now(timezone.utc)
        doc = {
            "product_id": product_oid,
            "date": date_dt,
            "score": result.get("score"),
            "status": result.get("status"),
            "axes": result.get("axes", {}),
            "axes_missing": result.get("axes_missing", []),
            "todos": result.get("warnings", []) + result.get("todos", []),
            "content_hash": result.get("content_hash"),
            "model_version": result.get("model_version", MODEL_VERSION),
            "computed_at": computed_at_dt,
            "inputs_hash": result.get("inputs_hash"),
            "updated_at": now,
        }

        update = {"$set": doc, "$setOnInsert": {"created_at": now}}
        scores = self.live_db["listing_health_scores"]
        try:
            scores.update_one({"product_id": product_oid, "date": date_dt}, update, upsert=True)
        except DuplicateKeyError:
            scores.update_one({"product_id": product_oid}, update)
        return str(product_oid)
