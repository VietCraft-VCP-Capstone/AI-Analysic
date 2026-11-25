from datetime import timedelta

import pytest
from bson import ObjectId

from app.core.f29 import constants
from app.core.f29.score import image_check
from app.core.f29.checks import run
from app.core.f29.constants import KEYS, MODEL_VERSION
from app.core.f29.score.preview import preview_health
from app.core.f29.score.scoring import content_hints, normalize_image
from app.core.f29.shared.embedder import MODEL_ID as SIGLIP_ID
from tests.f29.fake_mongo import make_calculator
from tests.f29.samples import base_product, NOW, PRODUCT_ID, with_id


ORDER = ObjectId()


OTHER = ObjectId("507f1f77bcf86cd799439012")


PRICED = [{"is_active": True, "stock_quantity": 10, "retail_price": "150000", "base_cost": "80000"}]


def _priced(product, variants=PRICED):
    return [{**v, "product_id": product["_id"]} for v in variants]


def _review(product_id, rating, order_id=ORDER):
    return {"product_id": product_id, "order_id": order_id, "rating": rating}


def _with_peers(peer_title, price):
    product = with_id(base_product())
    peers = [{"_id": ObjectId(f"{i:024x}"), "shop_id": OTHER, "categories": ["Thời trang"],
              "title": f"{peer_title} {i}"} for i in range(1, 9)]
    variants = _priced(product, [{"is_active": True, "retail_price": price, "base_cost": "30000"}])
    variants += [{"product_id": p["_id"], "is_active": True, "retail_price": "100000"} for p in peers]
    return make_calculator(products=[product, *peers], product_variants=variants).calculate(PRODUCT_ID)


class TestCalculateIntegration:
    def test_invalid_product_id_returns_none(self):
        calc = make_calculator()
        assert calc.calculate("not-an-object-id") is None

    def test_seed_product_excluded(self):
        product = with_id(base_product(seed_ref="seed_123"))
        calc = make_calculator(products=[product])
        assert calc.calculate(PRODUCT_ID) is None

    def test_missing_product_returns_none(self):
        calc = make_calculator(products=[])
        assert calc.calculate(PRODUCT_ID) is None

    def test_weights_missing_returns_error(self, monkeypatch, tmp_path):
        monkeypatch.setattr(constants, "WEIGHTS_PATH", tmp_path / "none.json")
        constants.clear_cache()
        calc = make_calculator(products=[with_id(base_product())])
        assert calc.calculate(PRODUCT_ID) == {"error": "no_weights"}

    def test_happy_path_shape_and_axes_missing(self):
        product = with_id(base_product())
        calc = make_calculator(products=[product], product_variants=_priced(product))
        result = calc.calculate(PRODUCT_ID)

        assert result["product_id"] == PRODUCT_ID
        assert isinstance(result["score"], float)
        assert result["status"] in ("good", "needs_improvement", "poor")
        assert set(result["axes"]) == set(KEYS)
        assert result["axes_missing"] == ["review", "price"]
        assert [f["key"] for f in result["factors"]] == list(KEYS)
        assert result["coverage"] == {"evaluated": 3, "total": 5}
        assert result["model_version"] == MODEL_VERSION
        assert result["content_hash"] and result["inputs_hash"]

    def test_missing_review_is_not_applicable(self):
        product = with_id(base_product())
        calc = make_calculator(products=[product], product_variants=_priced(product))
        review = next(f for f in calc.calculate(PRODUCT_ID)["factors"] if f["key"] == "review")
        assert review["state"] == "not_applicable" and review["sub_score"] is None and review["points"] == 0.0
        assert review["reason"] == "Chưa có đánh giá"

    def test_simulated_order_reviews_ignored(self):
        sim_order = ObjectId()
        product = with_id(base_product())
        calc = make_calculator(
            products=[product], product_variants=_priced(product),
            orders=[{"_id": sim_order, "is_simulated": True}],
            reviews=[_review(product["_id"], 5, order_id=sim_order)],
        )
        result = calc.calculate(PRODUCT_ID)
        assert result["axes"]["review"] is None
        assert "review" in result["axes_missing"]

    def test_review_uses_platform_p0(self):
        product = with_id(base_product())
        reviews = [_review(product["_id"], 5), _review(product["_id"], 5),
                   _review(OTHER, 1), _review(OTHER, 1)]
        calc = make_calculator(products=[product], product_variants=_priced(product),
                               orders=[{"_id": ORDER}], reviews=reviews)
        review = next(f for f in calc.calculate(PRODUCT_ID)["factors"] if f["key"] == "review")
        assert review["evidence"]["p0"] == pytest.approx(0.5) and review["state"] == "not_applicable"
        assert "chưa đủ tin có đánh giá để so" in review["reason"]

    def test_no_active_variant_price_is_missing(self):
        product = with_id(base_product())
        variants = _priced(product, [{"is_active": False, "retail_price": "150000", "base_cost": "80000"}])
        calc = make_calculator(products=[product], product_variants=variants)
        result = calc.calculate(PRODUCT_ID)
        assert result["axes"]["price"] == 0.0
        assert "price" in result["axes_missing"]
        assert [b["field"] for b in result["blockers"]] == ["variants.stock"]

    def test_price_not_penalized_without_peers(self):
        product = with_id(base_product())
        variants = _priced(product, [{"is_active": True, "retail_price": "400000", "base_cost": "80000"}])
        result = make_calculator(products=[product], product_variants=variants).calculate(PRODUCT_ID)
        price = next(f for f in result["factors"] if f["key"] == "price")
        assert result["axes"]["price"] is None and price["state"] == "not_applicable" and price["points"] == 0.0
        scored = [f for f in result["factors"] if f["state"] == "scored"]
        assert result["score"] == round(sum(f["points"] for f in scored) * 100 / (20 * len(scored)), 1)

    def test_no_typo_check_against_rough_reference(self):
        product = with_id(base_product())
        variants = _priced(product, [{"is_active": True, "retail_price": "15000", "base_cost": "8000"}])
        result = make_calculator(products=[product], product_variants=variants).calculate(PRODUCT_ID)
        assert not any(w["field"] == "price" for w in result["warnings"])
        assert result["axes"]["price"] is None

    def test_cheap_price_is_not_penalised(self):
        result = _with_peers("Áo cotton mẫu", "50000")
        price = next(f for f in result["factors"] if f["key"] == "price")
        assert price["state"] == "scored" and price["evidence"]["n"] == 8 and result["axes"]["price"] == 100.0
        assert any(r["id"] == "info:price_low" for r in result["recommendations"])

    def test_price_at_market_level_scores_half(self):
        price = next(f for f in _with_peers("Áo cotton mẫu", "100000")["factors"] if f["key"] == "price")
        assert price["sub_score"] == 100 - price["evidence"]["pct"] == 50.0 and price["points"] == 10.0

    def test_junk_title_warns_with_cleaned_suggestion(self):
        product = with_id(base_product(title="icon arrow left bold Share: Favorite (48) Thắt lưng vải canvas nam"))
        result = make_calculator(products=[product], product_variants=_priced(product)).calculate(PRODUCT_ID)
        warning = next(w for w in result["warnings"] if w["field"] == "title")
        assert warning["type"] == "warning" and warning["target"] == "Thắt lưng vải canvas nam"

    def test_junk_description_fails_word_check(self):
        product = with_id(base_product(description="a " * 570))
        real = "tu " + " ".join(f"chu{j}" for j in range(20))
        peers = [{"_id": ObjectId(f"{i:024x}"), "categories": ["Thời trang"], "description": real} for i in range(1, 9)]
        result = make_calculator(products=[product, *peers], product_variants=_priced(product)).calculate(PRODUCT_ID)
        description = next(f for f in result["factors"] if f["key"] == "description")
        assert description["evidence"]["checks"]["words"] is False and description["sub_score"] == 0.0
        assert description["evidence"]["level"] == "all" and description["method"] == "learned"

    def test_deterministic(self):
        product = with_id(base_product())
        calc = make_calculator(products=[product], product_variants=_priced(product))
        first, second = calc.calculate(PRODUCT_ID), calc.calculate(PRODUCT_ID)
        assert (first["score"], first["axes"], first["todos"]) == (second["score"], second["axes"], second["todos"])

    def test_warnings_are_separate_from_todos(self):
        product = with_id(base_product(images=[], moderation_status="REJECTED"))
        variants = _priced(product, [{"is_active": True, "retail_price": "50000", "base_cost": "80000"}])
        result = make_calculator(products=[product], product_variants=variants).calculate(PRODUCT_ID)

        assert {w["field"] for w in result["warnings"]} == {"images", "variants.retail_price", "moderation_status", "variants.stock"}
        assert all(w["impact"] == 0 for w in result["warnings"])
        assert all(t["type"] == "todo" for t in result["todos"])


class TestSaveIdempotency:
    def _sample_result(self, score=72.5, date=None):
        return {
            "product_id": PRODUCT_ID,
            "date": date or NOW.date().isoformat(),
            "score": score,
            "status": "needs_improvement",
            "axes": {"image": 100.0, "description": 100.0, "tags": 100.0, "review": 0.0, "price": 0.0},
            "axes_missing": ["review", "price"],
            "todos": [],
            "computed_at": NOW.isoformat().replace("+00:00", "Z"),
            "model_version": "health-2.2",
            "content_hash": "abc123",
            "inputs_hash": "def456",
        }

    def test_save_different_dates_creates_history_documents(self):
        calc = make_calculator()
        calc.save(self._sample_result(date="2026-10-15", score=50.0))
        calc.save(self._sample_result(date="2026-10-16", score=75.0))
        docs = constants.store_db()["listing_health_scores"].docs
        assert len(docs) == 2
        scores = {d["score"] for d in docs}
        assert scores == {50.0, 75.0}

    def test_save_when_db_allows_one_document_per_product(self):
        from pymongo.errors import DuplicateKeyError
        calc = make_calculator()
        calc.save(self._sample_result(date="2026-10-15", score=50.0))
        coll = constants.store_db()["listing_health_scores"]
        plain_update = coll.update_one

        def unique_product(filt, update, upsert=False):
            if upsert and not coll.find_one(filt) and coll.find_one({"product_id": filt["product_id"]}):
                raise DuplicateKeyError("E11000 duplicate key error index: product_id_1")
            return plain_update(filt, update, upsert)

        coll.update_one = unique_product
        calc.save(self._sample_result(date="2026-10-16", score=75.0))
        assert [(d["score"], d["date"].day) for d in coll.docs] == [(75.0, 16)]

    def test_save_twice_same_result_creates_one_document(self):
        calc = make_calculator()
        calc.save(self._sample_result())
        calc.save(self._sample_result())
        docs = constants.store_db()["listing_health_scores"].docs
        assert len(docs) == 1
        assert docs[0]["score"] == 72.5

    def test_save_upserts_on_score_change_same_day(self):
        calc = make_calculator()
        calc.save(self._sample_result(score=50.0))
        calc.save(self._sample_result(score=90.0))
        docs = constants.store_db()["listing_health_scores"].docs
        assert len(docs) == 1
        assert docs[0]["score"] == 90.0

    def test_calculate_then_save_twice_is_idempotent(self):
        product = with_id(base_product())
        calc = make_calculator(products=[product], product_variants=_priced(product))

        result1 = calc.calculate(PRODUCT_ID)
        calc.save(result1)
        result2 = calc.calculate(PRODUCT_ID)
        calc.save(result2)

        docs = constants.store_db()["listing_health_scores"].docs
        assert len(docs) == 1
        assert docs[0]["score"] == result1["score"] == result2["score"]
        assert docs[0]["content_hash"] == result1["content_hash"]

    def test_save_drops_breakdown_and_basis(self):
        product = with_id(base_product())
        calc = make_calculator(products=[product], product_variants=_priced(product))
        result = calc.calculate(PRODUCT_ID)
        calc.save(result)
        doc = constants.store_db()["listing_health_scores"].docs[0]
        assert "breakdown" not in doc and "basis" not in doc
        assert doc["todos"] == result["warnings"] + result["todos"]

    def test_save_returns_none_for_invalid_result(self):
        calc = make_calculator()
        assert calc.save(None) is None
        assert calc.save({"product_id": "khong-phai-objectid", "date": "2026-10-15"}) is None


def test_tag_under_review_counts_as_pending():
    tags = [{"_id": ObjectId(f"{i:024x}"), "name": n, "status": s, "review_status": r}
            for i, (n, s, r) in enumerate([("a", "active", "approved"), ("b", "pending", "pending"),
                                           ("c", "active", "pending")], start=1)]
    product = with_id(base_product(tag_ids=[t["_id"] for t in tags]))
    calc = make_calculator(products=[product], product_variants=_priced(product), tags=tags)
    row = next(f for f in calc.calculate(PRODUCT_ID)["factors"] if f["key"] == "tags")
    assert row["evidence"]["approved"] == 1 and row["evidence"]["pending"] == 2


RICH = {"images": [f"i{i}.jpg" for i in range(6)],
        "description": " ".join(f"chu{chr(97 + i % 26)}{i}" for i in range(130))}


def test_missing_price_counts_as_zero():
    product = with_id(base_product())
    result = make_calculator(products=[product]).calculate(PRODUCT_ID)
    price = next(f for f in result["factors"] if f["key"] == "price")
    assert price["state"] == "seller_missing" and price["points"] == 0.0
    assert result["coverage"]["evaluated"] == 4


def test_blocking_title_does_not_cap_score():
    product = with_id(base_product(**RICH, title="icon arrow left bold Share: Favorite (48) Áo thun cotton local brand unisex"))
    clean = with_id(base_product(**RICH))
    raw = make_calculator(products=[clean], product_variants=_priced(clean)).calculate(PRODUCT_ID)
    result = make_calculator(products=[product], product_variants=_priced(product)).calculate(PRODUCT_ID)
    assert result["score"] == raw["score"] and raw["blockers"] == []
    assert [b["field"] for b in result["blockers"]] == ["title"]


CONTRACT_FIELDS = ("score", "status", "coverage", "factors", "blockers", "recommendations", "search", "versions",
                   "content_snapshot", "axes", "axes_missing", "todos", "warnings", "content_hash", "inputs_hash",
                   "computed_at", "model_version", "date", "title", "thumbnail")


class TestStoredResult:
    def _calc(self, **seed):
        product = with_id(base_product())
        return make_calculator(products=[product], product_variants=_priced(product), **seed)

    def test_save_persists_contract_fields_without_readiness(self):
        calc = self._calc()
        calc.save(calc.calculate(PRODUCT_ID))
        doc = constants.store_db()["listing_health_scores"].docs[0]
        assert all(k in doc for k in CONTRACT_FIELDS)
        assert "readiness" not in doc

    def test_stored_result_round_trips_calculate_shape(self):
        calc = self._calc()
        result = calc.calculate(PRODUCT_ID)
        calc.save(result)
        assert calc.stored_result(PRODUCT_ID) == result

    def test_stored_result_misses_when_images_change(self):
        calc = self._calc()
        calc.save(calc.calculate(PRODUCT_ID))
        calc.live_db["products"].docs[0]["images"] = ["new.jpg"]
        assert calc.stored_result(PRODUCT_ID) is None

    def test_stored_result_misses_on_other_model_version(self):
        calc = self._calc()
        calc.save(calc.calculate(PRODUCT_ID))
        constants.store_db()["listing_health_scores"].docs[0]["model_version"] = "health-2.2"
        assert calc.stored_result(PRODUCT_ID) is None

    def test_zero_result_queries_fill_search_block(self):
        logs = [{"keyword": "áo thun oversize", "result_count": 0, "created_at": NOW - timedelta(days=1)}] * 2
        result = self._calc(search_logs=logs).calculate(PRODUCT_ID)
        assert result["search"]["zero_result"] == [{"query": "áo thun oversize", "searches": 2}]

    def test_benchmark_is_vietnam_date_tag(self):
        result = self._calc().calculate(PRODUCT_ID)
        assert result["versions"]["benchmark"] == f"vc-{result['date']}"

    def test_save_unsets_legacy_fields(self):
        calc = self._calc()
        calc.save(calc.calculate(PRODUCT_ID))
        constants.store_db()["listing_health_scores"].docs[0].update(
            readiness={}, conversion_detail={}, content_changed_at=NOW, breakdown=[], basis={}, cap=79.0)
        calc.save(calc.calculate(PRODUCT_ID))
        doc = constants.store_db()["listing_health_scores"].docs[0]
        assert not {"readiness", "conversion_detail", "content_changed_at", "breakdown", "basis", "cap"} & set(doc)


def test_image_budget_defaults_to_20_and_passes_through(monkeypatch):
    seen = []
    monkeypatch.setattr(run, "fetch_all", lambda urls, budget, vec_urls=frozenset(): seen.append(budget) or {})
    product = with_id(base_product())
    calc = make_calculator(products=[product], product_variants=_priced(product))
    calc.calculate(PRODUCT_ID)
    calc.calculate(PRODUCT_ID, image_budget=1.5)
    assert seen == [20.0, 1.5]


@pytest.mark.parametrize("method,expected", [("ml_unvalidated", SIGLIP_ID), ("heuristic", None)])
def test_versions_siglip_follows_analysis_method(monkeypatch, method, expected):
    def spy(urls, fetch=None, budget=None):
        return {"state": "scored", "useful": 1, "unanalyzed": 0, "images": [], "method": method}

    monkeypatch.setattr(image_check, "analyze", spy)
    product = with_id(base_product())
    result = make_calculator(products=[product], product_variants=_priced(product)).calculate(PRODUCT_ID)
    assert result["versions"]["siglip"] == expected
    assert result["factors"][0]["method"] == "learned"


NONE = {"n_images": None, "description_length": None, "n_tags": None, "price": None}


LONG = " ".join(f"chu{i}" for i in range(130))


JUNK_TITLE = "icon arrow left bold Share: Favorite (48) Áo thun cotton local brand unisex"


def _calc(**product):
    p = with_id(base_product(**product))
    variants = [{"product_id": p["_id"], "is_active": True, "stock_quantity": 10,
                 "retail_price": "150000", "base_cost": "80000"}]
    peers = [{"_id": ObjectId(f"{i:024x}"), "categories": ["Thời trang"], "description": LONG} for i in range(1, 9)]
    variants += [{"product_id": p["_id"], "is_active": True, "retail_price": "100000"} for p in peers]
    return make_calculator(products=[p, *peers], product_variants=variants)


def _others_unchanged(preview, current, key):
    return all(preview["axes"][k] == current["axes"][k] for k in KEYS if k != key)


def test_no_override_matches_current():
    calc = _calc()
    current = calc.calculate(PRODUCT_ID)
    preview = preview_health(calc, PRODUCT_ID, NONE)
    assert preview["score"] == current["score"] and preview["axes"] == current["axes"]
    assert preview["delta_vs_current"] == 0.0 and preview["ignored"] == []


@pytest.mark.parametrize("override,key,expected", [
    ({"n_tags": 0}, "tags", 0.0),
    ({"n_images": 0}, "image", 0.0),
    ({"description_length": 0}, "description", 0.0),
])
def test_override_changes_only_its_factor(override, key, expected):
    calc = _calc()
    current = calc.calculate(PRODUCT_ID)
    preview = preview_health(calc, PRODUCT_ID, {**NONE, **override})
    assert preview["axes"][key] == expected
    assert _others_unchanged(preview, current, key)


def test_price_override_recomputes_price_axis():
    calc = _calc()
    current = calc.calculate(PRODUCT_ID)
    preview = preview_health(calc, PRODUCT_ID, {**NONE, "price": 100000})
    assert preview["axes"]["price"] == 50.0 and preview["inputs"]["price"] == 100000
    assert _others_unchanged(preview, current, "price")


def test_preview_blockers_never_cap_score():
    product = with_id(base_product(title=JUNK_TITLE))
    variants = [{"product_id": product["_id"], "is_active": True, "stock_quantity": 10,
                 "retail_price": "150000", "base_cost": "80000"}]
    calc = make_calculator(products=[product], product_variants=variants)
    current = calc.calculate(PRODUCT_ID)
    assert any(b["field"] == "title" for b in current["blockers"]) and current["score"] == 50.0
    assert preview_health(calc, PRODUCT_ID, NONE)["score"] == current["score"]


def test_description_override_on_empty_description_scores_words():
    calc = _calc(description="")
    assert calc.calculate(PRODUCT_ID)["axes"]["description"] == 0.0
    preview = preview_health(calc, PRODUCT_ID, {**NONE, "description_length": 130})
    assert preview["axes"]["description"] == 50.0


def _fields(hints):
    return [h["field"] for h in hints]


def test_content_hints_non_string_description():
    hints = content_hints({"description": 123, "title": "x", "images": []})
    assert isinstance(hints, list)


def test_content_hints_string_image_no_duplicate_hint():
    hints = content_hints(base_product(images="https://a/x.jpg"))
    assert "images" not in _fields(hints)


def test_content_hints_int_images():
    content_hints(base_product(images=5))


def test_cloudinary_image_dedupe():
    u1 = "https://res.cloudinary.com/demo/image/upload/v1570979139/sample.jpg"
    u2 = "https://res.cloudinary.com/demo/image/upload/w_200,h_200/v1570979139/sample.png"
    assert normalize_image(u1) == normalize_image(u2) == "sample"
    hints = content_hints(base_product(images=[u1, u2]))
    assert "images" in _fields(hints)


def test_preview_uses_stored_result_without_recalculating():
    calc = _calc()
    stored = calc.calculate(PRODUCT_ID)
    calls = []
    calc.stored_result = lambda pid: stored
    calc.calculate = lambda pid: calls.append(pid)
    preview = preview_health(calc, PRODUCT_ID, NONE)
    assert calls == [] and preview["score"] == stored["score"]
