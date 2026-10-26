import numpy as np
import pandas as pd
import pytest

from tests.listing_intel.test_bundle import synthetic


def weekly(kw_bump=None, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2021-08-15", periods=262, freq="W-SUN")
    base = 50 + 20 * np.sin(2 * np.pi * idx.isocalendar().week.to_numpy() / 52) + rng.normal(0, 3, len(idx))
    if kw_bump:
        for y in range(2021, 2027):
            ev = pd.Timestamp(f"{y}-10-20")
            base[(idx >= ev - pd.Timedelta(weeks=3)) & (idx <= ev)] += 60
    return pd.Series(base, index=idx)


@pytest.fixture(scope="module")
def results(tmp_path_factory):
    from scripts.li import retrieval, sanity, trend_eval
    from scripts.li.train import fit_bundle

    out = tmp_path_factory.mktemp("bundle")
    table = synthetic()
    meta = fit_bundle(table, out)
    series = {"áo thun": weekly(), "quà 20/10": weekly(True, 1)}
    monthly = pd.DataFrame({"group": "fashion", "month": range(1, 13), "index": 1.0 + np.arange(12) / 100,
                            "n_reviews": 100})
    rng = np.random.default_rng(0)
    img = rng.normal(size=(300, 64))
    split = {"train": {"rows": 1, "top25_rate": 0.25, "sellers": 1, "rows_no_seller": 0}}
    return {
        "generated": "2026-10-21", "model": meta, "shift": None, "image_sanity": None,
        "data": {"tiki26": {"raw_rows": 1, "clean_rows": 1, "table_rows": 1, "groups": ["bags", "fashion"],
                            "splits": split, "axis_all_nan_share": dict.fromkeys(["image", "text", "market", "trend"], 0.0)}},
        "coverage": {"tiki26": {"n_images_nan": 0.0, "desc_empty": 0.0, "has_image": 1.0}},
        "sanity": sanity.run(table, meta, out),
        "retrieval": retrieval.retrieval(img, img + rng.normal(scale=0.1, size=img.shape)),
        "trend": {"backtest": trend_eval.backtest_summary(series), "season_corr": trend_eval.season_corr(series, monthly),
                  "peaks": trend_eval.peak_check(series)},
    }


def test_render_has_sections_and_numbers(results):
    from scripts.li.report import render

    text = render(results)
    for head in ("## 1. Tóm tắt", "## 4. Chọn feature", "## 6. Ablation", "## 9. Sanity check",
                 "## 12. Điểm yếu và ảnh hưởng"):
        assert head in text
    assert f"{results['model']['metrics']['test']['roc_auc']:.3f}" in text


def test_render_previous_and_gate_rules(results):
    from scripts.li.report import render
    from scripts.li.report_history import history

    old = {**results, "model": {**results["model"], "model_version": "li-0.9"}, "generated": "2026-10-20"}
    past = history(old, results["model"]["model_version"])
    assert [h["model_version"] for h in past] == ["li-0.9"] and history(results, results["model"]["model_version"]) == []
    newer = {**results, "history": past}
    assert [h["model_version"] for h in history(newer, "li-9")] == ["li-0.9", results["model"]["model_version"]]
    text = render(newer)
    best = results["model"]["best_baseline"]
    assert "li-0.9 (2026-10-20)" in text and "đã được chấm và báo cáo cho `li-0.9`" in text
    assert f"`{best['name']}`" in text and f"`{best['val_choice']['name']}`" in text


def test_render_keeps_manual_blocks(results):
    from scripts.li.report import render

    first = render(results).replace("_Chưa điền. Task 12 viết", "ĐÃ VIẾT TAY. Task 12 viết")
    again = render(results, first)
    assert "ĐÃ VIẾT TAY" in again and again.count("<!-- manual:weakness -->") == 1


def test_sanity_on_synthetic(results):
    s = results["sanity"]
    assert s["deterministic"]["pass"] and s["banned_features"]["pass"] and s["seller_overlap"]["pass"]
    assert len(s["shuffled_labels"]["auc_runs"]["test"]) == 5


def test_trend_checks(results):
    bt, pk = results["trend"]["backtest"], results["trend"]["peaks"]
    assert bt["n"] == 2 and bt["n_selected"] == 2 and bt["rolling"]["pairs"] == 12
    assert pk["n_pairs"] >= 3 and pk["share_peak_before"] == 1.0
    assert results["retrieval"]["top1_img_to_txt"] > 0.9


def test_finite_drops_nan_and_inf():
    from scripts.li.train import finite

    assert finite({"a": float("inf"), "b": [float("nan"), 1.0], 3: (2,)}) == {"a": None, "b": [None, 1.0], "3": [2]}


def test_top_hit_ignores_row_order_on_ties():
    from scripts.li.measure import top_hit

    y = np.array([1, 0, 0, 0, 1, 0, 0, 0, 0, 0])
    flat = np.zeros(10)
    assert top_hit(y, flat) == top_hit(y[::-1], flat) == 0.2
    s = np.array([5, 1, 1, 1, 1, 1, 1, 1, 1, 0.0])
    assert top_hit(y, s) == pytest.approx((1 + 1 / 8) / 2, abs=1e-3)
