import sys
import json
from collections import Counter

import joblib
import numpy as np

from app.core.f29.checks.attributes import method_probs
from scripts.f29.train.b3_attr.helpers import METHODS, conflict_matrix, gaps, max_gap
from app.core.f29.checks.describe import ATTR_DIR as MODEL_DIR
from scripts.f29.train.b3_attr.attr_card import card
from scripts.f29.train.b3_attr.attr_cls import cls_metrics
from scripts.f29.train.b3_attr.attr_fit import fit_all
from scripts.f29.train.b3_attr.attr_groups import group_ids
from scripts.f29.train.b3_attr.attr_labels import claim_index, predict_types, row_claims
from scripts.f29.train.b3_attr.attr_load import load_all
from scripts.f29.train.b3_attr.attr_pairs import make_set
from scripts.f29.train.b3_attr.attr_pr import baseline_scores, candidate_ap, eval_prev
from scripts.f29.train.b3_attr.attr_zs import class_matrix
from scripts.f29.eval_kit import conformal_threshold, group_split

ALPHA = 0.02
PREVS = (0.03, 0.05)
SEEDS = {"split": 0, "pairs": 1}
FIXED = "blend"


def _cands(P: dict, idx: dict, M: dict, img_rows, txt_rows) -> dict:
    return {m: max_gap(P[m], idx, M, img_rows, txt_rows) for m in METHODS}


def _val_table(claims, types, va, P, idx, M) -> tuple[dict, dict]:
    table, pairs = {m: {} for m in METHODS}, {}
    for p in PREVS:
        S = make_set(va, claims, types, p, SEEDS["pairs"])
        aps = candidate_ap(S, _cands(P, idx, M, S["img"], S["txt"]))
        for m in METHODS:
            table[m][str(p)] = aps[m]
        pairs[str(p)] = {"n_pos": int(S["y"].sum()), "n_neg": int((S["y"] == 0).sum())}
    for m in METHODS:
        table[m]["mean"] = round(float(np.mean([table[m][str(p)] for p in PREVS])), 4)
    return table, pairs


def _per_attr(g, claims, types, te, d, gid, P, idx, M) -> dict:
    out = {}
    for p in PREVS:
        S = make_set(te, claims, types, p, SEEDS["pairs"], group=g)
        ours = gaps(P[FIXED][g][S["img"]], idx[g][S["txt"]], M[g])
        r = eval_prev(S, {FIXED: ours, **baseline_scores(d["img"], d["txt"], types, S)}, FIXED, gid, None)
        out[str(p)] = {k: v for k, v in r.items() if k != "live"}
    return out


def main() -> None:
    d = load_all()
    gid = group_ids(d["seller"], d["img"], d["txt"])
    tr, va, te = group_split(gid, seed=SEEDS["split"])
    if "--dry-run" in sys.argv:
        print(f"train/val/test: {len(tr)}/{len(va)}/{len(te)}")
        return
    types = predict_types(d["img"], d["txt"])
    claims = row_claims(d["text"], types)
    bundle, fit = fit_all(d["img"], claims, tr, va)
    classes = {g: e["classes"] for g, e in bundle.items()}
    idx = claim_index(claims, classes)
    M = {g: conflict_matrix(g, classes[g]) for g in bundle}
    V = {g: class_matrix(g, classes[g]) for g in bundle}
    P = {m: {g: method_probs(m, bundle[g], V[g], d["img"]) for g in bundle} for m in METHODS}
    val_table, val_pairs = _val_table(claims, types, va, P, idx, M)
    cal = max_gap(P[FIXED], idx, M, va, va)
    t_warn = conformal_threshold(cal[np.isfinite(cal)], ALPHA)
    prev, pairs_test = {}, {}
    for p in PREVS:
        S = make_set(te, claims, types, p, SEEDS["pairs"])
        scores = {**_cands(P, idx, M, S["img"], S["txt"]), **baseline_scores(d["img"], d["txt"], types, S)}
        prev[str(p)] = eval_prev(S, scores, FIXED, gid, t_warn)
        pairs_test[str(p)] = {"n_pos": int(S["y"].sum()), "n_neg": int((S["y"] == 0).sum()), "n_pool": S["n_pool"]}
    per_attr = {g: {**cls_metrics(bundle[g], V[g], d["img"], claims, te, g, "probe"),
                    "prevalence": _per_attr(g, claims, types, te, d, gid, P, idx, M)} for g in bundle}
    mode = "live" if all(r["live"] for r in prev.values()) else "hint"
    metrics = {"rows": {"total": len(tr) + len(va) + len(te), "train": len(tr), "val": len(va), "test": len(te),
                        "sources": dict(Counter(d["src"].tolist()))},
               "groups_total": int(gid.max()) + 1, "seeds": SEEDS, "alpha": ALPHA, "t_warn": t_warn,
               "n_cal": int(np.isfinite(cal).sum()), "fit": fit,
               "selection": {"rule": "phương pháp cố định 'blend' (chọn trên val ở fix round 1, không chọn lại)",
                             "chosen": FIXED, "val_pr_auc_current_pairs": val_table, "val_pairs": val_pairs},
               "pairs_test": pairs_test, "prevalence": prev,
               "prevalence_false_alarm": {p: r["false_alarm_clean"] for p, r in prev.items()},
               "per_attribute": per_attr, "mode": mode,
               "mode_rule": "live khi phương pháp đã chọn > baseline tốt nhất (1−cos, B3 v1) ở cả 3% và 5%, "
                            "CI95 bootstrap theo group_id của chênh lệch > 0"}
    thresholds = {"alpha_warn": ALPHA, "t_warn": t_warn, "mode": mode, "method": FIXED,
                  "n_cal": int(np.isfinite(cal).sum())}
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, MODEL_DIR / "model.joblib")
    np.save(MODEL_DIR / "prompts.npy", V, allow_pickle=True)
    (MODEL_DIR / "thresholds.json").write_text(json.dumps(thresholds, indent=2), "utf-8")
    (MODEL_DIR / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), "utf-8")
    (MODEL_DIR / "card.md").write_text(card(metrics), "utf-8")
    print(json.dumps({"mode": mode, "t_warn": t_warn, "pairs_test": pairs_test, "prevalence": prev},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
