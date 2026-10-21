import json

import numpy as np
from sklearn.metrics import roc_auc_score

from app.core.listing_intel import formulas
from scripts.f29_ml.evaluate import auc_ci
from scripts.li.embed_cache import features_dir
from scripts.li.image_robust import MAX_SHIFT, perturbed, val_rows
from scripts.li.measure import sellers
from scripts.li.reference import QS
from scripts.li.train import load_table

OUT = features_dir() / "image_formula.json"
LI13 = {"sharpness": 0.25, "exposure": 0.2, "border": 0.15, "no_text": 0.15, "sim_title": 0.15, "sim_category": 0.1}
CANDIDATES = {
    "c1_semantic_0.2": {"sharpness": 0.25, "exposure_ok": 0.1, "contrast_ok": 0.1, "border": 0.15, "no_text": 0.15,
                        "resolution": 0.05, "sim_title": 0.1, "sim_category": 0.1},
    "c2_semantic_0.1": {"sharpness": 0.3, "exposure_ok": 0.1, "contrast_ok": 0.1, "border": 0.2, "no_text": 0.15,
                        "resolution": 0.05, "sim_title": 0.05, "sim_category": 0.05},
    "c3_semantic_0.3": {"sharpness": 0.2, "exposure_ok": 0.1, "contrast_ok": 0.1, "border": 0.15, "no_text": 0.1,
                        "resolution": 0.05, "sim_title": 0.15, "sim_category": 0.15},
    "c4_no_semantic": {"sharpness": 0.35, "exposure_ok": 0.1, "contrast_ok": 0.1, "border": 0.25, "no_text": 0.15,
                       "resolution": 0.05},
    "c5_rel_sharp_no_semantic": {"sharpness_rel": 0.35, "exposure_ok": 0.1, "contrast_ok": 0.1, "border": 0.25,
                                 "no_text": 0.15, "resolution": 0.05},
    "c6_rel_sharp_semantic_0.1": {"sharpness_rel": 0.3, "exposure_ok": 0.1, "contrast_ok": 0.1, "border": 0.2,
                                  "no_text": 0.15, "resolution": 0.05, "sim_title": 0.05, "sim_category": 0.05},
    "c7_rel_sharp_semantic_0.2": {"sharpness_rel": 0.25, "exposure_ok": 0.1, "contrast_ok": 0.1, "border": 0.15,
                                  "no_text": 0.15, "resolution": 0.05, "sim_title": 0.1, "sim_category": 0.1},
    "c8_rel_sharp_flags_0.05": formulas.IMAGE_WEIGHTS,
}
RULE = f"mọi lệch trung vị ≤ {MAX_SHIFT}, rồi p90 lớn nhất nhỏ nhất"


def _legacy(feats):
    b = feats["img_brightness"]
    gap = max(formulas.BRIGHTNESS_RANGE[0] - b, b - formulas.BRIGHTNESS_RANGE[1], 0.0)
    parts = {k: v for k, v in formulas.image_parts(feats).items() if k in LI13}
    return formulas.mix(parts | {"exposure": max(0.0, 1 - gap / 0.1)}, LI13)


def check(score, frames, val):
    groups, y = val["group"].to_numpy(str), val["top25"].to_numpy()
    vals = {n: np.array([score(r) for r in df.to_dict("records")]) for n, df in frames.items()}
    ref = {g: np.percentile(vals["gốc"][groups == g], QS) for g in np.unique(groups)}
    pct = {n: np.array([np.interp(x, ref[g], QS) for x, g in zip(v, groups)]) for n, v in vals.items()}
    moved = {n: np.abs(p - pct["gốc"]) for n, p in pct.items() if n != "gốc"}
    return {"median_shift": {n: round(float(np.median(d)), 2) for n, d in moved.items()},
            "p90_shift": {n: round(float(np.percentile(d, 90)), 2) for n, d in moved.items()},
            "auc": round(float(roc_auc_score(y, vals["gốc"])), 3), "ci95": auc_ci(y, vals["gốc"], sellers(val))}


def run():
    val = val_rows(load_table())
    frames = perturbed(val)
    rows = {"li-1.3": check(_legacy, frames, val)}
    rows |= {n: check(lambda r, w=w: formulas.image(r, w), frames, val) for n, w in CANDIDATES.items()}
    ok = [n for n in CANDIDATES if max(rows[n]["median_shift"].values()) <= MAX_SHIFT]
    best = min(ok or CANDIDATES, key=lambda n: max(rows[n]["p90_shift"].values()))
    return {"rule": RULE, "n_val": int(len(val)), "candidates": CANDIDATES, "rows": rows, "chosen": best,
            "served_weights_match": CANDIDATES[best] == formulas.IMAGE_WEIGHTS}


if __name__ == "__main__":
    res = run()
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1), "utf-8")
    for n, r in res["rows"].items():
        print(n, r)
    print("chosen:", res["chosen"], "| served weights match:", res["served_weights_match"])
