import json
import time

import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from app.core.calendar_vn import ALL_GROUPS
from scripts.li.assess import eval_sets
from scripts.li.fit import FULL, frame, hgb
from scripts.li.measure import measure, paired
from scripts.li.paths import DATA_DIR

SEED = 42
SETS = ("val", "val_all")
REFERENCE = "HistGradientBoosting"


def dev_rows(table):
    table = table[table["split"] != "test"]
    assert not (table["split"] == "test").any()
    return table


def load():
    path = DATA_DIR / "features" / "table.parquet"
    return dev_rows(pd.read_parquet(path, filters=[("split", "!=", "test")]))


def prep(scale):
    num = [c for c in FULL if c != "group"]
    steps = [SimpleImputer(strategy="median")] + ([StandardScaler()] if scale else [])
    return ColumnTransformer([
        ("num", make_pipeline(*steps), num),
        ("group", OneHotEncoder(categories=[ALL_GROUPS], handle_unknown="ignore"), ["group"]),
    ])


def candidates():
    return {
        REFERENCE: hgb,
        "RandomForest": lambda: make_pipeline(prep(False), RandomForestClassifier(
            n_estimators=300, min_samples_leaf=20, random_state=SEED, n_jobs=-1)),
        "LogisticRegression": lambda: make_pipeline(prep(True), LogisticRegression(max_iter=2000, random_state=SEED)),
        "GradientBoosting": lambda: make_pipeline(prep(False), GradientBoostingClassifier(random_state=SEED)),
    }


def score(sets, proba, ref):
    out = {}
    for key, df in sets.items():
        m = measure(df, proba.loc[df.index].to_numpy())
        entry = {"auc": m["roc_auc"], "ci95": m["auc_ci95"], "n": m["n"]}
        if ref is not None:
            entry["delta"], entry["delta_ci95"] = paired(df, ref.loc[df.index].to_numpy(), proba.loc[df.index].to_numpy())
        out[key] = entry
    return out


def run(table):
    train, val = table[table["split"] == "train"], table[table["split"] == "val"]
    sets = {k: v for k, v in eval_sets(val).items() if k in SETS}
    assert all((v["split"] == "val").all() for v in sets.values())
    X_train, X_val, results, ref = frame(train, FULL), frame(val, FULL), {}, None
    for name, make in candidates().items():
        start = time.perf_counter()
        model = make().fit(X_train, train["top25"])
        seconds = round(time.perf_counter() - start, 1)
        proba = pd.Series(model.predict_proba(X_val)[:, 1], val.index)
        ref = proba if ref is None else ref
        results[name] = {"seconds": seconds, "sets": score(sets, proba, None if name == REFERENCE else ref)}
    return results


def show(results):
    for key in SETS:
        print(f"\n{key}")
        for name, r in results.items():
            s = r["sets"][key]
            delta = "-" if "delta" not in s else f"{s['delta']:+.4f} {s['delta_ci95']}"
            print(f"| {name} | {s['auc']:.3f} {s['ci95']} | {delta} | {r['seconds']}s |")


if __name__ == "__main__":
    results = run(load())
    show(results)
    print(json.dumps(results))
