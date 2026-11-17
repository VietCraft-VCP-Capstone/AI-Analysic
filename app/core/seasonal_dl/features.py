"""Đặc trưng chuỗi thời gian cho mô hình Deep Learning dự báo cầu mùa vụ (F38).

Quy ước thời gian: chuỗi tuần y[0..T-1]. Tại "điểm gốc" t (chỉ dùng y[:t]),
dự báo H tuần y[t..t+H-1].

Không rò rỉ (Leakage-free):
  * Mọi đặc trưng quá khứ & tĩnh chỉ dùng y[:t].
  * Vùng lân cận mùa vụ (±3 tuần quanh t-52+h) có chỉ số tối đa t-24 < t.
  * Covariate lịch (sin/cos năm, khoảng cách Tết âm lịch, Trung thu) biết trước hoàn toàn.
"""
from __future__ import annotations

from datetime import date
from functools import lru_cache
from typing import Dict, Tuple

import numpy as np
import pandas as pd

from app.core import calendar_vn

L = 52          # độ dài cửa sổ quá khứ (1 năm)
H = 26          # tầm dự báo (tuần)
N_COV = 4       # sin, cos, ngày-đến-Tết, ngày-đến-Trung-thu
LAG_RADIUS = 3  # lân cận ±3 tuần quanh lag-52 để căn chỉnh lịch âm
LAG_WIN = 2 * LAG_RADIUS + 1  # 7 tuần
N_STATIC = 6    # thống kê tĩnh của chuỗi tại gốc t
# Bố cục vector đặc trưng:
# [0 : L]                      -> y_past (L=52)
# [L : L + L*N_COV]            -> cov_past (52*4 = 208)
# [.. : .. + H*N_COV]          -> cov_future (26*4 = 104)
# [.. : .. + H*N_COV]          -> cov_lag52 (26*4 = 104)
# [.. : .. + H*LAG_WIN]        -> lag_neighbors (26*7 = 182), cột giữa (idx=3) là lag-52
# [.. : .. + N_STATIC]         -> static_stats (6)
FEATURE_DIM = L + L * N_COV + H * N_COV * 2 + H * LAG_WIN + N_STATIC
RATIO_CLIP = 12.0
QUANTILES = (0.1, 0.5, 0.9)


@lru_cache(maxsize=4096)
def _days_to_tet(d: date) -> int:
    return int(calendar_vn.days_to_tet(d))


@lru_cache(maxsize=4096)
def _days_to_mid_autumn(d: date) -> int:
    best = None
    for y in (d.year - 1, d.year, d.year + 1):
        try:
            diff = (d - calendar_vn.get_mid_autumn_date(y)).days
        except Exception:
            continue
        if best is None or abs(diff) < abs(best):
            best = diff
    return int(best) if best is not None else 365


def week_covariates(dates: pd.DatetimeIndex) -> np.ndarray:
    """(n, 4): chu kỳ năm (sin/cos) + khoảng cách tới 2 ngày lễ âm lịch (Tết, Trung thu)."""
    out = np.zeros((len(dates), N_COV), dtype=np.float32)
    for i, ts in enumerate(dates):
        d = ts.date()
        doy = ts.dayofyear
        out[i, 0] = np.sin(2 * np.pi * doy / 365.25)
        out[i, 1] = np.cos(2 * np.pi * doy / 365.25)
        out[i, 2] = float(np.clip(_days_to_tet(d) / 90.0, -1.0, 1.0))
        out[i, 3] = float(np.clip(_days_to_mid_autumn(d) / 90.0, -1.0, 1.0))
    return out


def make_features(y: np.ndarray, cov_window: np.ndarray, t: int) -> Tuple[np.ndarray, float]:
    """Vector đặc trưng tại gốc t.
    y: mảng lịch sử (chỉ dùng y[:t]).
    cov_window: covariate cho khoảng [t - L .. t + H - 1], shape (L + H, N_COV).
    Trả về (features, scale).
    """
    window = y[t - L:t]
    scale = float(window.mean())
    if scale < 1.0:
        raise ValueError("scale<1")

    y_past = np.clip(window / scale, 0.0, RATIO_CLIP).astype(np.float32)
    cov_past = cov_window[:L].reshape(-1).astype(np.float32)
    cov_future = cov_window[L:L + H].reshape(-1).astype(np.float32)
    cov_lag = cov_window[0:H].reshape(-1).astype(np.float32)  # cov tại t-52..t-52+H-1

    # Lân cận ±3 tuần quanh lag-52 cho từng bước dự báo h in [0..H-1]
    lag_neighbors = np.zeros((H, LAG_WIN), dtype=np.float32)
    for h in range(H):
        center = t - 52 + h
        for j, d in enumerate(range(-LAG_RADIUS, LAG_RADIUS + 1)):
            idx = max(0, center + d)
            lag_neighbors[h, j] = float(np.clip(y[idx] / scale, 0.0, RATIO_CLIP))

    # Đặc trưng tĩnh & động lượng ngắn hạn (không rò rỉ)
    recent_4w = float(np.clip(y[t - 4:t].mean() / scale, 0.0, RATIO_CLIP))
    recent_8w = float(np.clip(y[t - 8:t].mean() / scale, 0.0, RATIO_CLIP))
    if t >= 56:
        yoy_base = float(y[t - 56:t - 52].mean())
        yoy_ratio = float(np.clip((y[t - 4:t].mean() + 0.5) / (yoy_base + 0.5), 0.1, 5.0))
    else:
        yoy_ratio = 1.0
    cv = float(np.clip(window.std() / (scale + 1e-6), 0.0, 5.0))
    peak_ratio = float(np.clip(window.max() / scale, 0.0, RATIO_CLIP))
    log_scale = float(np.log1p(scale) / 5.0)
    static_stats = np.array([log_scale, cv, recent_4w, recent_8w, yoy_ratio, peak_ratio], dtype=np.float32)

    feats = np.concatenate([
        y_past,
        cov_past,
        cov_future,
        cov_lag,
        lag_neighbors.reshape(-1),
        static_stats,
    ]).astype(np.float32)
    return feats, scale


def extract_lag52_from_features(X: np.ndarray) -> np.ndarray:
    """Lấy cột lag-52 (offset 0 trong lag_neighbors) từ batch đặc trưng X."""
    lag_start = L + L * N_COV + H * N_COV * 2
    lag_block = X[:, lag_start:lag_start + H * LAG_WIN].reshape(-1, H, LAG_WIN)
    return lag_block[:, :, LAG_RADIUS]


def build_samples(series: Dict[str, pd.Series], t_lo: int | None = None, t_hi: int | None = None,
                  end_before: int | None = None):
    """Dựng mẫu từ nhiều chuỗi (mô hình toàn cục — học chung mọi từ khóa)."""
    X, Y, S, meta = [], [], [], []
    for kw, s in series.items():
        y = s.values.astype(np.float64)
        T = len(y)
        cov_all = week_covariates(s.index)
        lo = max(L, t_lo if t_lo is not None else L)
        hi = min(T - H, t_hi if t_hi is not None else T - H)
        if end_before is not None:
            hi = min(hi, end_before - H)
        for t in range(lo, hi + 1):
            try:
                f, sc = make_features(y, cov_all[t - L:t + H], t)
            except ValueError:
                continue
            X.append(f)
            Y.append(np.clip(y[t:t + H] / sc, 0.0, RATIO_CLIP * 2))
            S.append(sc)
            meta.append((kw, t))
    if not X:
        return (np.zeros((0, FEATURE_DIM), np.float32), np.zeros((0, H), np.float32),
                np.zeros((0,), np.float64), [])
    return np.stack(X), np.stack(Y).astype(np.float32), np.asarray(S), meta
