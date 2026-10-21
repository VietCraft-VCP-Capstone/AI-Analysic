import json
import math
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

from app.core.listing_intel.context import FeatureContext, save_context
from app.core.listing_intel.formulas import FORMULAS, title_keys
from app.core.listing_intel.fusion import top_medians
from scripts.li.fit import AXIS_MODELS, FULL, axis_cols, defined, predict

QS = np.arange(101)
MIN_REF = 20
CONTEXT_FILES = ["lift.json", "group_median_price.json", "group_season.json", "pca.npz",
                 "prompt_vecs.npz", "trend_kw_vecs.npz", "centroids.npz", "thresholds.json"]
DESIGN = "image_design.json"


def population(table):
    val = table[table["split"] == "val"]
    counts = val["group"].value_counts()
    small = set(table["group"].dropna()) - set(counts[counts >= MIN_REF].index)
    return pd.concat([val[~val["group"].isin(small)], table[table["group"].isin(small)]])


def _dist(df, s, prefix=""):
    parts = [(str(g), np.asarray(i)) for g, i in df.groupby("group", observed=True).indices.items()]
    return {f"{prefix}{g}": np.percentile(s[idx], QS) for g, idx in parts + [("all", np.arange(len(df)))]}


def median_prices(table):
    train = table[table["split"] == "train"].dropna(subset=["log_price"])
    out = {str(g): math.exp(v) for g, v in train.groupby("group", observed=True)["log_price"].median().items()}
    return out | {"all": math.exp(train["log_price"].median())}


def _context(table, ref, context_dir):
    if context_dir is None:
        save_context(FeatureContext(group_median_price=median_prices(table)), ref)
        return
    src = Path(context_dir)
    for p in [src / f for f in CONTEXT_FILES] + sorted(src.glob("knn_*.npz")):
        shutil.copy2(p, ref / p.name)


def image_design(src: Path):
    robust, formula = src / "image_robust.json", src / "image_formula.json"
    if not (robust.exists() and formula.exists()):
        return None
    rb, fc = json.loads(robust.read_text("utf-8")), json.loads(formula.read_text("utf-8"))
    return {"n_val": rb["n_val"], "configs": len(rb["rows"]), "model": rb["chosen"],
            "formula": {"name": fc["chosen"], **fc["rows"][fc["chosen"]]}}


def write(table, models, ref, context_dir=None):
    ref = Path(ref)
    ref.mkdir(parents=True, exist_ok=True)
    _context(table, ref, context_dir)
    design = image_design(Path(context_dir).parent) if context_dir else None
    if design:
        (ref / DESIGN).write_text(json.dumps(design, ensure_ascii=False, indent=1), "utf-8")
    (ref / "top_medians.json").write_text(json.dumps(top_medians(table), ensure_ascii=False), "utf-8")
    pop = population(table)
    np.savez(ref / "score_dist.npz", **_dist(pop, predict(models["fusion"], pop, FULL)))
    axes = {}
    for a in AXIS_MODELS:
        p = defined(pop, a)
        axes |= _dist(p, predict(models[a], p, axis_cols(a)), f"{a}__") if len(p) else {}
    np.savez(ref / "axis_dist.npz", **axes)
    np.savez(ref / "formula_dist.npz", **formula_dist(pop))
    return design


def formula_values(df, axis):
    recs = df.to_dict("records")
    if axis == "text":
        recs = [{**r, **title_keys(r["title"] if isinstance(r.get("title"), str) else "", [], r.get("group"))}
                for r in recs]
    return np.array([FORMULAS[axis](r) for r in recs], dtype=float)


def formula_dist(pop):
    out = {}
    for a in AXIS_MODELS:
        p = defined(pop, a)
        v = formula_values(p, a) if len(p) else np.empty(0)
        ok = ~np.isnan(v)
        out |= _dist(p[ok], v[ok], f"{a}__") if ok.any() else {}
    return out
