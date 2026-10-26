import itertools
import json

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score

from app.core.listing_intel import features as F
from app.core.listing_intel.context import load_context
from scripts.f29_ml.evaluate import auc_ci
from scripts.li import imgcheck
from scripts.li.embed_cache import features_dir, load_image
from scripts.li.fit import frame
from scripts.li.measure import sellers
from scripts.li.reference import QS
from scripts.li.train import load_table

OUT = features_dir() / "image_robust.json"
CACHE = features_dir() / "val_perturb.parquet"
RAW_EXPOSURE = ("img_brightness", "img_contrast")
EMB = [c for c in F.IMAGE_COLS if c.startswith("emb_pca_")]
SEMANTIC = ["sim_title", "sim_category", *(f"style_{s}" for s in F.STYLES)]
COLSETS = {
    "all": F.IMAGE_COLS,
    "no_raw_exposure": [c for c in F.IMAGE_COLS if c not in RAW_EXPOSURE] + ["img_exposure_ok"],
    "no_emb_pca": [c for c in F.IMAGE_COLS if c not in EMB],
    "no_emb_pca_raw_exposure": [c for c in F.IMAGE_COLS if c not in EMB + list(RAW_EXPOSURE)] + ["img_exposure_ok"],
    "quality_only": [c for c in F.QUALITY_COLS if c not in RAW_EXPOSURE] + ["img_exposure_ok"],
}
GRID = {"max_depth": (3, 4), "min_samples_leaf": (40, 100), "l2_regularization": (1.0, 10.0),
        "max_iter": (10, 25, 50, 100, 200, 400)}
LI11 = {"max_depth": None, "min_samples_leaf": 20, "l2_regularization": 0.0, "max_iter": 400}
MAX_SHIFT = imgcheck.MAX_SHIFT
RULE = (f"cận dưới CI95 ROC-AUC validation > 0,5, rồi chọn lệch trung vị lớn nhất (3 biến đổi) nhỏ nhất, hoà thì "
        f"AUC cao hơn; mục tiêu ≤ {MAX_SHIFT} điểm phân vị")


def derived(df):
    return df.assign(img_exposure_ok=F.exposure_ok(df["img_brightness"]))


def perturbed(val, cache=CACHE):
    if cache.exists():
        return {n: g.drop(columns="variant").set_index(val.index) for n, g in pd.read_parquet(cache).groupby("variant")}
    ctx = load_context(features_dir() / "context", trend_series={})
    z = np.load(features_dir() / "emb.npz")
    pos = {(s, i): k for k, (s, i) in enumerate(zip(z["source"], z["listing_id"]))}
    txt = z["txt"]
    title_vecs = [txt[pos[("tiki26", i)]].astype(np.float32) for i in val["listing_id"]]
    base = [load_image(u) for u in val["image_url"]]
    images = {"gốc": base} | {n: [f(im) for im in base] for n, f in imgcheck.VARIANTS.items()}
    out = {n: imgcheck.features_for(val, ims, title_vecs, ctx) for n, ims in images.items()}
    pd.concat([df.assign(variant=n) for n, df in out.items()]).reset_index(drop=True).to_parquet(cache, index=False)
    return out


def score(params, cols, train, val, frames):
    cols = cols + ["group"]
    model = HistGradientBoostingClassifier(learning_rate=0.05, random_state=42, early_stopping=False, **params)
    model.fit(frame(train, cols), train["top25"])
    preds = {n: model.predict_proba(frame(derived(df).assign(group=val["group"]), cols))[:, 1] for n, df in frames.items()}
    y, groups, p0 = val["top25"].to_numpy(), val["group"].to_numpy(str), preds["gốc"]
    dist = lambda p: np.array([np.interp(x, np.percentile(p0[groups == g], QS), QS) for x, g in zip(p, groups)])
    base = dist(p0)
    moved = {n: np.abs(dist(p) - base) for n, p in preds.items() if n != "gốc"}
    shifts = {n: round(float(np.median(d)), 2) for n, d in moved.items()}
    return {"auc": round(float(roc_auc_score(y, p0)), 3), "ci95": auc_ci(y, p0, sellers(val)), "shifts": shifts,
            "max_shift": max(shifts.values()), "p90_shift": round(float(max(np.percentile(d, 90) for d in moved.values())), 2),
            "n_distinct": int(len(np.unique(p0)))}


def val_rows(table):
    val = table[(table["source"] == "tiki26") & (table["split"] == "val") & table["image_url"].notna()]
    return val[[load_image(u) is not None for u in val["image_url"]]]


def run():
    table = derived(load_table())
    train = table[(table["split"] == "train") & table["emb_pca_0"].notna()]
    val = val_rows(table)
    frames = perturbed(val)
    gap = float(np.nanmax(np.abs(frames["gốc"][F.IMAGE_COLS].to_numpy() - val[F.IMAGE_COLS].to_numpy())))
    rows = [{"cols": "all", "params": LI11, "li11": True, **score(LI11, COLSETS["all"], train, val, frames)}]
    for name, values in itertools.product(COLSETS, itertools.product(*GRID.values())):
        params = dict(zip(GRID, values))
        rows.append({"cols": name, "params": params, **score(params, COLSETS[name], train, val, frames)})
    ok = [r for r in rows if r["ci95"][0] > 0.5]
    best = min(ok or rows, key=lambda r: (r["max_shift"], -r["auc"]))
    return {"rule": RULE, "n_val": int(len(val)), "parity_max_abs": gap, "colsets": COLSETS, "grid": GRID,
            "rows": rows, "chosen": best, "meets_target": best["max_shift"] <= MAX_SHIFT and bool(ok)}


if __name__ == "__main__":
    res = run()
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1), "utf-8")
    top = sorted(res["rows"], key=lambda r: (r["ci95"][0] <= 0.5, r["max_shift"]))[:12]
    for r in [res["rows"][0], *top]:
        print(r["cols"], r["params"], r["auc"], r["ci95"], r["shifts"], r["p90_shift"], r["n_distinct"])
    print("chosen:", res["chosen"]["cols"], res["chosen"]["params"], "meets target:", res["meets_target"],
          "parity:", res["parity_max_abs"])
