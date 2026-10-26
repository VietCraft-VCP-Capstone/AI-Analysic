import joblib
import numpy as np

from scripts.f29_ml.evaluate import within_category_auc
from scripts.li.assess import eval_sets
from scripts.li.fit import FULL, fit, predict
from scripts.li.measure import auc

BANNED = ["review_count", "rating_average", "favourite_count", "order_count", "revenue_estimate",
          "quantity_sold", "inventory_status", "badges", "is_official_store", "discount", "discount_rate",
          "has_video", "fulfillment_type", "brand"]
LABEL_COLS = ["age_days", "sold", "top25", "rank_target", "split", "seller", "seller_id", "listing_id", "source"]
SHUFFLE_RANGE = (0.45, 0.55)
SHUFFLE_SEEDS = range(5)


def _inside(v):
    return SHUFFLE_RANGE[0] <= v <= SHUFFLE_RANGE[1]


def shuffled(train, sets, seeds=SHUFFLE_SEEDS):
    runs, within = {k: [] for k in ("test", "test_all")}, {k: [] for k in ("test", "test_all")}
    for seed in seeds:
        model = fit(train, FULL, np.random.default_rng(seed).permutation(train["top25"].to_numpy()))
        for k in runs:
            df, s = sets[k], predict(model, sets[k], FULL)
            runs[k].append(round(auc(df, s), 4))
            within[k].append(round(within_category_auc(df["top25"].to_numpy(), s, df["group"].to_numpy(str)), 4))
    mean = {k: round(float(np.mean(v)), 4) for k, v in runs.items()}
    return {"auc_mean": mean, "auc_runs": runs, "within_group_auc_mean": {k: round(float(np.mean(v)), 4)
                                                                         for k, v in within.items()},
            "seeds": list(seeds), "range": list(SHUFFLE_RANGE),
            "all_runs_inside": all(_inside(v) for r in runs.values() for v in r),
            "pass": all(_inside(v) for v in mean.values())}


def _sellers(df):
    return set(df["seller"].dropna().astype(str))


def seller_overlap(table):
    within, cross = {}, {}
    for src, df in table.groupby("source"):
        by = {s: _sellers(df[df["split"] == s]) for s in ("train", "val", "test")}
        within[src] = {f"{a}-{b}": len(by[a] & by[b]) for a, b in (("train", "val"), ("train", "test"), ("val", "test"))}
    for src, df in table.groupby("source"):
        other = table[table["source"] != src]
        shared = _sellers(df[df["split"] == "train"]) & _sellers(other[other["split"] != "train"])
        cross[f"train {src} ∩ val/test khác nguồn"] = sorted(shared)
    n_rows = int(table[(table["split"] != "train") & table["seller"].astype(str).isin(
        set().union(*cross.values()))].shape[0])
    return {"within_source": within, "cross_source": cross, "cross_rows_eval": n_rows,
            "pass": all(v == 0 for d in within.values() for v in d.values())}


def banned_features(features, model=None):
    used = list(features) + list(getattr(model, "feature_names_in_", []))
    bad = sorted({f for f in used if f in LABEL_COLS or any(b in f for b in BANNED)})
    same = model is None or list(model.feature_names_in_) == list(features)
    return {"checked": len(set(used)), "found": bad, "model_matches_meta": bool(same), "pass": not bad and same}


def deterministic(train, test, bundle_dir):
    a = predict(fit(train, FULL), test, FULL)
    b = predict(fit(train, FULL), test, FULL)
    saved = predict(joblib.load(bundle_dir / "fusion.joblib"), test, FULL)
    return {"refit_identical": bool(np.array_equal(a, b)), "bundle_identical": bool(np.array_equal(a, saved)),
            "pass": bool(np.array_equal(a, b) and np.array_equal(a, saved))}


def run(table, meta, bundle_dir):
    train = table[table["split"] == "train"]
    sets = eval_sets(table[table["split"].isin(["val", "test"])])
    return {
        "shuffled_labels": shuffled(train, sets),
        "seller_overlap": seller_overlap(table),
        "banned_features": banned_features(meta["features"], joblib.load(bundle_dir / "fusion.joblib")),
        "deterministic": deterministic(train, sets["test_all"], bundle_dir),
    }
