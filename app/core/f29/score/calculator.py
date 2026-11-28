from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from bson import ObjectId
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError

from app.api.v1._live import LOC_SP_THAT, db_live
from app.config import settings
from app.core.f29.score import ai_summary, change, image_check, recommend
from app.core.f29 import constants
from app.core.f29.score import factors
from app.core.f29.score import peers
from app.core.f29.score import price
from app.core.f29.score import scoring
from app.core.f29.score import text_rules
from app.core.f29.checks import run as checks_run
from app.core.f29.constants import BLOCKING_FIELDS, MODEL_VERSION
from app.core.f29.score.peers import peer_values
from app.core.f29.score.factors import price_reasons
from app.core.f29.score.price import category_of, product_price
from app.core.f29.score.recommend import build_warnings, todos_of, warnings_of
from app.core.f29.shared import image_fetch
from app.core.f29.shared.embedder import MODEL_ID as SIGLIP_ID

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
SEARCH_DAYS = 30


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _blockers(warnings: List[Dict[str, Any]], variants: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    found = {w["field"]: w["message"] for w in warnings if w["type"] == "warning" and w["field"] in BLOCKING_FIELDS}
    if not any(v.get("is_active") is not False and (v.get("stock_quantity") or 0) > 0 for v in variants):
        found["variants.stock"] = "Không có biến thể nào đang bán còn hàng"
    return [{"field": f, "message": m} for f, m in found.items()]


def _snapshot(product: Dict[str, Any], variants: List[Dict[str, Any]]) -> Dict[str, Any]:
    desc = str(product.get("description") or "")
    return {"title": product.get("title") or "", "tags": product.get("tags") or [],
            "n_images": factors.image_count(product), "desc_words": constants.desc_words(desc),
            "has_size": factors.has_size(product, desc), "materials": sorted(text_rules.materials_of(product)),
            "price": product_price(variants)}


SAVED_FIELDS = ("title", "thumbnail", "score", "status", "coverage", "factors", "blockers", "recommendations",
                "search", "versions", "content_snapshot", "axes", "axes_missing", "todos", "warnings",
                "content_hash", "inputs_hash", "model_version", "checks", "confidence", "incomplete", "change")
RETRY_INCOMPLETE = timedelta(minutes=30)
LEGACY_FIELDS = ("readiness", "conversion_detail", "content_changed_at", "breakdown", "basis", "cap")


def _iso(value: datetime) -> str:
    return value.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


def _usable(doc: Dict[str, Any]) -> bool:
    at = doc["computed_at"]
    at = at if at.tzinfo else at.replace(tzinfo=timezone.utc)
    return not doc.get("incomplete") or datetime.now(timezone.utc) - at < RETRY_INCOMPLETE


def _from_doc(doc: Dict[str, Any]) -> Dict[str, Any]:
    result = {k: doc.get(k) for k in SAVED_FIELDS}
    result["todos"] = [t for t in doc.get("todos") or [] if t.get("type") == "todo"]
    result.update(product_id=str(doc["product_id"]), date=doc["date"].date().isoformat(),
                  computed_at=_iso(doc["computed_at"]), ai=ai_summary.build(doc.get("checks") or [], doc.get("factors") or []))
    return result


class HealthScoreCalculator:
    def __init__(self, db_client: Optional[MongoClient] = None):
        if db_client is not None:
            self.client = db_client
            self.live_db = db_client[settings.MONGO_DB_LIVE]
        else:
            self.client = None
            self.live_db = db_live()
        self._pending_tags: Optional[frozenset] = None

    def pending_tag_ids(self) -> frozenset:
        if self._pending_tags is None:
            tags = self.live_db["tags"]
            self._pending_tags = frozenset(
                t["_id"] for field in ("status", "review_status") for t in tags.find({field: "pending"}, {"_id": 1}))
        return self._pending_tags

    def _compute_inputs_hash(
        self, product: Dict[str, Any], variants: List[Dict[str, Any]], reviews: Tuple[int, int]
    ) -> str:
        return scoring.inputs_hash(product, variants, reviews,
                                   {**checks_run.versions(), "models": checks_run.stamp(),
                                    "config": constants.load(), "price": text_rules.price_params()})

    def _variants(self, product_oid: ObjectId) -> List[Dict[str, Any]]:
        return list(self.live_db["product_variants"].find(
            {"product_id": product_oid},
            {"is_active": 1, "stock_quantity": 1, "retail_price": 1, "base_cost": 1, "color": 1},
        ))

    def _zero_result(self, product: Dict[str, Any]) -> List[Dict[str, Any]]:
        since = datetime.now(timezone.utc) - timedelta(days=SEARCH_DAYS)
        return price.zero_result_queries(self.live_db, product, since)

    def _search(self, product: Dict[str, Any]) -> List[Dict[str, Any]]:
        category = category_of(product)
        if not category:
            return []
        since = datetime.now(timezone.utc) - timedelta(days=SEARCH_DAYS)
        text = price.product_text(product)
        rows = [r for r in price.category_queries(self.live_db, category, since) if price.about(r["query"], product)]
        return [{**r, "covered": price.relevant(r["query"], text)} for r in rows]

    def _factors(self, product: Dict[str, Any], variants: List[Dict[str, Any]], cfg: Dict[str, Any],
                 reviews: Tuple[int, int], search: List[Dict[str, Any]],
                 loaded: Dict[str, Any], image_budget: float) -> List[Dict[str, Any]]:
        median_images, median_words, in_category = factors.peer_medians(self.live_db, product)
        analysis = image_check.analyze(list(loaded),
                                       fetch=lambda url, save=False: image_check.item_of(*loaded[url]),
                                       budget=image_budget)
        pending = self.pending_tag_ids()
        n_good, n = reviews
        return [
            factors.image_row(analysis, median_images, in_category),
            factors.description_row(product, median_words, in_category),
            factors.tags_row(scoring.count_approved_tags(product, pending), scoring.count_pending_tags(product, pending),
                        search, "rule"),
            factors.review_row(n_good, n, peers.platform_p0(self.live_db), float(cfg["review"]["m"])),
            factors.price_row(price.position(self.live_db, product, product_price(variants)),
                         price_reasons(product, self._copied_description(product))),
        ]

    def _copied_description(self, product: Dict[str, Any]) -> bool:
        desc = product.get("description")
        if not isinstance(desc, str) or not desc.strip() or not product.get("shop_id"):
            return False
        query = {"shop_id": product["shop_id"], "_id": {"$ne": product.get("_id")}, "description": desc}
        return self.live_db["products"].find_one(query, {"_id": 1}) is not None

    def _warnings(self, product: Dict[str, Any], variants: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        hints = [h for h in scoring.content_hints(product, self.pending_tag_ids()) if h.get("type") == "warning"]
        return build_warnings(product, variants) + hints

    def calculate(self, product_id: str, image_budget: float = 20.0) -> Optional[Dict[str, Any]]:
        try:
            product_oid = ObjectId(product_id)
        except Exception:
            return None
        try:
            cfg = constants.load()
        except RuntimeError:
            return {"error": "no_weights"}

        product = self.live_db["products"].find_one({"_id": product_oid, **LOC_SP_THAT})
        if not product:
            return None
        result = self._score(product_id, product, self._variants(product_oid),
                             peers.product_counts(self.live_db, product_oid), cfg, image_budget, True)
        result["change"] = change.explain(self._previous(product_oid), result)
        return result

    def _previous(self, product_oid: ObjectId) -> Optional[Dict[str, Any]]:
        try:
            return constants.store_db()["listing_health_scores"].find_one(
                {"product_id": product_oid},
                {"score": 1, "content_snapshot": 1, "content_hash": 1, "factors": 1, "model_version": 1,
                 "incomplete": 1, "versions": 1},
                sort=[("computed_at", -1)])
        except Exception:
            return None

    def calculate_draft(self, product: Dict[str, Any], variants: List[Dict[str, Any]],
                        image_budget: float) -> Dict[str, Any]:
        try:
            cfg = constants.load()
        except RuntimeError:
            return {"error": "no_weights"}
        return self._score(None, self._with_tag_ids(product), variants, (0, 0), cfg, image_budget, False)

    def _with_tag_ids(self, product: Dict[str, Any]) -> Dict[str, Any]:
        wanted = {t.strip().lower() for t in product.get("tags") or [] if isinstance(t, str)}
        found = [t for t in self.live_db["tags"].find({}, {"name": 1, "status": 1})
                 if str(t.get("name") or "").strip().lower() in wanted and t.get("status") in ("active", "pending")]
        return {**product, "tag_ids": [t["_id"] for t in found],
                "tags": [t["name"] for t in found if t.get("status") == "active"]}

    def _score(self, product_id: Optional[str], product: Dict[str, Any], variants: List[Dict[str, Any]],
               reviews: Tuple[int, int], cfg: Dict[str, Any], image_budget: float, index: bool) -> Dict[str, Any]:
        now_utc = datetime.now(timezone.utc)
        today = datetime.now(VN_TZ).date().isoformat()
        search = self._search(product)
        urls = image_check.unique(factors.image_urls(product))
        loaded = checks_run.fetch_all(urls, image_budget, frozenset(urls))
        rows = self._factors(product, variants, cfg, reviews, search, loaded, image_budget)
        image = next(r for r in rows if r["key"] == "image")
        image_urls = [r["url"] for r in image["evidence"].get("images", [])]
        checks, check_versions = checks_run.collect(product, variants, self.live_db, image_urls, loaded=loaded,
                                                     index=index)
        rows = checks_run.apply(rows, checks)
        values = peer_values(self.live_db, product, self.pending_tag_ids(),
                             peers.platform_p0(self.live_db), float(cfg["review"]["m"]))
        rows = scoring.rescore_all(rows, values)
        warnings = self._warnings(product, variants)
        score, coverage = scoring.score(rows)

        raw_imgs = product.get("images")
        thumb = raw_imgs[0] if isinstance(raw_imgs, list) and raw_imgs else (raw_imgs if isinstance(raw_imgs, str) else None)
        image = next(r for r in rows if r["key"] == "image")
        siglip = SIGLIP_ID if image["evidence"].get("siglip") else None
        result = {
            "product_id": product_id,
            "title": product.get("title") or "",
            "thumbnail": thumb,
            "date": today,
            "score": score,
            "status": scoring.status_from_score(score),
            "coverage": coverage,
            "factors": rows,
            "blockers": _blockers(warnings, variants),
            "recommendations": [],
            "search": {"category": category_of(product), "queries": search,
                       "zero_result": self._zero_result(product)},
            "versions": {"score": MODEL_VERSION, "siglip": siglip, "relevance": "lexical",
                         "benchmark": f"vc-{today}", **check_versions, "stamp": checks_run.stamp()},
            "checks": checks,
            "ai": ai_summary.build(checks, rows),
            "confidence": scoring.confidence(rows, values["n"]),
            "content_snapshot": _snapshot(product, variants),
            "axes": {r["key"]: r["sub_score"] for r in rows},
            "axes_missing": [r["key"] for r in rows if r["state"] != "scored"],
            "todos": [],
            "warnings": [],
            "computed_at": now_utc.isoformat().replace("+00:00", "Z"),
            "model_version": MODEL_VERSION,
            "content_hash": scoring.content_hash(product),
            "inputs_hash": self._compute_inputs_hash(product, variants, reviews),
        }
        result["recommendations"] = recommend.build(result, image, search, result["search"]["zero_result"])
        result["todos"] = todos_of(result["recommendations"])
        result["warnings"] = warnings_of(result["recommendations"])
        retry = any(img is None and image_fetch.allowed(url) for url, (img, _) in loaded.items())
        result["incomplete"] = retry or any(c["id"].endswith(":error") for c in checks)
        return result

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
        doc = {k: result.get(k) for k in SAVED_FIELDS}
        doc.update(
            product_id=product_oid, date=date_dt, computed_at=computed_at_dt, updated_at=now,
            model_version=result.get("model_version", MODEL_VERSION),
            todos=(result.get("warnings") or []) + (result.get("todos") or []),
        )

        update = {"$set": doc, "$setOnInsert": {"created_at": now}, "$unset": {k: "" for k in LEGACY_FIELDS}}
        scores = constants.store_db()["listing_health_scores"]
        try:
            scores.update_one({"product_id": product_oid, "date": date_dt}, update, upsert=True)
        except DuplicateKeyError:
            scores.update_one({"product_id": product_oid}, update)
        return str(product_oid)

    def stored_result(self, product_id: str) -> Optional[Dict[str, Any]]:
        try:
            product_oid = ObjectId(product_id)
        except Exception:
            return None
        with ThreadPoolExecutor(4) as pool:
            product = pool.submit(self.live_db["products"].find_one, {"_id": product_oid, **LOC_SP_THAT})
            reviews = pool.submit(peers.product_counts, self.live_db, product_oid)
            variants = pool.submit(self._variants, product_oid)
            doc = pool.submit(constants.store_db()["listing_health_scores"].find_one,
                              {"product_id": product_oid, "model_version": MODEL_VERSION}, sort=[("computed_at", -1)])
            product, doc = product.result(), doc.result()
            if not product or not doc:
                return None
            key = self._compute_inputs_hash(product, variants.result(), reviews.result())
        return _from_doc(doc) if doc.get("inputs_hash") == key and _usable(doc) else None
