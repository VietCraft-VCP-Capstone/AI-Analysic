from scripts.li.fit import AXES, FULL, defined, fit, predict, without
from scripts.li.measure import paired

MIN_LIFT = 0.005
LEARNED = ("image", "text", "market", "trend")


def measured(entry):
    lift, ci = entry.get("lift"), entry.get("ci95")
    return lift is not None and ci is not None and lift >= MIN_LIFT and ci[0] > 0


def evidence_labels(ablation, beats):
    out = {a: "measured" if beats and measured(ablation.get(a, {})) else "practice" for a in LEARNED}
    return {"image": out["image"], "text": out["text"], "tags": "practice",
            "market": out["market"], "trend": out["trend"]}


def _entry(rows, full, drop):
    lift, ci = paired(rows, full, drop)
    return {"lift": lift, "ci95": ci, "n": int(len(rows)), "sources": sorted(rows["source"].astype(str).unique())}


def run(train, test, full_model):
    out = {}
    for axis in AXES:
        rows = defined(test, axis)
        if rows.empty:
            out[axis] = {"lift": None, "ci95": None, "n": 0}
            continue
        cols = without(axis)
        full = predict(full_model, rows, FULL)
        drop = predict(fit(train, cols), rows, cols)
        out[axis] = _entry(rows, full, drop)
    return out
