import json

import numpy as np
from sklearn.metrics import brier_score_loss

from scripts.li import candidates
from scripts.li.assess import eval_sets
from scripts.li.fit import FULL, fit, predict
from scripts.li.measure import auc, paired, sellers
from scripts.li.train import FEATURES, load_table

OUT = FEATURES / "selection.json"
CANDIDATES = candidates.CANDIDATES
BASE = FULL
SETS = ("val", "val_all")
MAX_BRIER_UP = 0.001
MAX_ECE_UP = 0.01
RULE = (f"giữ ứng viên khi ROC-AUC tăng trên cả validation tiki26 lẫn validation gộp, Brier tăng không quá {MAX_BRIER_UP} "
        f"và ECE tăng không quá {MAX_ECE_UP} trên cả hai tập")


def ece(y, p, bins=10):
    edges = np.quantile(p, np.linspace(0, 1, bins + 1))
    idx = np.clip(np.searchsorted(edges, p, side="right") - 1, 0, bins - 1)
    return float(sum(abs(y[idx == b].mean() - p[idx == b].mean()) * (idx == b).mean()
                     for b in range(bins) if (idx == b).any()))


def _scores(df, p):
    y = df["top25"].to_numpy()
    return {"roc_auc": round(auc(df, p), 4), "brier": round(float(brier_score_loss(y, p)), 4),
            "ece": round(ece(y, p), 4), "n": int(len(df)), "n_sellers": len(set(sellers(df)))}


def variants():
    out = {"base": BASE}
    out |= {f"+{k}": BASE + cols for k, cols in CANDIDATES.items()}
    out["+" + "+".join(CANDIDATES)] = BASE + [c for cols in CANDIDATES.values() for c in cols]
    return out


def keep(rows, name):
    return all(rows[name][s]["roc_auc"] > rows["base"][s]["roc_auc"]
               and rows[name][s]["brier"] <= rows["base"][s]["brier"] + MAX_BRIER_UP
               and rows[name][s]["ece"] <= rows["base"][s]["ece"] + MAX_ECE_UP for s in SETS)


def run(table):
    train = table[table["split"] == "train"]
    sets = eval_sets(table[table["split"] == "val"])
    preds, rows = {}, {}
    for name, cols in variants().items():
        model = fit(train, cols)
        preds[name] = {s: predict(model, sets[s], cols) for s in SETS}
        rows[name] = {s: _scores(sets[s], preds[name][s]) for s in SETS}
    for name in rows:
        for s in SETS:
            delta, ci = paired(sets[s], preds[name][s], preds["base"][s])
            rows[name][s] |= {"delta_vs_base": delta, "delta_ci95": ci}
    kept = [k for k in CANDIDATES if keep(rows, f"+{k}")]
    return {"rule": RULE, "sets": list(SETS), "variants": rows, "kept": kept,
            "features": BASE + [c for k in kept for c in CANDIDATES[k]]}


def main():
    out = run(candidates.add(load_table()))
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), "utf-8")
    for name, r in out["variants"].items():
        print(name, {s: {k: r[s][k] for k in ("roc_auc", "brier", "ece", "delta_vs_base", "delta_ci95")} for s in SETS})
    print("kept:", out["kept"])


if __name__ == "__main__":
    main()
