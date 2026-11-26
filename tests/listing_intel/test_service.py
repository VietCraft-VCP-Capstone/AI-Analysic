import json
from datetime import date
from types import SimpleNamespace

import numpy as np

from app.core.listing_intel import advice, fusion, image_fetch, service, store
from app.core.listing_intel.types import AxisResult
from tests.listing_intel.intel_support import PID, SHOP, URLS, env, listing  # noqa: F401

AT = date(2026, 10, 21)
KEYS = {"score", "base", "demand_factor", "score_timeline", "axes", "material", "keywords", "tags",
        "suggested_tags", "images", "market", "advice", "peers", "model", "title", "thumbnail",
        "product_id", "date", "capped_reason"}
AXES = {"image", "text", "tags", "market", "trend"}


def _no_image(out):
    assert out["axes"]["image"]["score"] is None
    assert "ảnh" in out["axes"]["image"]["missing_reason"]
    assert out["score"] is not None and 0 <= out["score"] <= 100


def test_analyze_without_images(env):
    _no_image(service.analyze(listing(image_urls=[]), AT, persist=False))


def test_analyze_failed_downloads(env, monkeypatch):
    monkeypatch.setattr(image_fetch, "fetch", lambda *a, **k: None)
    out = service.analyze(listing(), AT, persist=False)
    _no_image(out)
    assert all(i["issues"][0]["code"] == "fetch_failed" for i in out["images"])


def test_unknown_category_falls_back(env):
    out = service.analyze(listing(category="Danh mục mới", group=None), AT, persist=False)
    assert out["peers"]["group"] is None and out["peers"]["size"] >= 2
    assert 0 <= out["score"] <= 100


def test_material_missing_for_fashion(env):
    inp = listing(title="Áo khoác nữ dáng dài", description="Áo đẹp", materials=[], tags=["áo khoác"])
    out = service.analyze(inp, AT, persist=False)
    assert out["material"]["missing"] is True and out["material"]["required"] is True
    hits = [a for a in out["advice"] if a["code"] == "missing_material"]
    assert hits and hits[0]["evidence"] == "practice"


def test_timeline_has_8_weeks_and_bounds(env):
    out = service.analyze(listing(), AT, persist=False)
    tl = out["score_timeline"]
    assert len(tl) == 8
    assert all(0 <= p["score"] <= 100 and 0.5 <= p["demand_factor"] <= 1.5 for p in tl)
    assert len({p["demand_factor"] for p in tl}) > 1
    assert all(isinstance(e, str) for p in tl for e in p["events"])


def test_persist_upserts_once(env):
    before = [dict(d) for d in env["products"].docs]
    service.analyze(listing(), AT, persist=True)
    service.analyze(listing(), AT, persist=True)
    docs = env["listing_intel_scores"].docs
    assert len(docs) == 1 and docs[0]["product_id"] == PID and docs[0]["date"] == AT.isoformat()
    assert env["products"].docs == before


def test_contract_shape_and_finite(env):
    out = service.analyze(listing(), AT, persist=False)
    assert set(out) == KEYS and set(out["axes"]) == AXES
    json.dumps(out, allow_nan=False)
    assert out["thumbnail"] == URLS[0] and isinstance(out["model"]["trained_on"], str)
    assert all(a["effort"] in (1, 2, 3) and a["evidence"] in ("measured", "practice") for a in out["advice"])
    assert out["axes"]["image"]["score"] is not None and out["market"]["neighbors"] > 0
    assert {t["verdict"] for t in out["tags"]} >= {"duplicate"}


def test_embedding_cache_skips_download(env, monkeypatch):
    first = service.analyze(listing(), AT, persist=False)
    doc = env["listing_embeddings"].docs[0]
    assert len(doc["vec"]) == 768 * 2 and len(doc["_id"]) == 40
    monkeypatch.setattr(image_fetch, "fetch", lambda *a, **k: (_ for _ in ()).throw(AssertionError("fetched")))
    second = service.analyze(listing(), AT, persist=False)
    assert second["score"] == first["score"] and second["images"] == first["images"]


def test_advice_order_and_limit():
    axes = {"image": AxisResult(issues=[{"code": "blurry", "message": "m"}, {"code": "too_dark", "message": "m"}]),
            "text": AxisResult(issues=[{"code": c, "message": "m"} for c in
                                       ("title_short", "desc_short", "missing_color", "missing_size", "banned_word")])}
    material = {"missing": True}
    out = advice.build(axes, material, {"image": "measured", "text": "practice"}, {"desc_short": 9.0})
    assert len(out) == 6 and out[0]["axis"] == "image"
    assert any(a["code"] == "missing_material" and a["evidence"] == "practice" for a in out)
    practice = [a for a in out if a["evidence"] == "practice" and a["code"] != "missing_material"]
    assert practice[0]["code"] == "desc_short"
    assert np.all(np.diff([a["effort"] for a in practice[1:]]) >= 0)



def test_version_bump_recomputes(env):
    env["listing_intel_scores"].seed([{"product_id": PID, "date": AT.isoformat(), "model_version": "li-0.9", "score": 1.0}])
    items = {i["product_id"]: i for i in service.shop_summary(SHOP)["items"]}
    assert items[PID]["score"] not in (None, 1.0)
    version = fusion.load_bundle().meta["model_version"]
    assert {d["model_version"] for d in env["listing_intel_scores"].docs} == {"li-0.9", version}
    assert set(store.last_computed(version)) == set(items)


def test_shop_summary_caps_sync_scoring(env, monkeypatch):
    monkeypatch.setattr(service, "MAX_SYNC", 1)
    scores = [i["score"] for i in service.shop_summary(SHOP)["items"]]
    assert len(scores) == 2 and scores.count(None) == 1


def test_shop_summary_scores_without_writes(env):
    env.client = SimpleNamespace(address=("10.0.0.5", 27017))
    items = service.shop_summary(SHOP)["items"]
    assert env["listing_intel_scores"].docs == []
    assert all(i["score"] is not None and i["axes"]["text"] is not None and i["computed_at"] for i in items)


def test_non_local_mongo_refuses_writes(env, caplog):
    env.client = SimpleNamespace(address=("10.0.0.5", 27017))
    service.analyze(listing(), AT, persist=True)
    assert env["listing_intel_scores"].docs == [] and env["listing_embeddings"].docs == [] and env.indexes == []
    assert "refusing write" in caplog.text


def test_indexes_created_once(env):
    service.analyze(listing(), AT, persist=True)
    service.analyze(listing(), AT, persist=True)
    store._indexed["thread"].join(5)
    assert env.indexes == [([("product_id", 1), ("date", 1), ("model_version", 1)], {"unique": True}),
                           ([("product_id", 1), ("model_version", 1), ("date", -1)], {})]


def test_n_images_counts_all_but_downloads_8(env):
    urls = [f"https://res.cloudinary.com/demo/image/upload/{i}.jpg" for i in range(10)]
    out = service.analyze(listing(image_urls=urls), AT, persist=False)
    assert len(out["images"]) == 8 and out["axes"]["image"]["metrics"]["n_images"] == 10


def test_impact_set_when_top_medians_exist(env):
    out = service.analyze(listing(title="Áo", description="", tags=[]), AT, persist=False)
    fixable = [a for a in out["advice"] if a["code"] in advice.FIXES]
    assert fixable and all(isinstance(a["impact"], float) and a["impact"] >= 0 for a in fixable)
