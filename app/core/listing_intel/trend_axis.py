from datetime import timedelta

import numpy as np
import pandas as pd
from statsmodels.tsa.seasonal import STL

from app.core.calendar_vn import upcoming_events
from app.core.listing_intel.normalize import fold
from app.core.metrics import mase

LO, HI = 0.5, 1.5
MOM_CAP = 0.5
CACHE_MAX = 512
_SEASON_CACHE: dict = {}


def week_of_year(at) -> int:
    return min(int(pd.Timestamp(at).isocalendar().week), 52) - 1


def _stl(values: np.ndarray):
    return STL(values, period=52, robust=True, seasonal_deg=0).fit()


def _clean(s: pd.Series) -> pd.Series:
    return s.dropna().astype(float).sort_index()


def informative(s) -> bool:
    return s is not None and len(s.dropna()) >= 8 and s.dropna().nunique() > 1


def seasonal_index(s: pd.Series) -> np.ndarray:
    s = _clean(s)
    if len(s) < 8 or s.std() == 0 or s.mean() <= 0:
        return np.ones(52)
    values = s.to_numpy()
    if len(s) >= 104:
        values = s.mean() + _stl(values).seasonal
    weeks = np.minimum(s.index.isocalendar().week.to_numpy().astype(int), 52) - 1
    idx = pd.Series(values).groupby(weeks).mean().reindex(range(52))
    idx = np.clip(idx.interpolate(limit_direction="both").to_numpy(), 0, None)
    return idx / idx.mean() if idx.mean() > 0 else np.ones(52)


def momentum(s: pd.Series, at) -> float:
    s = _clean(s)
    v = s[s.index <= pd.Timestamp(at)].to_numpy()
    if len(v) < 8 or v[-8:-4].mean() <= 0:
        return 0.0
    return float(v[-4:].mean() / v[-8:-4].mean() - 1)


def match_keywords(tokens, keywords, kw_vecs, text_vec, cos_min=None) -> list:
    text = f" {' '.join(fold(t) for t in tokens)} "
    hits = [(k, 1.0) for k in keywords if f" {fold(k)} " in text]
    if hits or cos_min is None or kw_vecs is None or text_vec is None:
        return hits
    norms = np.linalg.norm(kw_vecs, axis=1) * np.linalg.norm(text_vec)
    cos = kw_vecs @ text_vec / np.where(norms == 0, 1, norms)
    found = [(k, float(c)) for k, c in zip(keywords, cos) if c >= cos_min]
    return sorted(found, key=lambda x: -x[1])


def cached_season(kw: str, s: pd.Series) -> np.ndarray:
    key = (kw, len(s), s.index[-1], float(s.sum()))
    hit = _SEASON_CACHE.get(key)
    if hit is None:
        if len(_SEASON_CACHE) > CACHE_MAX:
            _SEASON_CACHE.clear()
        _SEASON_CACHE[key] = hit = seasonal_index(s)
    return hit


def demand_factor(matches, series, at, group_season=None) -> float:
    week = week_of_year(at)
    num = den = 0.0
    for kw, weight in matches:
        s = series.get(kw)
        if s is None:
            continue
        past = _clean(s)
        past = past[past.index <= pd.Timestamp(at)]
        if not informative(past):
            continue
        boost = 1 + float(np.clip(momentum(past, at), -MOM_CAP, MOM_CAP))
        num += weight * cached_season(kw, past)[week] * boost
        den += weight
    if den > 0:
        return float(np.clip(num / den, LO, HI))
    base = 1.0 if group_season is None else float(group_season[week])
    return float(np.clip(base, LO, HI))


def timeline(matches, series, start, weeks=8, group_season=None) -> list:
    start = pd.Timestamp(start).date()
    events = upcoming_events(start, weeks)
    out = []
    for i in range(weeks):
        ws = start + timedelta(days=7 * i)
        we = ws + timedelta(days=6)
        out.append({
            "week_start": ws,
            "demand_factor": demand_factor(matches, series, ws, group_season),
            "events": [e for e in events if ws <= e["date"] <= we],
        })
    return out


def backtest(series_by_kw: dict, horizon: int = 8) -> pd.DataFrame:
    rows = []
    for kw, s in series_by_kw.items():
        y = _clean(s).to_numpy()
        if len(y) < 104 + horizon:
            continue
        train, test = y[:-horizon], y[-horizon:]
        naive = train[-52:][:horizon]
        fit = _stl(train)
        stl = fit.trend[-1] + fit.seasonal[-52:][:horizon]
        m_stl = mase(test, stl, train, 52)
        m_naive = mase(test, naive, train, 52)
        rows.append({"keyword": kw, "mase_stl": m_stl, "mase_naive": m_naive,
                     "winner": "stl" if m_stl < m_naive else "naive"})
    return pd.DataFrame(rows, columns=["keyword", "mase_stl", "mase_naive", "winner"])
