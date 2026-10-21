from app.core.listing_intel import features as F
from scripts.li.fit import fit, predict
from scripts.li.measure import measure, paired

TEXT_META = F.TEXT_COLS + F.META_COLS + ["group"]
PURE = [c for c in TEXT_META if not c.startswith("kw_lift")]


def run(table):
    t23 = table[table["source"] == "tiki23"]
    t26 = table[table["source"] == "tiki26"]
    test = t26[t26["split"] == "test"]
    if t23.empty or test.empty:
        return None
    variants = {
        "shift": ("Học trên toàn bộ tiki23 (2023) → tiki26 test (2026)", t23, TEXT_META),
        "shift_pure": ("Như trên, bỏ kw_lift_* (bảng lift học từ nhãn train của cả 2 nguồn)", t23, PURE),
        "in_domain": ("Học trên tiki26 train → tiki26 test, cùng feature", t26[t26["split"] == "train"], TEXT_META),
        "pooled": ("Học trên train của cả 2 nguồn → tiki26 test, cùng feature",
                   table[table["split"] == "train"], TEXT_META),
    }
    preds, out = {}, {}
    for key, (label, fit_on, wanted) in variants.items():
        cols = [c for c in wanted if c == "group" or fit_on[c].notna().any()]
        preds[key] = predict(fit(fit_on, cols), test, cols)
        out[key] = {"label": label, "rows_fit": int(len(fit_on)), "n_features": len(cols),
                    "dropped": [c for c in wanted if c not in cols],
                    **(measure(test, preds[key]) or {})}
    for key in ("shift", "shift_pure"):
        delta, ci = paired(test, preds[key], preds["in_domain"])
        out[key]["delta_vs_in_domain"], out[key]["delta_ci95"] = delta, ci
    out["groups_fit"] = sorted(t23["group"].astype(str).unique())
    out["groups_test"] = sorted(test["group"].astype(str).unique())
    return out
