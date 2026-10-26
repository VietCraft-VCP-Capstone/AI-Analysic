import math

import numpy as np

from .context import FeatureContext
from .formulas import title_keys
from .market_axis import centroid_margin, knn_features
from .normalize import norm
from .text_axis import text_features
from .trend_axis import demand_factor, match_keywords, momentum
from .types import ListingInput
from .vision import BRIGHTNESS_RANGE

NAN = float("nan")
STYLES = ("white_bg", "lifestyle", "flatlay", "closeup")
STYLE_TEMPERATURE = 100.0
PCA_DIM = 16
QUALITY_COLS = [
    "img_w", "img_h", "img_aspect", "img_sharpness", "img_brightness",
    "img_contrast", "img_border_uniform", "img_center_edges", "img_text_ratio",
]
META_COLS = ["log_price", "price_rel", "n_images"]
TEXT_COLS = list(text_features(ListingInput(title=""), None))
IMAGE_COLS = [
    *QUALITY_COLS, "sim_title", "sim_category",
    *(f"style_{s}" for s in STYLES), *(f"emb_pca_{i}" for i in range(PCA_DIM)),
]
MARKET_COLS = ["knn_price_pct", "knn_dup_count", "top_centroid_margin"]
TREND_COLS = ["trend_factor", "trend_matches", "trend_momentum_max"]
FEATURE_COLS = META_COLS + TEXT_COLS + IMAGE_COLS + MARKET_COLS + TREND_COLS


def exposure_ok(brightness) -> np.ndarray:
    b = np.asarray(brightness, dtype=float)
    return np.where(np.isnan(b), np.nan, ((b >= BRIGHTNESS_RANGE[0]) & (b <= BRIGHTNESS_RANGE[1])).astype(float))


def unit(v) -> np.ndarray:
    v = np.asarray(v, dtype=np.float32)
    n = np.linalg.norm(v, axis=-1, keepdims=True)
    return v / np.where(n == 0, 1.0, n)


def market_vec(img_vec, title_vec) -> np.ndarray:
    return unit(unit(img_vec) + unit(title_vec))


def _cos(a, b) -> float:
    return NAN if a is None or b is None else float(np.dot(unit(a), unit(b)))


def image_semantics(img_vec, title_vec, group, prompt_vecs) -> dict[str, float]:
    out = {"sim_title": _cos(img_vec, title_vec), "sim_category": _cos(img_vec, prompt_vecs.get(group))}
    sims = np.array([_cos(img_vec, prompt_vecs.get(f"style_{s}")) for s in STYLES]) * STYLE_TEMPERATURE
    probs = np.exp(sims - sims.max())
    probs = probs / probs.sum()
    out.update({f"style_{s}": float(p) for s, p in zip(STYLES, probs)})
    return out


def _meta(inp: ListingInput, ctx: FeatureContext) -> dict[str, float]:
    price = inp.price if inp.price is not None and inp.price > 0 else None
    median = ctx.group_median_price.get(inp.group) or ctx.group_median_price.get("all")
    return {
        "log_price": math.log(price) if price else NAN,
        "price_rel": math.log(price / median) if price and median else NAN,
        "n_images": float(len(inp.image_urls or [])),
    }


def _image(img_feats, title_vec, group, ctx: FeatureContext) -> dict[str, float]:
    out = dict.fromkeys(IMAGE_COLS, NAN)
    if img_feats is None:
        return out
    out.update({c: float(img_feats[c]) for c in QUALITY_COLS if c in img_feats})
    vec = img_feats.get("vec")
    if vec is None:
        return out
    out.update(image_semantics(vec, title_vec, group, ctx.prompt_vecs))
    if ctx.pca is not None:
        pcs = ctx.pca.transform(np.asarray(vec, dtype=np.float64)[None])[0]
        out.update({f"emb_pca_{i}": float(x) for i, x in enumerate(pcs)})
    return out


def _market(img_vec, title_vec, price, group, ctx: FeatureContext, exclude) -> dict[str, float]:
    out = dict.fromkeys(MARKET_COLS, NAN)
    if img_vec is None or title_vec is None:
        return out
    vec = market_vec(img_vec, title_vec)
    index = ctx.knn.get(group)
    if index is not None:
        knn = knn_features(vec, price, index, exclude=exclude)
        out.update(knn_price_pct=knn["knn_price_pct"], knn_dup_count=knn["knn_dup_count"])
    pair = ctx.centroids.get(group)
    if pair is not None:
        out["top_centroid_margin"] = centroid_margin(vec, *pair)
    return out


def trend_matches(inp: ListingInput, text_vec, ctx: FeatureContext) -> list:
    locked = ctx.trend_keywords
    kws = [k for k in ctx.trend_kw_vecs if k in ctx.trend_series and (locked is None or k in locked)]
    vecs = np.stack([ctx.trend_kw_vecs[k] for k in kws]) if kws else None
    return match_keywords(norm(inp.title).split(), kws, vecs, text_vec, ctx.trend_match_cos)


def trend_demand(matches, ctx: FeatureContext, group, at=None) -> float:
    return demand_factor(matches, ctx.trend_series, at or ctx.at, ctx.group_season.get(group))


def _trend(inp: ListingInput, title_vec, ctx: FeatureContext) -> dict[str, float]:
    matches = trend_matches(inp, title_vec, ctx)
    moms = [momentum(ctx.trend_series[k], ctx.at) for k, _ in matches]
    return {
        "trend_factor": trend_demand(matches, ctx, inp.group),
        "trend_matches": float(len(matches)),
        "trend_momentum_max": max(moms, default=0.0),
    }


def assemble(inp: ListingInput, img_feats: dict | None, ctx: FeatureContext,
             title_vec=None, exclude: int | None = None) -> dict[str, float]:
    img_vec = None if img_feats is None else img_feats.get("vec")
    out = _meta(inp, ctx)
    out.update(text_features(inp, ctx.lift))
    out.update(title_keys(inp.title, inp.materials, inp.group))
    out.update(_image(img_feats, title_vec, inp.group, ctx))
    out.update(_market(img_vec, title_vec, inp.price, inp.group, ctx, exclude))
    out.update(_trend(inp, title_vec, ctx))
    return out
