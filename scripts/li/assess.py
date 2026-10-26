import pandas as pd

from scripts.li import ablation
from scripts.li.baselines import available
from scripts.li.fit import AXIS_MODELS, FULL, axis_cols, defined, predict
from scripts.li.measure import measure, paired
from scripts.li.reference import formula_values


def eval_sets(ev):
    prim = ev[ev["source"] == "tiki26"] if (ev["source"] == "tiki26").any() else ev
    return {
        "test": prim[prim["split"] == "test"],
        "val": prim[prim["split"] == "val"],
        "test_tiki23": ev[(ev["split"] == "test") & (ev["source"] == "tiki23")],
        "test_all": ev[ev["split"] == "test"],
        "val_all": ev[ev["split"] == "val"],
    }


def predictions(table, models):
    train = table[table["split"] == "train"]
    ev = table[table["split"].isin(["val", "test"])]
    preds = {"Model gộp (fusion)": pd.Series(predict(models["fusion"], ev, FULL), ev.index)}
    for a in AXIS_MODELS:
        rows = defined(ev, a)
        preds[f"Chỉ trục {a}"] = pd.Series(predict(models[a], rows, axis_cols(a)), rows.index)
    base = {name: pd.Series(fn(train, ev), ev.index) for name, fn in available(table).items()}
    return train, ev, preds, base


def formula_preds(ev, axes):
    out = {}
    for a in axes:
        rows = defined(ev, a)
        out[f"Công thức trục {a}"] = pd.Series(formula_values(rows, a), rows.index).dropna()
    return out


def _tables(sets, scores):
    out = {}
    for key, df in sets.items():
        out[key] = {}
        for name, s in scores.items():
            rows = df[df.index.isin(s.index)]
            out[key][name] = measure(rows, s.loc[rows.index].to_numpy()) if len(rows) else None
    return out


def _strongest(table):
    return max((n for n, m in table.items() if m), key=lambda n: table[n]["roc_auc"])


def _versus(sets, tables, base, fusion, name, key="test"):
    df = sets[key]
    delta, ci = paired(df, fusion.loc[df.index].to_numpy(), base[name].loc[df.index].to_numpy())
    return {"name": name, "auc": tables[key][name]["roc_auc"], "delta": delta, "ci95": ci,
            "significant": ci is not None and ci[0] > 0}


def _best(sets, tables, base, fusion):
    name = _strongest({n: tables["test"][n] for n in base})
    out = _versus(sets, tables, base, fusion, name)
    val_name = _strongest({n: tables["val"][n] for n in base})
    out |= {"best_on_val": val_name, "val_choice": _versus(sets, tables, base, fusion, val_name),
            "gate": "spec §1.2: baseline mạnh nhất trên chính test tiki26",
            "secondary": {k: {f: v for f, v in _versus(sets, tables, base, fusion, name, k).items()
                              if f in ("delta", "ci95")} for k in ("test_tiki23", "test_all") if len(sets[k])}}
    return out


MODE_RULE = ("trục dùng model khi cận dưới CI95 (bootstrap theo seller) của ROC-AUC trên mọi tập validation có trục "
             "đó (validation tiki26, validation gộp) lớn hơn 0,5; nếu không, trục dùng công thức minh bạch. Riêng trục "
             "ảnh dùng công thức khi kết quả độ bền đã lưu (`reference/image_design.json`) cho thấy p90 lệch của model "
             "ổn định nhất lớn hơn p90 lệch của công thức trên cùng tập ảnh validation biến đổi")


def _num(v):
    return f"{v:.1f}".replace(".", ",")


def image_override(design):
    if not design:
        return None
    model, form = design["model"], design["formula"]
    worst = max(form["p90_shift"].values())
    if model["p90_shift"] <= worst:
        return None
    return (f"độ bền trên validation ({design['n_val']} ảnh, {design['configs']} cấu hình): model ảnh ổn định nhất "
            f"(max_iter={model['params']['max_iter']}, max_depth={model['params']['max_depth']}) lệch trung vị "
            f"{_num(model['max_shift'])} nhưng p90 lệch {_num(model['p90_shift'])} điểm phân vị, so với p90 lớn nhất "
            f"{_num(worst)} của công thức `{form['name']}`")


def _summary(tables, name, keys):
    return {k: {"auc": m["roc_auc"], "ci95": m["auc_ci95"], "n": m["n"]}
            for k in keys if (m := tables[k].get(name))}


def axis_modes(tables, design=None):
    out = {}
    for a in AXIS_MODELS:
        val = _summary(tables, f"Chỉ trục {a}", ("val", "val_all"))
        ok = bool(val) and all(v["ci95"][0] > 0.5 for v in val.values())
        forced = image_override(design) if a == "image" else None
        reason = forced or ("AUC validation hơn ngẫu nhiên" if ok else "AUC validation không hơn ngẫu nhiên")
        out[a] = {"mode": "model" if ok and not forced else "formula", "reason": reason, "val": val}
    return out


def assess(table, models, design=None):
    train, ev, preds, base = predictions(table, models)
    sets = eval_sets(ev)
    fusion = preds["Model gộp (fusion)"]
    tables = _tables(sets, preds | base)
    modes = axis_modes(tables, design)
    form = _tables(sets, formula_preds(ev, [a for a, e in modes.items() if e["mode"] == "formula"]))
    tables = {k: {n: v for n, v in tables[k].items() if n not in base} | form[k] | {n: tables[k][n] for n in base}
              for k in tables}
    for a, e in modes.items():
        if e["mode"] == "formula":
            e["formula"] = _summary(tables, f"Công thức trục {a}", ("val", "val_all", "test"))
    best = _best(sets, tables, base, fusion)
    beats = best["significant"]
    abl = ablation.run(train, sets["test"], models["fusion"])
    return {
        "metrics": {"test": tables["test"]["Model gộp (fusion)"], "val": tables["val"]["Model gộp (fusion)"]},
        "baselines": {n: tables["test"][n] for n in base},
        "best_baseline": best,
        "beats_best_baseline": bool(beats),
        "ablation": abl,
        "evidence": ablation.evidence_labels(abl, beats),
        "axis_modes": modes,
        "axis_mode_rule": MODE_RULE,
        "tables": tables,
    }
