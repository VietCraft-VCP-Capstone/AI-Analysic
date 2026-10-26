import json
import re

import numpy as np
import pandas as pd
from scipy.stats import pearsonr, spearmanr

from app.core.calendar_vn import SHOPPING_EVENTS
from app.core.listing_intel import trend_store
from app.core.listing_intel.normalize import norm
from app.core.listing_intel.trend_axis import MOM_CAP, week_of_year, backtest, momentum, seasonal_index
from scripts.li import paths
from scripts.li.reviews import GROUP_KEYWORDS

OCCASIONS = {"tet": ("tết",), "valentine": ("valentine", "người yêu"), "8/3": ("8/3",),
             "20/10": ("20/10",), "20/11": ("20/11", "thầy cô"), "noel": ("giáng sinh", "noel")}
EVENTS = {e["key"]: e["date_fn"] for e in SHOPPING_EVENTS}
WINDOW = range(-8, 3)
BEFORE = (-4, 0)


def _share(mask):
    return round(float(mask.mean()), 3) if len(mask) else None


def _selected(series, bt, horizon=8):
    prev = backtest({k: s.dropna().sort_index().iloc[:-horizon] for k, s in series.items()}, horizon)
    win = dict(zip(prev["keyword"], prev["winner"]))
    pick = bt["keyword"].map(win)
    return bt["mase_stl"].where(pick == "stl", bt["mase_naive"]).where(pick.notna())


def rolling(series, origins=6, horizon=8):
    cut = {k: v.dropna().sort_index() for k, v in series.items()}
    bts = [backtest({k: v.iloc[:len(v) - o * horizon] for k, v in cut.items()}, horizon).assign(origin=o)
           for o in range(origins + 1)]
    for o in range(origins):
        win = dict(zip(bts[o + 1]["keyword"], bts[o + 1]["winner"]))
        pick = bts[o]["keyword"].map(win)
        bts[o]["mase_selected"] = bts[o]["mase_stl"].where(pick == "stl", bts[o]["mase_naive"]).where(pick.notna())
    df = pd.concat(bts[:origins])
    per = df.groupby("keyword")[["mase_stl", "mase_naive", "mase_selected"]].mean()
    sel = df.dropna(subset=["mase_selected"])
    return {"origins": origins, "weeks_covered": origins * horizon, "pairs": int(len(df)),
            "share_pairs_stl_lt_1": _share(df["mase_stl"] < 1), "share_pairs_naive_lt_1": _share(df["mase_naive"] < 1),
            "share_pairs_selected_lt_1": _share(sel["mase_selected"] < 1),
            "share_kw_mean_stl_lt_1": _share(per["mase_stl"] < 1),
            "share_kw_mean_naive_lt_1": _share(per["mase_naive"] < 1),
            "share_kw_mean_selected_lt_1": _share(per["mase_selected"].dropna() < 1),
            "share_pairs_stl_beats_naive": _share(df["mase_stl"] < df["mase_naive"]),
            "share_pairs_selected_beats_naive": _share(sel["mase_selected"] < sel["mase_naive"]),
            "median_mase_stl": round(float(df["mase_stl"].median()), 3),
            "median_mase_naive": round(float(df["mase_naive"].median()), 3)}


def backtest_summary(series=None):
    series = trend_store.weekly_series() if series is None else series
    bt = backtest(series)
    bt["mase_selected"] = _selected(series, bt)
    missing = paths.clean("trend_missing.json")
    return {
        "n": int(len(bt)), "n_keywords": len(series), "horizon_weeks": 8,
        "share_mase_lt_1": _share(bt["mase_stl"] < 1),
        "share_naive_mase_lt_1": _share(bt["mase_naive"] < 1),
        "share_stl_beats_naive": _share(bt["mase_stl"] < bt["mase_naive"]),
        "share_selected_lt_1": _share(bt["mase_selected"].dropna() < 1),
        "share_selected_beats_naive": _share((bt["mase_selected"] < bt["mase_naive"])[bt["mase_selected"].notna()]),
        "n_selected": int(bt["mase_selected"].notna().sum()),
        "share_oracle_lt_1": _share(bt[["mase_stl", "mase_naive"]].min(axis=1) < 1),
        "median_mase_stl": round(float(bt["mase_stl"].median()), 3) if len(bt) else None,
        "median_mase_naive": round(float(bt["mase_naive"].median()), 3) if len(bt) else None,
        "rolling": rolling(series),
        "missing_keywords": json.loads(missing.read_text("utf-8")) if missing.exists() else [],
        "per_keyword": bt.round(3).to_dict("records"),
    }


def keyword_group(kw):
    text = norm(kw)
    return next((g for g, rx in GROUP_KEYWORDS if re.search(rx, text)), "home")


def monthly_profile(s):
    m = s.dropna().resample("MS").mean()
    t = pd.DataFrame({"y": m.index.year, "m": m.index.month, "v": m.to_numpy()})
    t = t.pivot(index="y", columns="m", values="v").reindex(columns=range(1, 13)).dropna()
    t = t[t.mean(axis=1) > 0]
    return t.div(t.mean(axis=1), axis=0).mean() if len(t) else None


def season_corr(series, monthly):
    out = {}
    for g, rv in monthly.groupby("group"):
        profs = [p for k, s in series.items() if keyword_group(k) == g and (p := monthly_profile(s)) is not None]
        if not profs:
            out[g] = {"n_keywords": 0}
            continue
        gt = pd.concat(profs, axis=1).mean(axis=1).to_numpy()
        rev = rv.set_index("month")["index"].reindex(range(1, 13)).to_numpy()
        pr, sr = pearsonr(gt, rev), spearmanr(gt, rev)
        out[g] = {"n_keywords": len(profs), "pearson": round(float(pr.statistic), 3),
                  "p_pearson": round(float(pr.pvalue), 3), "spearman": round(float(sr.statistic), 3),
                  "p_spearman": round(float(sr.pvalue), 3)}
    return out


def occasion(kw):
    text = norm(kw)
    return next((e for e, keys in OCCASIONS.items() if any(norm(k) in text for k in keys)), None)


def factor(s, at):
    past = s[s.index <= at]
    return seasonal_index(past)[week_of_year(at)] * (1 + float(np.clip(momentum(past, at), -MOM_CAP, MOM_CAP)))


def _peaks(kw, s, ev):
    s, rows = s.dropna().sort_index(), []
    for year in range(s.index.min().year, s.index.max().year + 1):
        try:
            when = pd.Timestamp(EVENTS[ev](year))
        except KeyError:
            continue
        weeks = [when + pd.Timedelta(weeks=o) for o in WINDOW]
        if weeks[0] - pd.Timedelta(weeks=52) < s.index.min() or weeks[-1] > s.index.max():
            continue
        f = [factor(s, w) for w in weeks]
        rows.append({"keyword": kw, "event": ev, "year": year, "peak_offset": WINDOW[int(np.argmax(f))]})
    return rows


def peak_check(series):
    rows = [r for k, s in series.items() if (ev := occasion(k)) for r in _peaks(k, s, ev)]
    df = pd.DataFrame(rows, columns=["keyword", "event", "year", "peak_offset"])
    ok = df["peak_offset"].between(*BEFORE)
    per = df.assign(ok=ok).groupby(["keyword", "event"]).agg(
        years=("year", "size"), median_offset=("peak_offset", "median"), share_before=("ok", "mean"))
    return {"n_pairs": int(len(df)), "share_peak_before": _share(ok), "window_weeks": list(BEFORE),
            "search_weeks": [WINDOW.start, WINDOW.stop - 1],
            "per_keyword": per.round(3).reset_index().to_dict("records")}


def run():
    series = trend_store.weekly_series()
    monthly = pd.read_parquet(paths.clean("tikireviews_monthly.parquet"))
    return {"backtest": backtest_summary(series), "season_corr": season_corr(series, monthly),
            "peaks": peak_check(series)}
