import math
from dataclasses import replace
from datetime import date

import numpy as np
import pandas as pd
import pytest
from sklearn.decomposition import PCA

from app.core.listing_intel import features as F
from app.core.listing_intel.context import FeatureContext, load_context, save_context
from app.core.listing_intel.market_axis import KnnIndex
from app.core.listing_intel.types import ListingInput

BANNED = {
    "review_count", "rating_average", "favourite_count", "order_count", "revenue_estimate",
    "quantity_sold", "inventory_status", "badges", "is_official_store", "discount",
    "discount_rate", "has_video", "fulfillment_type", "brand",
}
LABEL_DERIVED = {"age_days", "sold", "top25", "split", "seller", "listing_id", "source", "scraped_at"}
ALL = F.META_COLS + F.TEXT_COLS + F.IMAGE_COLS + F.MARKET_COLS + F.TREND_COLS


def unit(m):
    return m / np.linalg.norm(m, axis=-1, keepdims=True)


def rich_ctx(tmp_dim=32):
    rng = np.random.default_rng(0)
    prompts = {k: unit(rng.normal(size=tmp_dim)).astype(np.float32) for k in ("bags", *(f"style_{s}" for s in F.STYLES))}
    vecs = unit(rng.normal(size=(30, tmp_dim))).astype(np.float16)
    top = np.arange(30) % 4 == 0
    weeks = pd.date_range("2022-01-02", periods=150, freq="W-SUN")
    series = {"túi da": pd.Series(np.linspace(10, 50, 150), index=weeks)}
    return FeatureContext(
        lift={"bags": {"túi": 0.2, "da": -0.1}},
        group_median_price={"bags": 100000.0, "all": 80000.0},
        pca=PCA(16, random_state=0).fit(rng.normal(size=(40, tmp_dim))),
        prompt_vecs=prompts,
        knn={"bags": KnnIndex(vecs, np.linspace(1e4, 3e5, 30), top)},
        trend_series=series,
        trend_kw_vecs={"túi da": unit(rng.normal(size=tmp_dim)).astype(np.float32), "chưa có": prompts["bags"]},
        group_season={"bags": np.full(52, 1.2)},
        at=date(2026, 4, 18),
        centroids={"bags": (unit(rng.normal(size=tmp_dim)), unit(rng.normal(size=tmp_dim)))},
    )


def test_assemble_has_all_columns():
    out = F.assemble(ListingInput(title="Túi da nữ"), None, FeatureContext())
    assert set(ALL) <= set(out)
    assert all(math.isnan(out[c]) for c in F.IMAGE_COLS)


def test_price_rel_uses_group_median():
    ctx = FeatureContext(group_median_price={"bags": 100000.0})
    out = F.assemble(ListingInput(title="Túi", group="bags", price=200000), None, ctx)
    assert out["price_rel"] == pytest.approx(math.log(2))


def test_no_banned_columns():
    assert not (BANNED | LABEL_DERIVED) & set(ALL)
    assert len(ALL) == len(set(ALL)) == len(F.FEATURE_COLS)


def test_image_semantics_softmax_and_cosines():
    ctx = rich_ctx()
    img = ctx.prompt_vecs["style_flatlay"]
    out = F.image_semantics(img, img, "bags", ctx.prompt_vecs)
    styles = [out[f"style_{s}"] for s in F.STYLES]
    assert sum(styles) == pytest.approx(1.0)
    assert max(styles) == out["style_flatlay"]
    assert out["sim_title"] == pytest.approx(1.0)
    assert math.isnan(F.image_semantics(img, None, None, ctx.prompt_vecs)["sim_category"])


def test_assemble_with_image_fills_image_market_trend():
    ctx = rich_ctx()
    rng = np.random.default_rng(1)
    img = {"vec": unit(rng.normal(size=32)).astype(np.float32), "img_w": 256.0}
    inp = ListingInput(title="Túi da bò", group="bags", price=150000, image_urls=["u"])
    out = F.assemble(inp, img, ctx, title_vec=unit(rng.normal(size=32)))
    assert not any(math.isnan(out[c]) for c in F.MARKET_COLS + F.TREND_COLS)
    assert not math.isnan(out["emb_pca_15"]) and out["img_w"] == 256.0
    assert out["trend_matches"] == 1.0 and out["trend_momentum_max"] > 0
    assert 0.5 <= out["trend_factor"] <= 1.5
    assert out["kw_lift_terms"] == 2.0 and out["n_images"] == 1.0


def test_trend_falls_back_to_group_season_without_series():
    ctx = replace(rich_ctx(), trend_series={})
    out = F.assemble(ListingInput(title="Túi da", group="bags"), None, ctx)
    assert out["trend_matches"] == 0.0 and out["trend_momentum_max"] == 0.0
    assert out["trend_factor"] == pytest.approx(1.2)


def test_exclude_drops_self_duplicate():
    ctx = rich_ctx()
    vec = ctx.knn["bags"].vecs[3].astype(np.float32)
    title = np.zeros(32, np.float32)
    inp = ListingInput(title="x", group="bags", price=1e5)
    img = {"vec": vec}
    assert F.assemble(inp, img, ctx, title_vec=title + vec)["knn_dup_count"] >= 1
    assert F.assemble(inp, img, ctx, title_vec=title + vec, exclude=3)["knn_dup_count"] == 0


def test_context_roundtrip_gives_same_features(tmp_path):
    ctx = rich_ctx()
    save_context(ctx, tmp_path)
    back = load_context(tmp_path, at=ctx.at, trend_series=ctx.trend_series)
    rng = np.random.default_rng(2)
    img = {"vec": unit(rng.normal(size=32)).astype(np.float32)}
    inp = ListingInput(title="Túi da bò", group="bags", price=150000)
    a = F.assemble(inp, img, ctx, title_vec=img["vec"])
    b = F.assemble(inp, img, back, title_vec=img["vec"])
    assert a.keys() == b.keys()
    assert all(a[k] == b[k] or (math.isnan(a[k]) and math.isnan(b[k])) for k in a)


def test_group_season_maps_months_to_iso_weeks():
    from scripts.li.fit_context import group_season

    monthly = pd.DataFrame({"group": "home", "month": range(1, 13), "index": [2.0] + [1.0] * 11})
    season = group_season(monthly)["home"]
    assert season.shape == (52,)
    assert season[:4].tolist() == [2.0] * 4 and season[4] == 1.0
    assert group_season(monthly.iloc[:0]) == {}


def test_seller_folds_keep_seller_together():
    from scripts.li.fit_context import seller_folds

    df = pd.DataFrame({"source": "tiki26", "seller": ["a", "a", "b", None, None, "c", "d", "e"]})
    train = np.array([True] * 7 + [False])
    folds = seller_folds(df, train)
    assert folds[0] == folds[1] and folds[7] == -1
    assert set(folds[:7]) == set(range(5))


def test_trend_vector_match_follows_context_threshold():
    ctx = rich_ctx()
    vec = ctx.trend_kw_vecs["túi da"]
    inp = ListingInput(title="ví cầm tay", group="bags")
    assert F.trend_matches(inp, vec, ctx) == []
    assert [k for k, _ in F.trend_matches(inp, vec, replace(ctx, trend_match_cos=0.9))] == ["túi da"]
    assert F.trend_demand([], ctx, "bags") == pytest.approx(1.2)


def test_trend_keywords_locked_to_training_set(tmp_path):
    ctx = rich_ctx()
    inp = ListingInput(title="Túi da bò", group="bags")
    assert [k for k, _ in F.trend_matches(inp, None, ctx)] == ["túi da"]
    assert F.trend_matches(inp, None, replace(ctx, trend_keywords=["chưa có"])) == []
    save_context(replace(ctx, trend_keywords=["túi da"]), tmp_path)
    assert load_context(tmp_path, trend_series={}).trend_keywords == ["túi da"]
    assert not list(tmp_path.glob("*.joblib")) and (tmp_path / "pca.npz").exists()
