from datetime import datetime, timezone
from statistics import median
from typing import Any, Dict, FrozenSet, List, Optional, Tuple

from bson import ObjectId
from pymongo import MongoClient

from app.api.v1._live import LOC_SP_THAT, db_live
from app.config import settings
from app.core.f29 import basis, breakdown, factors, review_stats, scoring, weights
from app.core.f29.constants import MODEL_VERSION
from app.core.f29.factors import KEYS
from app.core.f29.price_ref import PriceRef, product_price
from app.core.f29.todos import build_todos, build_warnings, content_peer_stats


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

    def pending_tag_ids(self) -> FrozenSet:
        if self._pending_tags is None:
            self._pending_tags = frozenset(
                t["_id"] for t in self.live_db["tags"].find({"status": "pending"}, {"_id": 1}))
        return self._pending_tags

    def _get_status_from_score(self, score: float) -> str:
        return scoring.status_from_score(score)

    def _get_content_score(self, product: Dict[str, Any]) -> Tuple[Optional[float], List[Dict[str, str]]]:
        return scoring.content_score(product, self.pending_tag_ids())

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
        n_images = len(product.get("images") or [])
        desc_len = len((product.get("description") or "").strip())
        n_tags = scoring.count_approved_tags(product, pending)
        price = product_price(variants)
        ref = self._reference(product, pc)
        img_peers, desc_peers, tag_peers, _ = self._peer_stats(scoring.category_key(product))

        values = {"image": n_images, "description": desc_len, "tags": n_tags,
                  "review": n_reviews, "price": price}
        targets = {"image": t["image"], "description": t["description"], "tags": t["tags"],
                   "review": None, "price": ref["price"] * pc["full_at"]}
        peers = {"image": _median(img_peers), "description": _median(desc_peers),
                 "tags": _median(tag_peers), "review": None, "price": ref["price"]}
        subs = {
            "image": factors.ratio_score(float(n_images), float(t["image"])),
            "description": factors.ratio_score(float(desc_len), float(t["description"])),
            "tags": factors.ratio_score(float(n_tags), float(t["tags"])),
            "review": factors.review_score(n_good, n_reviews, review_stats.platform_p0(self.live_db),
                                           float(cfg["review"]["m"])),
            "price": factors.price_score(price, ref["price"], float(pc["full_at"]), float(pc["zero_at"])),
        }
        missing = {k for k in KEYS if not values[k]} | ({"price"} if ref["price"] is None else set())
        extra = {"tags": {"pending": scoring.count_pending_tags(product, pending)},
                 "review": {"n_good": n_good}, "price": {"reference": ref}}
        return breakdown.build(subs, values, targets, peers, missing, cfg["weights"], extra)

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

        now = datetime.now(timezone.utc)
        variants = list(self.live_db["product_variants"].find(
            {"product_id": product_oid},
            {"is_active": 1, "stock_quantity": 1, "retail_price": 1, "base_cost": 1},
        ))
        n_good, n_reviews = review_stats.product_counts(self.live_db, product_oid)
        rows, score = self._rows(product, variants, cfg, (n_good, n_reviews))
        infos = [{"type": "info", "field": h["field"], "message": h["message"], "current_value": None,
                  "target": None, "impact": 0} for h in self._get_content_score(product)[1]]

        return {
            "product_id": product_id,
            "title": product.get("title") or "",
            "thumbnail": (product.get("images") or [None])[0],
            "date": now.date().isoformat(),
            "score": score,
            "status": self._get_status_from_score(score),
            "axes": {r["key"]: r["sub_score"] for r in rows},
            "axes_missing": [r["key"] for r in rows if r["missing"]],
            "breakdown": rows,
            "todos": build_todos(rows),
            "warnings": self._get_warnings(product, variants) + infos,
            "computed_at": now.isoformat().replace("+00:00", "Z"),
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

        self.live_db["listing_health_scores"].update_one(
            {"product_id": product_oid, "date": date_dt},
            {"$set": doc, "$setOnInsert": {"created_at": now}},
            upsert=True,
        )
        return str(product_oid)
