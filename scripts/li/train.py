import json
import math
from datetime import date
from pathlib import Path

import joblib
import pandas as pd
import sklearn

from app.core.calendar_vn import ALL_GROUPS
from app.core.listing_intel import embedder
from app.core.listing_intel.formulas import SPEC
from scripts.li import paths, reference
from scripts.li.assess import assess
from scripts.li.availability import IMPUTE_RULE, feature_availability, feature_constants, image_impute
from scripts.li.fit import AXIS_MODELS, AXIS_PARAMS, FULL, axis_cols, defined, fit

ROOT = Path(__file__).resolve().parents[2]
MODEL_DIR = ROOT / "app/core/listing_intel/model"
FEATURES = paths.DATA_DIR / "features"
FILES = {"fusion": "fusion.joblib", **{a: f"axis_{a}.joblib" for a in AXIS_MODELS}}


def finite(obj):
    if isinstance(obj, dict):
        return {str(k): finite(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [finite(v) for v in obj]
    if isinstance(obj, float) and not math.isfinite(obj):
        return None
    return obj


def fit_models(train):
    models = {"fusion": fit(train, FULL)}
    models |= {a: fit(defined(train, a), axis_cols(a), **AXIS_PARAMS.get(a, {})) for a in AXIS_MODELS}
    return models


def _train_data(train):
    by = train.groupby("source")["top25"].agg(["size", "mean"]).round(3)
    return {"rows": int(len(train)), "by_source": {s: {"rows": int(r["size"]), "top25_rate": float(r["mean"])}
                                                    for s, r in by.iterrows()},
            "split": "GroupShuffleSplit theo seller 70/15/15, random_state=42; model học trên split=train",
            "date": date.today().isoformat()}


def _vn(n):
    return f"{n:,}".replace(",", ".")


def _trained_on(data):
    years = " và ".join(f"{_vn(v['rows'])} năm 20{s[-2:]}" for s, v in data["by_source"].items())
    return (f"{_vn(data['rows'])} sản phẩm Tiki ({years}); chia theo người bán: 70% để học, 15% để kiểm định, "
            f"15% để kiểm tra; huấn luyện ngày {date.fromisoformat(data['date']).strftime('%d/%m/%Y')}")


def fit_bundle(table: pd.DataFrame, out_dir: Path, context_dir=None, extra=None) -> dict:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    train = table[table["split"] == "train"]
    models = fit_models(train)
    for name, file in FILES.items():
        joblib.dump(models[name], out_dir / file)
    design = reference.write(table, models, out_dir / "reference", context_dir)
    th = json.loads((out_dir / "reference/thresholds.json").read_text("utf-8"))
    data = _train_data(train)
    meta = {
        "model_version": "li-1.6",
        "sklearn": sklearn.__version__,
        "onnx_model": {"repo": embedder.MODEL_ID, "files": list(embedder.FILES)},
        "features": FULL,
        "axis_features": {a: axis_cols(a) for a in AXIS_MODELS},
        "groups": sorted(str(g) for g in train["group"].dropna().unique()),
        "group_categories": ALL_GROUPS,
        "thresholds": {"dup_cos": 0.92, "trend_match_cos": th["trend_match_cos"]},
        "trend_keywords": th.get("trend_keywords"),
        "trend_backtest": {"n": 0, "share_mase_lt_1": None},
        "formulas": SPEC,
        "axis_params": AXIS_PARAMS,
        "trained_on": _trained_on(data),
        "train_data": data,
        "feature_availability": feature_availability(train),
        "image_impute": image_impute(train, models["fusion"]),
        "image_impute_rule": IMPUTE_RULE,
        "feature_constants": feature_constants(train),
        "n_iter": {name: int(m.n_iter_) for name, m in models.items()},
        **assess(table, models, design),
        **(extra or {}),
    }
    meta = finite(json.loads(json.dumps(meta, ensure_ascii=False, default=float)))
    (out_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1, allow_nan=False), encoding="utf-8")
    return meta


def load_table():
    table = pd.read_parquet(FEATURES / "table.parquet")
    extra = []
    for src in ("tiki23", "tiki26"):
        df = pd.read_parquet(paths.clean(f"{src}.parquet"))
        age = df["age_days"].clip(lower=30) if "age_days" in df else 1
        extra.append(df.assign(source=src, rank_target=df["sold"] / age).reindex(
            columns=["source", "listing_id", "title", "price", "image_url", "rank_target"]))
    return table.merge(pd.concat(extra), on=["source", "listing_id"], how="left", validate="one_to_one")


def main():
    from scripts.li import trend_eval
    from scripts.li.report import print_summary

    table = load_table()
    ctx = FEATURES / "context" if (FEATURES / "context").exists() else FEATURES
    meta = fit_bundle(table, MODEL_DIR, ctx, {"trend_backtest": trend_eval.backtest_summary()})
    print_summary(meta)


if __name__ == "__main__":
    main()
