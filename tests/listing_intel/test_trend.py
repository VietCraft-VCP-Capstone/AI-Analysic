from datetime import date

import numpy as np
import pandas as pd
import pytest

from app.core import calendar_vn
from app.core.listing_intel import trend_axis as ta


def _weekly(fn, start="2021-08-15", periods=262):
    idx = pd.date_range(start, periods=periods, freq="W-SUN")
    woy = np.minimum(idx.isocalendar().week.to_numpy().astype(int), 52)
    return pd.Series([fn(w) for w in woy], index=idx, dtype=float)


def _peak(week, base=20.0, height=60.0):
    return lambda w: base + height * np.exp(-0.5 * ((w - week) / 2.0) ** 2)


def test_mid_autumn_2026():
    ev = next(e for e in calendar_vn.SHOPPING_EVENTS if e["key"] == "trung_thu")
    assert ev["date_fn"](2026) == date(2026, 9, 25)
    assert calendar_vn.MID_AUTUMN_DATES[2026] == "2026-09-25"


def test_black_friday_2026():
    ev = next(e for e in calendar_vn.SHOPPING_EVENTS if e["key"] == "black_friday")
    assert ev["date_fn"](2026) == date(2026, 11, 27)
    assert ev["date_fn"](2024) == date(2024, 11, 29)


def test_upcoming_events_window():
    keys = {e["key"] for e in calendar_vn.upcoming_events(date(2026, 10, 21), 6)}
    assert {"20/11", "halloween"} <= keys
    assert "tet" not in keys


def test_upcoming_events_sorted_with_prep_start():
    evs = calendar_vn.upcoming_events(date(2026, 10, 21), 16)
    assert [e["date"] for e in evs] == sorted(e["date"] for e in evs)
    assert all(e["prep_start"] < e["date"] for e in evs)
    assert "tet" in {e["key"] for e in evs}


def test_seasonal_index_peaks_at_season():
    idx = ta.seasonal_index(_weekly(_peak(42)))
    assert len(idx) == 52
    assert int(np.argmax(idx)) in {41, 42, 43}
    assert abs(idx.mean() - 1) < 1e-6


def test_seasonal_index_short_series_uses_week_means():
    idx = ta.seasonal_index(_weekly(_peak(30), periods=60))
    assert len(idx) == 52 and abs(idx.mean() - 1) < 1e-6


def test_momentum_flat_zero():
    assert ta.momentum(_weekly(lambda w: 0.0), date(2026, 8, 16)) == 0.0
    assert ta.momentum(_weekly(lambda w: 7.0), date(2026, 8, 16)) == 0.0


def test_momentum_rising():
    s = pd.Series([10.0] * 4 + [20.0] * 4, index=pd.date_range("2026-06-28", periods=8, freq="W-SUN"))
    assert ta.momentum(s, date(2026, 8, 16)) == 1.0


def test_demand_factor_bounds():
    s = _weekly(lambda w: 1.0)
    s.iloc[-4:] = 500.0
    at = s.index[-1].date()
    assert ta.demand_factor([("k", 1.0)], {"k": s}, at, None) == pytest.approx(1.5)
    assert ta.demand_factor([], {}, at, None) == 1.0


def test_demand_factor_falls_back_to_group_season():
    group = np.full(52, 1.3)
    flat = {"k": _weekly(lambda w: 0.0)}
    assert ta.demand_factor([("k", 1.0)], flat, date(2026, 10, 21), group) == 1.3
    assert ta.demand_factor([("missing", 1.0)], {}, date(2026, 10, 21), group) == 1.3


def test_timeline_peaks_before_event():
    series = {"k": _weekly(_peak(46, base=40.0, height=20.0))}
    tl = ta.timeline([("k", 1.0)], series, date(2026, 10, 5))
    factors = [w["demand_factor"] for w in tl]
    best = max(tl, key=lambda w: w["demand_factor"])
    assert len(tl) == 8 and max(factors) < ta.HI and min(factors) > ta.LO
    assert abs((best["week_start"] - date(2026, 11, 9)).days) <= 7
    assert factors[0] < best["demand_factor"] - 0.2


def test_demand_factor_ignores_data_after_at():
    idx = pd.date_range("2021-08-15", periods=262, freq="W-SUN")
    woy = np.minimum(idx.isocalendar().week.to_numpy().astype(int), 52)
    noise = np.random.default_rng(1).normal(0, 0.3, len(idx))
    late = idx > pd.Timestamp("2023-06-25")
    s = pd.Series(10 + noise + np.where(late, _peak(20, 0, 80)(woy), 0), index=idx)
    before = ta.demand_factor([("k", 1.0)], {"k": s}, date(2023, 5, 21))
    after = ta.demand_factor([("k", 1.0)], {"k": s}, date(2026, 5, 17))
    assert abs(before - 1.0) < 0.15
    assert after > 1.3


def test_season_cache_is_capped(monkeypatch):
    monkeypatch.setattr(ta, "CACHE_MAX", 3)
    s = _weekly(_peak(20))
    for i in range(10):
        ta.cached_season(f"k{i}", s)
    assert len(ta._SEASON_CACHE) <= 4


def test_upcoming_events_logs_missing_year_once(caplog):
    calendar_vn._MISSING_LOGGED.clear()
    with caplog.at_level("WARNING", logger="app.core.calendar_vn"):
        calendar_vn.upcoming_events(date(2030, 12, 1), 16)
        first = len(caplog.records)
        calendar_vn.upcoming_events(date(2030, 12, 1), 16)
    assert first >= 1 and len(caplog.records) == first


def test_match_keywords_text_then_vector():
    kws = ["áo thun", "túi tote"]
    got = ta.match_keywords(["ao", "thun", "nu"], kws, None, None)
    assert got == [("áo thun", 1.0)]
    assert ta.match_keywords(["Quà", "20", "11"], ["quà 20/11"], None, None) == [("quà 20/11", 1.0)]
    vecs = np.array([[1.0, 0.0], [0.0, 1.0]])
    assert ta.match_keywords(["xyz"], kws, vecs, np.array([0.1, 1.0])) == []
    got = ta.match_keywords(["xyz"], kws, vecs, np.array([0.1, 1.0]), cos_min=0.8)
    assert [k for k, _ in got] == ["túi tote"] and got[0][1] >= 0.8
    assert ta.match_keywords(["xyz"], kws, vecs, np.array([0.7, 0.7]), cos_min=0.8) == []


def test_backtest_columns_and_winner():
    noisy = _weekly(_peak(20))
    noisy += np.random.default_rng(0).normal(0, 3, len(noisy))
    df = ta.backtest({"a": noisy, "short": _weekly(_peak(20), periods=50)}, horizon=8)
    assert list(df.columns) == ["keyword", "mase_stl", "mase_naive", "winner"]
    assert df["keyword"].tolist() == ["a"]
    assert np.isfinite(df[["mase_stl", "mase_naive"]].to_numpy()).all()
    assert df["winner"].iloc[0] in {"stl", "naive"}


def test_weekly_series_reads_store_and_caches(monkeypatch):
    from app.core.listing_intel import trend_store as ts

    calls = []

    def fake():
        calls.append(1)
        return pd.DataFrame(
            {"keyword": ["a", "a", "b"],
             "observed_on": pd.to_datetime(["2026-01-11", "2026-01-04", "2026-01-04"]),
             "scaled": [2.0, 1.0, None]}
        )

    monkeypatch.setattr(ts, "_from_mongo", fake)
    monkeypatch.setitem(ts._cache, "data", None)
    out = ts.weekly_series()
    assert list(out) == ["a"] and out["a"].tolist() == [1.0, 2.0]
    ts.weekly_series()
    assert len(calls) == 1


def test_weekly_series_falls_back_to_parquet(monkeypatch, tmp_path):
    from app.core.listing_intel import trend_store as ts

    path = tmp_path / "t.parquet"
    pd.DataFrame(
        {"keyword": ["k"] * 2, "observed_on": pd.to_datetime(["2026-01-04", "2026-01-11"]),
         "scaled": [3.0, 4.0], "granularity": ["weekly", "daily"]}
    ).to_parquet(path)
    monkeypatch.setattr(ts, "_from_mongo", lambda: pd.DataFrame(columns=ts.COLS))
    monkeypatch.setattr(ts, "PARQUET", path)
    monkeypatch.setitem(ts._cache, "data", None)
    assert ts.weekly_series()["k"].tolist() == [3.0]


def test_weekly_series_mongo_error_logs_and_falls_back(monkeypatch, tmp_path, caplog):
    from pymongo.errors import ServerSelectionTimeoutError

    from app.core.listing_intel import trend_store as ts

    path = tmp_path / "t.parquet"
    pd.DataFrame(
        {"keyword": ["k"], "observed_on": pd.to_datetime(["2026-01-04"]),
         "scaled": [3.0], "granularity": ["weekly"]}
    ).to_parquet(path)

    def boom():
        raise ServerSelectionTimeoutError("down")

    monkeypatch.setattr(ts, "_from_mongo", boom)
    monkeypatch.setattr(ts, "PARQUET", path)
    monkeypatch.setitem(ts._cache, "data", None)
    with caplog.at_level("WARNING", logger=ts.__name__):
        assert ts.weekly_series()["k"].tolist() == [3.0]
    assert any("parquet" in r.message for r in caplog.records)


def test_weekly_series_non_mongo_error_propagates(monkeypatch):
    from app.core.listing_intel import trend_store as ts

    def boom():
        raise ValueError("bad frame")

    monkeypatch.setattr(ts, "_from_mongo", boom)
    monkeypatch.setitem(ts._cache, "data", None)
    with pytest.raises(ValueError):
        ts.weekly_series()
