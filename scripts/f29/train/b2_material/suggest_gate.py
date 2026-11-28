import argparse
import json
import sys

import joblib
import numpy as np

from app.core.f29.checks.describe import B2_DIR
from scripts.f29.train.b2_material import b2_data as data


def choose_min_p(p1, correct, target=0.8, min_n=20) -> float:
    p1, correct = np.asarray(p1, dtype=float), np.asarray(correct, dtype=bool)
    for t in np.unique(p1):
        keep = p1 >= t
        if keep.sum() >= min_n and correct[keep].mean() >= target:
            return float(t)
    return 1.01


def _rule(model, d, idx) -> tuple[np.ndarray, np.ndarray]:
    probs = model.predict_proba(d["b"][idx])
    top1, p1 = model.classes_[probs.argmax(axis=1)], probs.max(axis=1)
    kept = top1 != "khac"
    return p1[kept], (top1 == d["y"][idx])[kept]


def _stats(p1, correct, t) -> dict:
    sel = p1 >= t
    return {"precision": round(float(correct[sel].mean()), 4) if sel.any() else None,
            "coverage": round(float(sel.mean()), 4), "n": len(p1)}


def main(argv) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    d = data.build()
    _, va, te = d["splits"]
    model = joblib.load(B2_DIR / "model.joblib")
    p1_va, correct_va = _rule(model, d, va)
    t = choose_min_p(p1_va, correct_va)
    val = _stats(p1_va, correct_va, t)
    test = _stats(*_rule(model, d, te), t)
    gate = {"min_p": round(t, 4), "target_precision": 0.8,
            "val_precision": val["precision"], "val_coverage": val["coverage"], "n_val": val["n"],
            "test_precision": test["precision"], "test_coverage": test["coverage"], "n_test": test["n"],
            "input": "val và test, mô tả đã bỏ từ chất liệu"}
    print(json.dumps(gate, ensure_ascii=False, indent=2))
    if not args.dry_run:
        path = B2_DIR / "metrics.json"
        metrics = json.loads(path.read_text("utf-8"))
        metrics["suggest_gate"] = gate
        path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), "utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
