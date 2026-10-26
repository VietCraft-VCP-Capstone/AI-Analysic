import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.core.listing_intel import features as F

BUNDLE = Path(__file__).resolve().parents[2] / "app/core/listing_intel/model"
KEYS = {
    "model_version", "sklearn", "onnx_model", "features", "axis_features", "groups", "metrics",
    "baselines", "best_baseline", "ablation", "evidence", "thresholds", "trend_backtest", "trained_on",
    "feature_availability", "image_impute", "feature_constants",
}
FILES = ["fusion.joblib", "axis_image.joblib", "axis_text.joblib", "axis_market.joblib", "meta.json",
         "reference/score_dist.npz", "reference/axis_dist.npz", "reference/group_median_price.json",
         "reference/top_medians.json", "reference/thresholds.json", "reference/formula_dist.npz"]


def synthetic(n=200, seed=0):
    rng = np.random.default_rng(seed)
    df = pd.DataFrame(rng.normal(size=(n, len(F.FEATURE_COLS))), columns=F.FEATURE_COLS)
    signal = df["kw_lift_sum"] + df["img_sharpness"] + rng.normal(scale=0.5, size=n)
    seller = np.arange(n) % 40
    df["group"] = np.where(np.arange(n) % 2, "bags", "fashion")
    df["top25"] = (signal > np.quantile(signal, 0.75)).astype(int)
    df["seller"] = [f"s{i}" for i in seller]
    df["split"] = np.select([seller < 28, seller < 34], ["train", "val"], "test")
    df["source"], df["listing_id"], df["sold"] = "tiki26", np.arange(n), rng.integers(0, 100, n)
    return df


def check_meta(meta):
    assert KEYS <= set(meta)
    assert meta["model_version"] == "li-1.6"
    assert isinstance(meta["trained_on"], str) and "random_state" not in meta["trained_on"]
    for g, av in meta["feature_availability"].items():
        assert set(av) == set(F.FEATURE_COLS) and all(0 <= v <= 1 for v in av.values())
    for g, fill in meta["image_impute"].items():
        assert set(fill) == set(F.IMAGE_COLS) and meta["feature_availability"][g]["img_sharpness"] > 0
    for g, const in meta["feature_constants"].items():
        assert all(meta["feature_availability"][g][c] == 1.0 for c in const)
    assert set(meta["axis_features"]) == {"image", "text", "market"}
    assert set(meta["evidence"]) == {"image", "text", "tags", "market", "trend"}
    assert meta["thresholds"] == {"dup_cos": 0.92, "trend_match_cos": None}
    assert {"n", "share_mase_lt_1"} <= set(meta["trend_backtest"])
    assert {"name", "auc", "delta", "ci95", "significant", "val_choice"} <= set(meta["best_baseline"])
    assert {"test", "val"} <= set(meta["metrics"])
    assert set(meta["axis_modes"]) == {"image", "text", "market"}
    for a, e in meta["axis_modes"].items():
        rule = bool(e["val"]) and all(v["ci95"][0] > 0.5 for v in e["val"].values())
        forced = a == "image" and e["reason"].startswith("độ bền")
        assert e["mode"] == ("model" if rule and not forced else "formula")
        assert ("formula" in e) == (e["mode"] == "formula")


def check_evidence(meta):
    assert meta["evidence"]["tags"] == "practice"
    for axis, label in meta["evidence"].items():
        assert label in {"measured", "practice"}
        if label == "measured":
            assert meta["ablation"][axis]["lift"] >= 0.005
            assert meta["ablation"][axis]["ci95"][0] > 0


def check_dist(ref):
    for name in ("score_dist", "axis_dist", "formula_dist"):
        dist = dict(np.load(ref / f"{name}.npz"))
        assert dist and all(len(v) == 101 and np.all(np.diff(v) >= 0) for v in dist.values())
    assert not list(ref.glob("*.parquet"))


@pytest.fixture(scope="module")
def tiny(tmp_path_factory):
    from scripts.li.train import fit_bundle

    out = tmp_path_factory.mktemp("bundle")
    return fit_bundle(synthetic(), out), out


@pytest.fixture
def real():
    if not (BUNDLE / "meta.json").exists():
        pytest.skip("chưa có model bundle")
    return json.loads((BUNDLE / "meta.json").read_text("utf-8"))


def test_meta_has_required_keys(real):
    from scripts.li.assess import image_override

    check_meta(real)
    design = json.loads((BUNDLE / "reference/image_design.json").read_text("utf-8"))
    assert real["axis_modes"]["image"]["mode"] == "formula"
    assert real["axis_modes"]["image"]["reason"] == image_override(design)
    assert {"val", "test"} <= set(real["axis_modes"]["image"]["formula"])
    assert not list((BUNDLE / "reference").glob("*.joblib"))


def test_evidence_rule(real):
    check_evidence(real)


def test_score_dist_monotone(real):
    check_dist(BUNDLE / "reference")


def test_fit_bundle_tiny(tiny):
    meta, out = tiny
    check_meta(meta)
    check_evidence(meta)
    check_dist(out / "reference")
    assert all((out / f).exists() for f in FILES)
    assert json.loads((out / "meta.json").read_text("utf-8")) == meta
    assert "group" in meta["features"] and not {"age_days", "top25", "sold"} & set(meta["features"])
    import joblib

    image = joblib.load(out / "axis_image.joblib")
    assert (image.max_iter, image.max_depth) == (meta["axis_params"]["image"]["max_iter"], meta["axis_params"]["image"]["max_depth"])


def test_fit_bundle_context_loads(tiny):
    from app.core.listing_intel.context import load_context

    ctx = load_context(tiny[1] / "reference", trend_series={})
    assert set(ctx.group_median_price) >= {"bags", "fashion"}
    tops = json.loads((tiny[1] / "reference" / "top_medians.json").read_text("utf-8"))
    assert {"bags", "fashion", "all"} <= set(tops) and tops["all"]


def test_evidence_labels_rule():
    from scripts.li.ablation import evidence_labels

    ab = {"image": {"lift": 0.02, "ci95": [0.01, 0.03]}, "text": {"lift": 0.004, "ci95": [0.001, 0.01]},
          "market": {"lift": 0.03, "ci95": [-0.01, 0.05]}, "trend": {"lift": 0.01, "ci95": [0.002, 0.02]}}
    assert evidence_labels(ab, beats=True) == {
        "image": "measured", "text": "practice", "tags": "practice", "market": "practice", "trend": "measured"}
    assert set(evidence_labels(ab, beats=False).values()) == {"practice"}
