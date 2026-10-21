import argparse
import json
from pathlib import Path

import joblib
import pandas as pd
import sklearn
from sklearn.inspection import permutation_importance
from sklearn.metrics import roc_auc_score

from app.core.f29.ml import features
from scripts.f29_ml import data, evaluate, models, report
from scripts.f29_ml.baselines import BASELINES

ROOT = Path(__file__).resolve().parents[2]
MODEL_DIR = ROOT / "app" / "core" / "f29" / "ml"
TRAIN = ["2017-07-01", "2017-08-01", "2017-09-01", "2017-10-01"]
VAL, TEST = "2018-01-01", "2018-05-01"
HISTORY = features.GROUPS["history"]
NO_HISTORY = [f for f in features.NUMERIC if f not in HISTORY]
PORTABLE = {
    "Gradient boosting, bản chạy trên VietCraft": features.PORTABLE,
    "Gradient boosting, chỉ lịch sử bán": HISTORY,
}
CANDIDATES = {
    "Logistic regression": (models.logistic, features.NUMERIC + ["category"]),
    "Gradient boosting": (models.boosting, features.NUMERIC + ["category"]),
    "Gradient boosting, bỏ lịch sử bán": (models.boosting, NO_HISTORY + ["category"]),
    **{name: (models.boosting, cols) for name, cols in PORTABLE.items()},
}


def _split(tables, cutoffs, dtype):
    df = pd.concat([features.snapshot(*tables, t) for t in cutoffs], ignore_index=True)
    df["category"] = df["category"].astype(dtype)
    return df


def _evaluate(fit_on, ev):
    scores, fitted, preds = {}, {}, {}
    for name, fn in BASELINES.items():
        preds[name] = fn(ev)
    for name, (factory, cols) in CANDIDATES.items():
        fitted[name] = factory().fit(fit_on[cols], fit_on["label"])
        preds[name] = fitted[name].predict_proba(ev[cols])[:, 1]
    for name, p in preds.items():
        scores[name] = evaluate.score_all(ev["label"], p, ev["category"], ev["seller_id"])
    return scores, fitted, preds


def _group_lift(fit_on, test, cols, auc):
    lift = {}
    for group, members in features.GROUPS.items():
        rest = [c for c in cols if c not in members]
        if rest and len(rest) < len(cols):
            model = models.boosting().fit(fit_on[rest], fit_on["label"])
            lift[group] = round(auc - roc_auc_score(test["label"], model.predict_proba(test[rest])[:, 1]), 4)
    return lift


def _summary(name, cutoffs, df):
    return {"name": name, "cutoffs": cutoffs, "rows": len(df), "positive_rate": round(float(df["label"].mean()), 3)}


def _deploy(name, model, fit_on, results):
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, MODEL_DIR / "listing_model.joblib")
    meta = {
        "model_version": "health-ml-1.1",
        "name": name,
        "features": PORTABLE[name],
        "groups": features.GROUPS,
        "actionable": features.ACTIONABLE,
        "horizon_days": features.HORIZON,
        "trained_on": "Olist (Brazil), mốc " + ", ".join(TRAIN + [VAL]),
        "sklearn": sklearn.__version__,
        "test": results["test"][name],
        "test_baselines": {k: results["test"][k] for k in BASELINES},
        "delta_vs_best_baseline": results["delta"],
        "group_lift": results["group_lift"],
        "importance": results["importance"],
        "quantiles": {c: fit_on[c].quantile([0.25, 0.5, 0.75]).round(4).tolist() for c in features.ACTIONABLE},
    }
    (MODEL_DIR / "listing_model.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default=str(data.DEFAULT_DIR))
    sales, products, rated, cleaning = data.load(parser.parse_args().data)
    dtype = pd.CategoricalDtype(sorted(products["category"].unique()))
    tables = (sales, products, rated)
    train, val, test = (_split(tables, c, dtype) for c in (TRAIN, [VAL], [TEST]))
    val_scores, _, _ = _evaluate(train, val)
    deploy = max(PORTABLE, key=lambda n: val_scores[n]["roc_auc"])
    fit_on = pd.concat([train, val], ignore_index=True)
    test_scores, fitted, preds = _evaluate(fit_on, test)
    best = max((b for b in BASELINES), key=lambda b: test_scores[b]["roc_auc"])
    cols = PORTABLE[deploy]
    perm = permutation_importance(fitted[deploy], test[cols], test["label"], scoring="roc_auc", n_repeats=5, random_state=42)
    results = {
        "cleaning": cleaning,
        "splits": [_summary("train", TRAIN, train), _summary("validation", [VAL], val), _summary("test", [TEST], test)],
        "validation": val_scores,
        "test": test_scores,
        "deployed": deploy,
        "best_baseline": best,
        "delta": {"vs": best, "auc": round(test_scores[deploy]["roc_auc"] - test_scores[best]["roc_auc"], 3),
                  "ci95": evaluate.delta_ci(test["label"], preds[deploy], preds[best], test["seller_id"])},
        "group_lift": _group_lift(fit_on, test, cols, roc_auc_score(test["label"], preds[deploy])),
        "importance": dict(sorted(zip(cols, perm.importances_mean.round(4).tolist()), key=lambda kv: -kv[1])),
    }
    _deploy(deploy, fitted[deploy], fit_on, results)
    (ROOT / "docs" / "f29_ml_results.json").write_text(json.dumps(results, ensure_ascii=False, indent=1))
    (ROOT / "docs" / "F29_ML_RESULTS.md").write_text(report.render(results))
    print(report.render(results))


if __name__ == "__main__":
    main()
