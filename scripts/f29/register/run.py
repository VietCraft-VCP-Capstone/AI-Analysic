import json

import numpy as np

from scripts.f29.register.learn import ROOT
from scripts.f29.register import learn

OUT = ROOT / "notes/f29/register/metrics.json"
EQUAL = dict.fromkeys(learn.FACTORS, 1.0)


def _baselines(sim_w: dict) -> dict:
    single = {f"chỉ {k}": {k: 1.0} for k in learn.FACTORS}
    return {"đặt tay 30/30/15/10/15": learn.HAND, "đều nhau": EQUAL, "chỉ học trên mô phỏng": sim_w, **single}


def _sim_block(sim, idx, w: dict, base: dict) -> dict:
    X, y, g = sim.loc[idx, learn.FACTORS], sim.loc[idx, "y"].to_numpy(), sim.loc[idx, "group"].to_numpy()
    rand = np.random.default_rng(0).random(len(idx))
    out = {"chính thức": learn.r_report(y, learn.score(X, w), g), "ngẫu nhiên": learn.r_report(y, rand, g),
           "trần lý thuyết r(q)": learn.r_report(y, sim.loc[idx, "q"].to_numpy(), g)}
    out |= {k: learn.r_report(y, learn.score(X, b), g) for k, b in base.items() if learn.score(X, b).std() > 0}
    out["chính thức − đặt tay"] = learn.r_delta(y, learn.score(X, w), learn.score(X, learn.HAND), g)
    return out


def _tiki_block(tk, mask, w: dict, base: dict) -> dict:
    t = tk[mask]
    X, y, cat, g = t[learn.TIKI_FACTORS], t["y"].to_numpy(), t["category"].to_numpy(), t["group"].to_numpy()
    usable = {k: b for k, b in base.items() if any(f in b for f in learn.TIKI_FACTORS)}
    out = {"chính thức": learn.auc_report(y, learn.score(X, w), cat, g)}
    out |= {k: learn.auc_report(y, learn.score(X, b), cat, g) for k, b in usable.items()}
    out["chính thức − đặt tay"] = learn.auc_delta(y, learn.score(X, w), learn.score(X, learn.HAND), g)
    return out


def main() -> dict:
    sim, tk = learn.synthetic(), learn.tiki()
    tr, va, te = learn.split_synthetic(sim)
    sim_w = learn.fit(sim.loc[tr, learn.FACTORS], sim.loc[tr, "y"])
    tiki_tr = tk["split"] == "train"
    tiki_w = learn.fit(tk.loc[tiki_tr, learn.TIKI_FACTORS], tk.loc[tiki_tr, "y"])
    w = learn.compose(sim_w, tiki_w)
    base = _baselines(sim_w)
    report = {
        "weights": {"chính thức": learn.percents(w), "mô phỏng": sim_w, "tiki": tiki_w},
        "sizes": {"mô phỏng": [len(tr), len(va), len(te)], "tiki": tk["split"].value_counts().to_dict()},
        "val": {"mô phỏng": _sim_block(sim, va, w, base), "tiki": _tiki_block(tk, tk["split"] == "val", w, base)},
        "test": {"mô phỏng": _sim_block(sim, te, w, base), "tiki": _tiki_block(tk, tk["split"] == "test", w, base)},
    }
    r3 = report["test"]["mô phỏng"]["chính thức"]["r"]
    lo = report["test"]["tiki"]["chính thức − đặt tay"]["ci95"][0]
    report["gates"] = {"R3 r ≥ 0,65": r3 >= 0.65, "AI hơn đặt tay trên Tiki (cận dưới > 0)": lo > 0}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", "utf-8")
    learn.write_weights(w, {"r_test_synthetic": r3, "tiki_auc_test": report["test"]["tiki"]["chính thức"]["roc_auc"],
                            "gates": report["gates"]})
    return report


if __name__ == "__main__":
    r = main()
    print(json.dumps({"weights": r["weights"]["chính thức"], "gates": r["gates"],
                      "r_test": r["test"]["mô phỏng"]["chính thức"],
                      "tiki_test": r["test"]["tiki"]["chính thức − đặt tay"]}, ensure_ascii=False, indent=1))
