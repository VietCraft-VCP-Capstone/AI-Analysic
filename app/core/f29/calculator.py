from datetime import datetime, timezone
from typing import Any, Dict, FrozenSet, List, Optional, Tuple

from bson import ObjectId
from pymongo import MongoClient

from app.api.v1._live import LOC_DON_THAT, LOC_SP_THAT, db_live
from app.config import settings
from app.core.f29 import scoring
from app.core.f29.constants import MODEL_VERSION
from app.core.f29.conversion import conversion_score, conversion_stats
from app.core.f29.todos import build_sales_warnings, build_todos, build_warnings


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class HealthScoreCalculator:
    def __init__(self, db_client: Optional[MongoClient] = None):
        if db_client is not None:
            self.client = db_client
            self.live_db = db_client[settings.MONGO_DB_LIVE]
        else:
            self.client = None
            self.live_db = db_live()
        self._conv_cache: Optional[Dict[str, Any]] = None
        self._pending_tags: Optional[FrozenSet] = None

    def pending_tag_ids(self) -> FrozenSet:
        if self._pending_tags is None:
            self._pending_tags = frozenset(
                t["_id"] for t in self.live_db["tags"].find({"status": "pending"}, {"_id": 1}))
        return self._pending_tags

    def _get_status_from_score(self, score: float) -> str:
        return scoring.status_from_score(score)

    def _to_float(self, value: Any) -> Optional[float]:
        return scoring.to_float(value)

    def _content_component_scores(self, n_images: int, desc_len: int, n_tags: int) -> Dict[str, float]:
        return scoring.content_component_scores(n_images, desc_len, n_tags)

    def _get_content_score(self, product: Dict[str, Any]) -> Tuple[Optional[float], List[Dict[str, str]]]:
        return scoring.content_score(product, self.pending_tag_ids())

    def _get_inventory_score(self, product: Dict[str, Any], variants: List[Dict[str, Any]]) -> Optional[float]:
        return scoring.inventory_score(product, variants)

    def _get_freshness_score(self, product: Dict[str, Any], content_hash: Optional[str] = None) -> float:
        return scoring.freshness_score(product)

    def _total_score(self, axes: Dict[str, Optional[float]]) -> Optional[float]:
        return scoring.total_score(axes)

    def _get_warnings(self, product: Dict[str, Any], variants: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return build_warnings(product, variants)

    def _get_todos(
        self,
        product: Dict[str, Any],
        axes: Dict[str, Optional[float]],
        n_images: int,
        desc_len: int,
        n_tags: int,
        inventory_ratio_pct: Optional[float],
    ) -> List[Dict[str, Any]]:
        return build_todos(self.live_db, product, axes, n_images, desc_len, n_tags, inventory_ratio_pct,
                           self.pending_tag_ids())

    def _conversion_stats(self) -> Dict[str, Any]:
        if self._conv_cache is None:
            self._conv_cache = conversion_stats(self.live_db)
        return self._conv_cache

    def _get_conversion(self, product_id: str) -> Tuple[Optional[float], Dict[str, Any]]:
        return conversion_score(self._conversion_stats(), product_id)

    def _get_conversion_score(self, product_id: str) -> Optional[float]:
        return self._get_conversion(product_id)[0]

    def _get_rating_score(self, product_id: str) -> Tuple[Optional[float], Optional[int]]:
        try:
            product_oid = ObjectId(product_id)
        except Exception:
            return None, None

        reviews_coll = self.live_db["reviews"]
        valid_order_ids = [o["_id"] for o in self.live_db["orders"].find(LOC_DON_THAT, {"_id": 1})]

        reviews = list(reviews_coll.find(
            {"product_id": product_oid, "order_id": {"$in": valid_order_ids}}, {"rating": 1}
        ))
        n = len(reviews)
        if n == 0:
            return None, None

        all_reviews = list(reviews_coll.find({"order_id": {"$in": valid_order_ids}}, {"rating": 1}))
        avg_all = sum(r.get("rating", 0) for r in all_reviews) / len(all_reviews) if all_reviews else 3.0

        sum_ratings = sum(r.get("rating", 0) for r in reviews)
        shrunk_rating = scoring.bayes_shrunk_rating(sum_ratings, n, avg_all)
        return scoring.rating_axis_score(shrunk_rating), n

    def _compute_inputs_hash(
        self, product: Dict[str, Any], variants: List[Dict[str, Any]], n_reviews: int
    ) -> str:
        return scoring.inputs_hash(product, variants, n_reviews)

    def _content_changed_at(self, product_oid: ObjectId, product: Dict[str, Any],
                            content_hash: str, now: datetime) -> Any:
        prev = self.live_db["listing_health_scores"].find_one(
            {"product_id": product_oid}, sort=[("date", -1)]
        )
        if prev is not None and prev.get("content_hash") == content_hash and prev.get("content_changed_at"):
            return prev["content_changed_at"]
        if prev is not None:
            return now
        return product.get("updated_at") or now

    def calculate(self, product_id: str) -> Optional[Dict[str, Any]]:
        try:
            product_oid = ObjectId(product_id)
        except Exception:
            return None

        product = self.live_db["products"].find_one({"_id": product_oid, **LOC_SP_THAT})
        if not product:
            return None

        now = datetime.now(timezone.utc)

        variants = list(self.live_db["product_variants"].find(
            {"product_id": product_oid},
            {"is_active": 1, "stock_quantity": 1, "retail_price": 1, "base_cost": 1},
        ))

        axes: Dict[str, Optional[float]] = {}
        axes_missing: List[str] = []

        def set_axis(name: str, value: Optional[float], ndigits: Optional[int] = 1) -> None:
            if value is None:
                axes[name] = None
                axes_missing.append(name)
            else:
                axes[name] = round(value, ndigits) if ndigits is not None else value

        rating_score, n_reviews = self._get_rating_score(product_id)
        set_axis("rating", rating_score)

        content_score, content_warnings = self._get_content_score(product)
        n_images = len(product.get("images") or [])
        desc_len = len((product.get("description") or "").strip())
        n_tags = scoring.count_approved_tags(product, self.pending_tag_ids())
        set_axis("content", content_score)

        inventory_raw = self._get_inventory_score(product, variants)
        set_axis("inventory", inventory_raw)

        content_hash = scoring.content_hash(product)
        content_changed_at = self._content_changed_at(product_oid, product, content_hash, now)
        freshness = self._get_freshness_score({**product, "content_changed_at": content_changed_at})
        axes["freshness"] = round(freshness, 1)

        conversion, conversion_detail = self._get_conversion(product_id)
        set_axis("conversion", conversion, ndigits=None)

        warnings = self._get_warnings(product, variants) + build_sales_warnings(
            product, conversion_detail, conversion, now)
        content_infos = [
            {"type": "info", "field": h["field"], "message": h["message"], "current_value": None,
             "target": None, "impact": 0}
            for h in content_warnings
        ]

        total = self._total_score(axes)
        if total is None:
            status, todos = None, []
        else:
            status = self._get_status_from_score(total)
            todos = self._get_todos(product, axes, n_images, desc_len, n_tags, inventory_raw)

        return {
            "product_id": product_id,
            "date": now.date().isoformat(),
            "score": total,
            "status": status,
            "axes": axes,
            "axes_missing": axes_missing,
            "todos": warnings + todos + content_infos,
            "computed_at": now.isoformat().replace("+00:00", "Z"),
            "model_version": MODEL_VERSION,
            "content_hash": content_hash,
            "content_changed_at": content_changed_at,
            "inputs_hash": self._compute_inputs_hash(product, variants, n_reviews or 0),
            "conversion_detail": conversion_detail,
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

        content_changed_at = result.get("content_changed_at")
        if isinstance(content_changed_at, str):
            try:
                content_changed_at = _parse_iso(content_changed_at)
            except Exception:
                content_changed_at = None

        now = datetime.now(timezone.utc)
        doc = {
            "product_id": product_oid,
            "date": date_dt,
            "score": result.get("score"),
            "status": result.get("status"),
            "axes": result.get("axes", {}),
            "axes_missing": result.get("axes_missing", []),
            "todos": result.get("todos", []),
            "content_hash": result.get("content_hash"),
            "content_changed_at": content_changed_at,
            "model_version": result.get("model_version", MODEL_VERSION),
            "computed_at": computed_at_dt,
            "inputs_hash": result.get("inputs_hash"),
            "conversion_detail": result.get("conversion_detail"),
            "updated_at": now,
        }

        self.live_db["listing_health_scores"].update_one(
            {"product_id": product_oid, "date": date_dt},
            {"$set": doc, "$setOnInsert": {"created_at": now}},
            upsert=True,
        )
        return str(product_oid)
