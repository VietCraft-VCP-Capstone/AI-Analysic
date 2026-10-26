import json
import logging
import math
import os
import threading
from dataclasses import dataclass, replace
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn

from app.core.calendar_vn import ALL_GROUPS

from . import formulas, trend_store
from .context import FeatureContext, load_context
from .features import IMAGE_COLS, MARKET_COLS

DEFAULT_DIR = Path(__file__).parent / "model"
QS = np.arange(101, dtype=float)
MASK_BELOW, IMPUTE_FROM = 0.01, 0.99
PARITY_KEYS = ("feature_availability", "feature_constants", "image_impute")
log = logging.getLogger(__name__)
_lock = threading.Lock()
_cache: dict = {}
_warned: set = set()


@dataclass
class Bundle:
    meta: dict
    models: dict
    score_dist: dict
    axis_dist: dict
    formula_dist: dict
    ctx: FeatureContext
    top_medians: dict


def bundle_dir() -> Path:
    return Path(os.environ.get("LI_BUNDLE_DIR") or DEFAULT_DIR)


def _load(path: Path) -> Bundle:
    meta = json.loads((path / "meta.json").read_text("utf-8"))
    if meta.get("sklearn") != sklearn.__version__:
        raise RuntimeError(f"Bundle học bằng scikit-learn {meta.get('sklearn')}, đang chạy {sklearn.__version__}")
    ref = path / "reference"
    tops = ref / "top_medians.json"
    return Bundle(
        meta=meta,
        models={"fusion": joblib.load(path / "fusion.joblib"),
                **{a: joblib.load(path / f"axis_{a}.joblib") for a in meta["axis_features"]}},
        score_dist=dict(np.load(ref / "score_dist.npz")),
        axis_dist={tuple(k.split("__", 1)): v for k, v in np.load(ref / "axis_dist.npz").items()},
        formula_dist={tuple(k.split("__", 1)): v for k, v in np.load(ref / "formula_dist.npz").items()},
        ctx=load_context(ref, trend_series={}),
        top_medians=json.loads(tops.read_text("utf-8")) if tops.exists() else {},
    )


def load_bundle() -> Bundle:
    path = bundle_dir()
    with _lock:
        if _cache.get("path") != path:
            _cache.update(bundle=_load(path), path=path)
        return _cache["bundle"]


def context(at) -> FeatureContext:
    return replace(load_bundle().ctx, at=at, trend_series=trend_store.weekly_series())


def _frame(rows: list[dict], cols: list[str], group) -> pd.DataFrame:
    X = pd.DataFrame(rows).reindex(columns=cols).astype({c: float for c in cols if c != "group"})
    g = group if group in ALL_GROUPS else None
    X["group"] = pd.Categorical([g] * len(rows), categories=ALL_GROUPS)
    return X


def served(feats: dict, group) -> dict:
    meta = load_bundle().meta
    for key in [k for k in PARITY_KEYS if k not in meta and k not in _warned]:
        _warned.add(key)
        log.warning("listing intel: bundle meta has no %s, skipping it", key)
    share = (meta.get("feature_availability") or {}).get(group) or {}
    out = {**feats, **{c: math.nan for c, v in share.items() if v < MASK_BELOW},
           **((meta.get("feature_constants") or {}).get(group) or {})}
    for c, q in ((meta.get("image_impute") or {}).get(group) or {}).items():
        if math.isnan(out.get(c, math.nan)) and share.get(c, 1.0) >= IMPUTE_FROM:
            out[c] = q
    return out


def without_images(feats: dict) -> dict:
    return {**feats, **dict.fromkeys(IMAGE_COLS + MARKET_COLS, math.nan), "n_images": 0.0}


def _scores(rows: list[dict], group) -> np.ndarray:
    b = load_bundle()
    rows = [served(r, group) for r in rows + [without_images(r) for r in rows]]
    p = b.models["fusion"].predict_proba(_frame(rows, b.meta["features"], group))[:, 1]
    s = np.interp(p, b.score_dist.get(group, b.score_dist["all"]), QS)
    return np.maximum(s[:len(s) // 2], s[len(s) // 2:])


def base_score(feats: dict, group) -> float:
    return float(_scores([feats], group)[0])


def axis_mode(axis) -> str:
    return ((load_bundle().meta.get("axis_modes") or {}).get(axis) or {}).get("mode", "model")


def _axis_raw(b, axis, cols, feats, group):
    if axis_mode(axis) == "formula":
        return formulas.FORMULAS[axis](feats), b.formula_dist
    return b.models[axis].predict_proba(_frame([feats], cols, group))[0, 1], b.axis_dist


def axis_scores(feats: dict, group) -> dict[str, float | None]:
    b, out = load_bundle(), {}
    for axis, cols in b.meta["axis_features"].items():
        if all(math.isnan(feats.get(c, math.nan)) for c in cols if c != "group"):
            out[axis] = None
            continue
        raw, dists = _axis_raw(b, axis, cols, feats, group)
        dist = dists.get((axis, group), dists.get((axis, "all")))
        out[axis] = None if dist is None or math.isnan(raw) else float(np.interp(raw, dist, QS))
    return out


def impacts(feats: dict, group, fixes: dict[str, list[str]]) -> dict[str, float]:
    tops = load_bundle().top_medians
    med = tops.get(group) or tops.get("all") or {}
    codes = [c for c, cols in fixes.items() if any(k in med for k in cols)]
    rows = [feats] + [{**feats, **{k: med[k] for k in fixes[c] if k in med}} for c in codes]
    s = np.clip(_scores(rows, group) * feats.get("trend_factor", 1.0), 0, 100)
    return {c: round(max(0.0, float(v - s[0])), 1) for c, v in zip(codes, s[1:])}


def top_medians(table: pd.DataFrame) -> dict:
    from .advice import FIXES

    cols = sorted({c for cs in FIXES.values() for c in cs} & set(table.columns))
    top = table[(table["split"] == "train") & (table["top25"] == 1)]
    med = lambda d: {c: float(v) for c, v in d[cols].median().items() if not math.isnan(v)}
    return {**{str(g): med(d) for g, d in top.groupby("group")}, "all": med(top)}
