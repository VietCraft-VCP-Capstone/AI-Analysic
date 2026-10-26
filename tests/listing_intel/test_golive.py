import hashlib
import io
import json
import math
from datetime import date, datetime

import pandas as pd
import pytest
from pymongo.errors import OperationFailure

from app.core.listing_intel import features as F
from app.core.listing_intel import advice, fusion, intel, live_data, service, store
from app.core.listing_intel import trend_store as ts
from app.core.listing_intel.tags_axis import tag_report
from scripts.li import fetch_models as fm
from scripts.li.trend_snapshot import snapshot
from tests.f29.fake_mongo import _FakeCollection
from tests.listing_intel.intel_support import PID, URLS, env, listing, product  # noqa: F401
from tests.listing_intel.test_bundle import synthetic

AT = date(2026, 10, 21)
PEER = "64c000000000000000000002"


def test_served_masks_and_imputes(env, monkeypatch):
    meta = fusion.load_bundle().meta
    monkeypatch.setitem(meta, "feature_availability", {"fashion": {"desc_len": 0.0, "img_w": 1.0, "sim_title": 0.5}})
    monkeypatch.setitem(meta, "image_impute", {"fashion": {"img_w": 120.0, "sim_title": 0.1}})
    monkeypatch.setitem(meta, "feature_constants", {"fashion": {"desc_words": 0.0}})
    out = fusion.served({"desc_len": 300.0, "desc_words": 50.0, "img_w": math.nan, "sim_title": math.nan,
                         "title_len": 20.0}, "fashion")
    assert math.isnan(out["desc_len"]) and out["img_w"] == 120.0 and math.isnan(out["sim_title"])
    assert out["desc_words"] == 0.0
    assert out["title_len"] == 20.0 and fusion.served({"desc_len": 3.0}, "bags") == {"desc_len": 3.0}


def test_served_without_meta_keys_logs_once(env, monkeypatch, caplog):
    meta = fusion.load_bundle().meta
    for key in fusion.PARITY_KEYS:
        monkeypatch.delitem(meta, key, raising=False)
    monkeypatch.setattr(fusion, "_warned", set())
    feats = {"desc_len": 3.0, "img_w": math.nan}
    assert fusion.served(feats, "fashion") is not feats
    fusion.served(feats, "fashion")
    assert all(caplog.text.count(f"no {k}") == 1 for k in fusion.PARITY_KEYS)


@pytest.mark.parametrize("urls", [URLS, []])
def test_image_fix_impacts_match_displayed_total(env, urls):
    parts = intel.build(listing(image_urls=urls), AT, store_embeddings=False)
    feats, g = parts["feats"], parts["inp"].group
    codes = ("low_resolution", "blurry", "too_dark", "busy_background", "text_overlay", "few_images", "no_images")
    fixes = {c: advice.FIXES[c] for c in codes}
    tops = fusion.load_bundle().top_medians
    med = tops.get(g) or tops["all"]
    shown = lambda f: min(100.0, fusion.base_score(f, g) * feats["trend_factor"])
    for c, v in fusion.impacts(feats, g, fixes).items():
        fixed = {**feats, **{k: med[k] for k in fixes[c] if k in med}}
        assert v <= round(max(0.0, shown(fixed) - shown(feats)), 1) + 1e-9


def test_no_image_never_above_with_image(env, monkeypatch):
    table = synthetic()
    train = table[(table["split"] == "train") & (table["group"] == "fashion")]
    meta = fusion.load_bundle().meta
    monkeypatch.setitem(meta, "feature_availability", {"fashion": dict.fromkeys(F.FEATURE_COLS, 1.0)})
    monkeypatch.setitem(meta, "image_impute", {"fashion": {c: float(train[c].quantile(0.1)) for c in F.IMAGE_COLS}})
    with_img = service.analyze(listing(), AT, persist=False)
    no_img = service.analyze(listing(image_urls=[]), AT, persist=False)
    assert no_img["base"] <= with_img["base"]


def test_peer_rows_cached_until_updated(env, monkeypatch):
    calls, real = [], live_data.load_many
    monkeypatch.setattr(live_data, "load_many", lambda ids: calls.append(list(ids)) or real(ids))
    first = service.analyze(listing(), AT, persist=False)
    second = service.analyze(listing(), AT, persist=False)
    assert calls == [[PEER]] and first["axes"]["tags"] == second["axes"]["tags"]
    env["products"].docs[1]["updated_at"] = datetime(2026, 10, 21)
    service.analyze(listing(), AT, persist=False)
    assert calls == [[PEER], [PEER]]


def test_peer_heads_capped_most_recent(env, monkeypatch):
    monkeypatch.setattr(live_data, "PEER_CAP", 2)
    monkeypatch.setattr(intel, "PEER_MAX", 1)
    env["products"].docs += [product(f"64c00000000000000000001{i}", title=f"Áo {i}", updated_at=datetime(2026, 1, i + 1))
                             for i in range(5)]
    assert [h[0] for h in live_data.peer_heads("fashion", PID)] == [PEER, "64c000000000000000000014"]
    assert service.analyze(listing(), AT, persist=False)["peers"] == {"group": "fashion", "size": 2}
    assert len(intel._PEER_ROWS) == 1


def test_suggestions_only_lexicon_or_approved():
    junk = ("mrm", "shopn6", "nhẹ duwa", "duwa hàng", "bụi leather", "nắng chống", "vali áo", "nam tính")
    lift = {"fashion": {**{t: 1.2 for t in junk}, "cotton": 0.5, "basic": 0.4, "xanh": 0.2, "len": -0.3}}
    _, _, sugg = tag_report(["áo"], "áo khoác", "fashion", lift, set(), set(), None, None)
    assert [s["tag"] for s in sugg] == ["cotton", "xanh"]
    _, _, sugg = tag_report([], "áo", "fashion", lift, set(), set(), None, None, approved={"Basic"})
    assert [s["tag"] for s in sugg] == ["cotton", "basic", "xanh"]
    assert tag_report(["áo"], "áo", "fashion", lift, set(), set(), None, None, suggest=False)[2] == []


def test_weekly_series_caches_empty_then_uses_snapshot(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(ts, "_from_mongo", lambda: calls.append(1) or pd.DataFrame(columns=ts.COLS))
    monkeypatch.setattr(ts, "PARQUET", tmp_path / "none.parquet")
    monkeypatch.setattr(ts, "SNAPSHOT", tmp_path / "none.json")
    monkeypatch.setitem(ts._cache, "data", None)
    assert ts.weekly_series() == {} and ts.weekly_series() == {} and calls == [1]
    series = {"k": pd.Series([1.0, 2.0], index=pd.to_datetime(["2026-01-04", "2026-01-11"]))}
    (tmp_path / "s.json").write_text(json.dumps(snapshot(series)), "utf-8")
    monkeypatch.setattr(ts, "SNAPSHOT", tmp_path / "s.json")
    monkeypatch.setitem(ts._cache, "data", None)
    assert ts.weekly_series()["k"].tolist() == [1.0, 2.0]


def test_fetch_models_pins_revision_and_checks_sha(monkeypatch, tmp_path):
    data, urls = b"onnx bytes", []
    monkeypatch.setattr(fm, "MODEL_DIR", tmp_path)
    monkeypatch.setitem(fm.SHA256, "tokenizer.json", hashlib.sha256(data).hexdigest())
    monkeypatch.setattr(fm.urllib.request, "urlopen", lambda url, timeout: urls.append(url) or io.BytesIO(data))
    fm.fetch("tokenizer.json")
    fm.fetch("tokenizer.json")
    assert (tmp_path / "tokenizer.json").read_bytes() == data and len(urls) == 1 and fm.REVISION in urls[0]
    (tmp_path / "tokenizer.json").unlink()
    monkeypatch.setitem(fm.SHA256, "tokenizer.json", "0" * 64)
    with pytest.raises(SystemExit):
        fm.fetch("tokenizer.json")
    assert list(tmp_path.iterdir()) == []


def test_index_failure_does_not_block_writes(env, monkeypatch, caplog):
    def boom(self, keys, **kw):
        raise OperationFailure("not authorized")

    monkeypatch.setattr(_FakeCollection, "create_index", boom, raising=False)
    service.analyze(listing(), AT, persist=True)
    store._indexed["thread"].join(5)
    assert len(env["listing_intel_scores"].docs) == 1 and "index creation failed" in caplog.text


def test_preview_output_omits_product_id(env):
    out = service.analyze(listing(product_id=None), AT, persist=True)
    assert "product_id" not in out and env["listing_intel_scores"].docs == []
