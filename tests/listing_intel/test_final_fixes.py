from datetime import date

import numpy as np
import pandas as pd
import pytest

from app.core.listing_intel import advice, axes, fusion, service, trend_axis, trend_store
from app.core.listing_intel import features as F
from app.core.listing_intel.tags_axis import tag_report
from app.core.listing_intel.types import AxisResult, ListingInput
from tests.listing_intel.intel_support import env, listing  # noqa: F401

AT = date(2026, 10, 21)


def test_no_image_fashion_listing_gets_add_images_impact(monkeypatch):
    monkeypatch.delenv("LI_BUNDLE_DIR", raising=False)
    if not (fusion.DEFAULT_DIR / "meta.json").exists():
        pytest.skip("chưa có model bundle")
    monkeypatch.setattr(trend_store, "weekly_series", dict)
    inp = ListingInput(title="Áo khoác jean nữ form rộng", description="Áo khoác jean mềm " * 20, tags=["áo khoác"],
                       materials=["jean"], category="Áo khoác", group="fashion", price=350000.0)
    feats = F.assemble(inp, None, fusion.context(AT), None)
    impact = fusion.impacts(feats, "fashion", {"no_images": advice.FIXES["no_images"]})
    assert impact["no_images"] > 0


def test_best_impact_advice_never_dropped():
    measured = AxisResult(issues=[{"code": c, "message": "m"} for c in
                                  ("blurry", "too_dark", "low_resolution", "busy_background", "text_overlay", "bad_aspect")])
    res = {"image": measured, "text": AxisResult(issues=[{"code": "no_images", "message": "m"}])}
    out = advice.build(res, {}, {"image": "measured"}, {"no_images": 30.0, "blurry": 1.0})
    assert len(out) == advice.MAX_ITEMS and out[-1]["code"] == "no_images"
    ranked = advice.build(res, {}, {}, {"no_images": 30.0, "blurry": 1.0})
    assert ranked[0]["code"] == "no_images"


def test_season_cache_survives_concurrent_clear(monkeypatch):
    class Racy(dict):
        def __setitem__(self, k, v):
            super().__setitem__(k, v)
            self.clear()

    monkeypatch.setattr(trend_axis, "_SEASON_CACHE", Racy())
    s = pd.Series(np.arange(60, dtype=float) % 7 + 1, index=pd.date_range("2025-01-05", periods=60, freq="W-SUN"))
    assert len(trend_axis.cached_season("k", s)) == 52


def test_calendar_keywords_follow_event_topic_and_hide_stale_momentum():
    idx = pd.date_range("2021-08-15", "2026-08-16", freq="W-SUN")
    peak = lambda w: pd.Series(np.where(idx.isocalendar().week.to_numpy() == w, 50.0, 1.0), index=idx)
    series = {"quà 20/11": peak(46), "quà giáng sinh": peak(51), "áo thun": peak(46)}
    event = {"key": "20/11", "date": date(2026, 11, 20), "prep_start": date(2026, 10, 30)}
    assert service._event_keywords(series, event, AT) == [{"term": "quà 20/11", "momentum": None}]
    assert service._event_keywords(series, event, date(2026, 8, 20))[0]["momentum"] is not None


def test_capped_reason_flags_no_images(env):
    assert service.analyze(listing(image_urls=[]), AT, persist=False)["capped_reason"] == "no_images"
    assert service.analyze(listing(), AT, persist=False)["capped_reason"] is None


def test_market_reason_matches_cause():
    assert axes.market_axis(None, None, {}, has_image=True).missing_reason == axes.NO_MARKET_GROUP
    assert axes.market_axis(None, None, {}, has_image=False).missing_reason == axes.NO_MARKET_IMAGE


def test_tag_reason_uses_vietnamese_label_and_comma():
    _, _, sugg = tag_report(["áo"], "áo khoác", "fashion", {"fashion": {"cotton": 0.25}}, set(), set(), None, None)
    assert sugg[0]["reason"].endswith("nhóm Thời trang (độ lift 0,25)")
