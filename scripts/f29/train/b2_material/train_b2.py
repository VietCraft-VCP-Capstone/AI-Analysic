import sys
import json
from collections import Counter

import joblib
import numpy as np
from sklearn.calibration import CalibratedClassifierCV
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score
from sklearn.pipeline import FeatureUnion, Pipeline

from app.core.f29.checks.describe import B2_DIR as MODEL_DIR
from app.core.f29.score.text_rules import strip_accents
from scripts.f29.train.b2_material import b2_data as data
from scripts.f29.train.b2_material import suggest_gate
from scripts.f29.train.b2_material.b2_card import card

C_GRID = (0.5, 2, 8)


def tfidf() -> FeatureUnion:
    return FeatureUnion([
        ("char", TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), min_df=2, max_features=200000)),
        ("word", TfidfVectorizer(ngram_range=(1, 2), min_df=2)),
    ])


def macro_f1(y, pred) -> float:
    return round(float(f1_score(y, pred, labels=np.unique(y), average="macro", zero_division=0)), 4)


def top3(model, X, y) -> float:
    top = model.classes_[np.argsort(-model.predict_proba(X), axis=1)[:, :3]]
    return round(float((top == y[:, None]).any(axis=1).mean()), 4)


def score_model(model, X, y) -> dict:
    return {"model": {"macro_f1": macro_f1(y, model.predict(X)), "top3": top3(model, X, y)}}


def score_base(name: str, fn, X, y) -> dict:
    return {name: {"macro_f1": macro_f1(y, [fn(t) for t in X])}}


def delta_ci(y, a, b, groups, n=1000, seed=0) -> list[float]:
    rng = np.random.default_rng(seed)
    _, inv = np.unique(groups, return_inverse=True)
    members = np.split(np.argsort(inv, kind="stable"), np.cumsum(np.bincount(inv))[:-1])
    diffs = []
    for _ in range(n):
        idx = np.concatenate([members[j] for j in rng.integers(0, len(members), len(members))])
        diffs.append(macro_f1(y[idx], a[idx]) - macro_f1(y[idx], b[idx]))
    return [round(float(v), 4) for v in np.percentile(diffs, [2.5, 97.5])]


def pick_c(a, y, tr, va) -> tuple[float, dict]:
    val = {}
    for c in C_GRID:
        model = Pipeline([("tfidf", tfidf()), ("clf", LogisticRegression(C=c, max_iter=2000))])
        val[str(c)] = macro_f1(y[va], model.fit(a[tr], y[tr]).predict(a[va]))
    return max(C_GRID, key=lambda c: val[str(c)]), val


def evaluate(model, d, te, majority) -> dict:
    out = {}
    for key in ("a", "b"):
        X, y = list(d[key][te]), d["y"][te]
        out[key.upper()] = (score_model(model, X, y) | score_base("baseline_current", data.baseline_current, X, y)
                            | score_base("baseline_text_vi", data.baseline_text_vi, X, y)
                            | score_base("baseline_majority", lambda _: majority, X, y))
    return out


def gate_a(model, d, te, majority, test) -> dict:
    X, y, groups = list(d["a"][te]), d["y"][te], d["sellers"][te]
    preds = {"baseline_current": np.array([data.baseline_current(t) for t in X]),
             "baseline_text_vi": np.array([data.baseline_text_vi(t) for t in X]),
             "baseline_majority": np.array([majority] * len(X))}
    best = max(preds, key=lambda k: test["A"][k]["macro_f1"])
    lo, hi = delta_ci(y, model.predict(X), preds[best], groups)
    return {"best_baseline": best, "delta_ci95": [lo, hi], "ci_pass": lo > 0}


def evaluate_unaccented(model, d, te) -> dict:
    return {key.upper(): score_model(model, [strip_accents(t) for t in d[key][te]], d["y"][te])
            for key in ("a", "b")}


def main() -> None:
    d = data.build()
    tr, va, te = d["splits"]
    if "--dry-run" in sys.argv:
        print(f"train/val/test: {len(tr)}/{len(va)}/{len(te)}")
        return
    a, y = d["a"], d["y"]
    C, val = pick_c(a, y, tr, va)
    majority = Counter(y[tr]).most_common(1)[0][0]
    model = Pipeline([("tfidf", tfidf()), ("clf", CalibratedClassifierCV(
        LogisticRegression(C=C, max_iter=2000), method="isotonic", cv=3, ensemble=False))])
    model.fit(a[tr], y[tr])
    test = evaluate(model, d, te, majority)
    metrics = {"rows": {"train": len(tr), "val": len(va), "test": len(te)}, "classes": [str(c) for c in model.classes_],
               "C": C, "majority": str(majority), "val_macro_f1_by_C": val, "test": test,
               "gate_A": gate_a(model, d, te, majority, test), "test_unaccented": evaluate_unaccented(model, d, te)}
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, MODEL_DIR / "model.joblib")
    (MODEL_DIR / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), "utf-8")
    (MODEL_DIR / "card.md").write_text(card(metrics), "utf-8")
    print(json.dumps({"C": C, "test": test, "gate_A": metrics["gate_A"], "unaccented": metrics["test_unaccented"]},
                     ensure_ascii=False, indent=2))
    suggest_gate.main([])


if __name__ == "__main__":
    main()
