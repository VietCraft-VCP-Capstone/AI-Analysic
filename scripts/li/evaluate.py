import json
from datetime import date

import joblib
import numpy as np

from scripts.li import datastats, imgcheck, imgdiag, report, retrieval, sanity, shift, trend_calib, trend_eval
from scripts.li.report_history import history
from scripts.li.image_formula_check import OUT as FORMULA
from scripts.li.image_robust import OUT as ROBUST
from scripts.li.image_runtime import OUT as RUNTIME
from scripts.li.vietcraft_check import OUT as VIETCRAFT
from scripts.li.availability import impute_check
from scripts.li.select_features import OUT as SELECTION
from scripts.li.train import MODEL_DIR, ROOT, finite, load_table

RESULTS = ROOT.parent / "notes" / "docs-listing" / "09_listing_intel_ket_qua_danh_gia.json"
REPORT = ROOT.parent / "notes" / "docs-listing" / "09_LISTING_INTEL_KET_QUA_DANH_GIA.md"
META_KEYS = ["model_version", "sklearn", "onnx_model", "features", "axis_features", "groups", "thresholds",
             "trained_on", "train_data", "trend_keywords", "feature_availability", "image_impute",
             "image_impute_rule", "feature_constants", "metrics", "baselines", "best_baseline", "beats_best_baseline",
             "ablation", "evidence", "axis_modes", "axis_mode_rule", "formulas", "axis_params", "tables", "trend_backtest", "n_iter"]


def coverage(table):
    out = {}
    for src, df in table.groupby("source"):
        out[src] = {"n_images_nan": round(float(df["n_images"].isna().mean()), 3),
                    "desc_empty": round(float((df["desc_len"].fillna(0) == 0).mean()), 3),
                    "has_image": round(float(df["emb_pca_0"].notna().mean()), 3),
                    "trend_matched": round(float((df["trend_matches"] > 0).mean()), 3)}
    return out


def collect():
    table = load_table()
    meta = json.loads((MODEL_DIR / "meta.json").read_text("utf-8"))
    return {
        "generated": date.today().isoformat(),
        "data": datastats.run(table),
        "coverage": coverage(table),
        "model": {k: meta[k] for k in META_KEYS if k in meta},
        "shift": shift.run(table),
        "sanity": sanity.run(table, meta, MODEL_DIR),
        "image_sanity": imgcheck.run(table, MODEL_DIR),
        "image_diag": imgdiag.run(table, MODEL_DIR),
        "retrieval": retrieval.run(),
        "trend": trend_eval.run(),
        "trend_calib": trend_calib.run(),
        "selection": json.loads(SELECTION.read_text("utf-8")) if SELECTION.exists() else None,
        "image_robust": json.loads(ROBUST.read_text("utf-8")) if ROBUST.exists() else None,
        "image_formula": json.loads(FORMULA.read_text("utf-8")) if FORMULA.exists() else None,
        "image_runtime": json.loads(RUNTIME.read_text("utf-8")) if RUNTIME.exists() else None,
        "impute_check": impute_check(table, joblib.load(MODEL_DIR / "fusion.joblib"), meta.get("image_impute") or {}),
        "vietcraft": json.loads(VIETCRAFT.read_text("utf-8")) if VIETCRAFT.exists() else None,
    }


def main():
    old = json.loads(RESULTS.read_text("utf-8")) if RESULTS.exists() else None
    results = finite(json.loads(json.dumps(collect(), ensure_ascii=False, default=lambda o: o.item()
                                           if isinstance(o, np.generic) else str(o))))
    results["history"] = history(old, results["model"]["model_version"])
    RESULTS.write_text(json.dumps(results, ensure_ascii=False, indent=1, allow_nan=False), "utf-8")
    report.write(results, REPORT)
    report.print_summary(results["model"])
    print(json.dumps({k: results["sanity"][k]["pass"] for k in results["sanity"]}
                     | {"image": (results["image_sanity"] or {}).get("pass")}, ensure_ascii=False))
    print(f"wrote {REPORT} and {RESULTS}")


if __name__ == "__main__":
    main()
