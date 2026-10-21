import json

import numpy as np

from app.core.listing_intel import features as F
from app.core.listing_intel import formulas
from scripts.li.embed_cache import features_dir
from scripts.li.fit import AXIS_PARAMS
from scripts.li.image_formula_check import check
from scripts.li.image_robust import COLSETS, derived, perturbed, score, val_rows
from scripts.li.imgcheck import scorers
from scripts.li.train import MODEL_DIR, load_table

OUT = features_dir() / "image_runtime.json"
CACHE = features_dir() / "val_perturb_runtime.parquet"
PATH = "ảnh validation → biến đổi → image_load.as_trained (thu về 256 px, JPEG q85) → feature, như lúc phục vụ"


def run():
    table = derived(load_table())
    train = table[(table["split"] == "train") & table["emb_pca_0"].notna()]
    val = val_rows(table)
    frames = perturbed(val, CACHE)
    served = scorers(MODEL_DIR)["formula"]
    parity = np.abs(served(frames["gốc"]) - served(val))
    params = {k: v for k, v in AXIS_PARAMS["image"].items() if k != "early_stopping"}
    return {"n_val": int(len(val)), "path": PATH,
            "parity_feature_max_abs": round(float(np.nanmax(np.abs(frames["gốc"][F.IMAGE_COLS].to_numpy()
                                                                    - val[F.IMAGE_COLS].to_numpy()))), 4),
            "parity_formula_pct": {"median": round(float(np.median(parity)), 2),
                                   "p90": round(float(np.percentile(parity, 90)), 2)},
            "formula": check(formulas.image, frames, val),
            "model": score(params, COLSETS["all"], train, val, frames)}


if __name__ == "__main__":
    res = run()
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1), "utf-8")
    print(json.dumps(res, ensure_ascii=False, indent=1))
