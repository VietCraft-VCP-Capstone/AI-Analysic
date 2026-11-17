"""Suy luận dự báo cầu mùa vụ cho API F38.

Chọn phương pháp theo bằng chứng backtest (meta.json), không theo ý muốn:
  * validated=True  -> ensemble mạng nơ-ron (P50) + khoảng conformal của mô hình.
  * validated=False -> baseline seasonal-naive (cùng kỳ năm trước) + khoảng conformal của baseline.
Phương pháp được trả kèm kết quả để UI hiển thị đúng tên, không gắn nhãn "AI" cho thứ không phải AI.

Đối tượng dự báo: chỉ số quan tâm tìm kiếm Google Trends (0-100), KHÔNG phải số đơn.
"""
from __future__ import annotations

import json
import threading
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from app.core.seasonal_dl.features import FEATURE_DIM, H, L, extract_lag52_from_features, make_features, week_covariates

MODEL_DIR = Path(__file__).parent / "model"
BUCKETS = {"1-4w": (0, 4), "5-13w": (4, 13), "14-26w": (13, 26)}
_lock = threading.Lock()
_state: Dict[str, Any] = {"loaded": False, "meta": None, "models": None}


def load_meta() -> Optional[Dict[str, Any]]:
    p = MODEL_DIR / "meta.json"
    if not p.exists():
        return None
    return json.loads(p.read_text("utf-8"))


def _load_models(meta: Dict[str, Any]):
    import torch
    from app.core.seasonal_dl.model import QuantileForecaster
    blob = torch.load(MODEL_DIR / "forecaster.pt", map_location="cpu", weights_only=True)
    models = []
    for st in blob["states"]:
        m = QuantileForecaster()
        m.load_state_dict(st)
        m.eval()
        models.append(m)
    return models


def _ensure_loaded() -> None:
    with _lock:
        if _state["loaded"]:
            return
        meta = load_meta()
        _state["meta"] = meta
        if meta and meta.get("validated") and (MODEL_DIR / "forecaster.pt").exists():
            try:
                _state["models"] = _load_models(meta)
            except Exception:
                _state["models"] = None
        _state["loaded"] = True


def method_info() -> Dict[str, Any]:
    """Thông tin minh bạch về phương pháp + số backtest thật, dùng cho scorecard/evidence."""
    _ensure_loaded()
    meta = _state["meta"]
    if not meta:
        return {"available": False, "method": "none"}
    using_dl = _state["models"] is not None
    return {
        "available": True,
        "method": "deep_ensemble" if using_dl else "seasonal_naive_conformal",
        "validated_deep_model": bool(meta.get("validated")),
        "avg_coverage_raw": meta.get("avg_coverage_p10_p90"),
        "improvement_vs_naive_pct": meta.get("improvement_vs_naive_scaled_mae_pct"),
        "conformal_cross_check_coverage": meta.get("conformal_cross_check_coverage"),
        "folds": meta.get("backtest", {}).get("folds", []),
        "data": meta.get("data"),
        "trained_at": meta.get("trained_at"),
    }


def forecast(series: pd.Series, horizon: int = H) -> Optional[Dict[str, Any]]:
    """Dự báo `horizon` tuần tiếp theo sau điểm quan sát cuối. None nếu thiếu dữ liệu/mô hình."""
    _ensure_loaded()
    meta = _state["meta"]
    if not meta or len(series) < L + 52:
        return None
    y = series.values.astype(np.float64)
    T = len(y)
    future = pd.DatetimeIndex([series.index[-1] + timedelta(weeks=i) for i in range(1, H + 1)])
    cov_past = week_covariates(series.index[-L:])
    cov_fut = week_covariates(future)
    cov_window = np.concatenate([cov_past, cov_fut], axis=0)
    try:
        feats, scale = make_features(np.concatenate([y, np.zeros(H)]), cov_window, T)
    except ValueError:
        return None
    lag = extract_lag52_from_features(feats[None, :])[0]
    models = _state["models"]
    if models is not None:
        import torch
        with torch.no_grad():
            xs = torch.from_numpy(feats[None, :])
            p50 = torch.stack([m(xs) for m in models]).mean(0).numpy()[0, :, 1]
        method, qres = "deep_ensemble", meta["conformal_residual_quantiles"]["model"]
    else:
        p50, method, qres = lag, "seasonal_naive_conformal", meta["conformal_residual_quantiles"]["naive"]
    p50 = np.maximum(p50, 0.0)
    lo, hi = np.zeros(H), np.zeros(H)
    for name, (a, b) in BUCKETS.items():
        lo[a:b] = p50[a:b] + qres[name][0]
        hi[a:b] = p50[a:b] + qres[name][1]
    lo, hi = np.maximum(np.minimum(lo, p50), 0.0), np.maximum(hi, p50)
    n = min(horizon, H)
    return {
        "method": method,
        "last_observed": str(series.index[-1].date()),
        "scale": float(scale),
        "weeks": [str(d.date()) for d in future[:n]],
        "p10": (lo[:n] * scale).round(2).tolist(),
        "p50": (p50[:n] * scale).round(2).tolist(),
        "p90": (hi[:n] * scale).round(2).tolist(),
    }


def _level(points: List[tuple], lo: date, hi: date) -> Optional[float]:
    vals = [v for d, v in points if lo < d <= hi]
    return float(np.mean(vals)) if len(vals) >= 6 else None


def event_demand_uplift(series: pd.Series, event_dates: Dict[int, date], event_date: date,
                        window_days: int, today: date) -> Optional[Dict[str, Any]]:
    """Mức cầu kỳ vọng trong cửa sổ bán của dịp so với mức nền 13 tuần gần nhất tính đến HÔM NAY.

    Mức nền đặt đúng kỳ với baseline đơn hàng của shop (13 tuần trước hôm nay). Nếu dữ liệu
    Trends dừng trước hôm nay, các tuần còn thiếu được lấp bằng P50 dự báo (trong tầm H tuần).
    Cửa sổ dịp: dùng dự báo nếu nằm trong tầm; xa hơn thì dùng thống kê lịch sử cùng cửa sổ
    các năm trước và ghi rõ 'historical_same_window' (mô tả lịch sử, không phải dự báo).
    event_dates: {năm: ngày diễn ra} của các năm đã có dữ liệu.
    """
    if len(series) < 60:
        return None
    last = series.index[-1].date()
    win_start, win_end = event_date - timedelta(days=window_days), event_date
    observed = [(d.date(), float(v)) for d, v in series.items()]
    fc = forecast(series)
    fc_points = ([(date.fromisoformat(w), float(v)) for w, v in zip(fc["weeks"], fc["p50"])] if fc else [])
    base = _level(observed + fc_points, today - timedelta(weeks=13), today)
    if not base or base <= 0:
        return None

    if fc and fc_points:
        idx = [i for i, (d, _) in enumerate(fc_points) if win_start - timedelta(days=3) <= d <= win_end + timedelta(days=3)]
        if len(idx) >= 2 and win_end <= fc_points[-1][0] + timedelta(days=7):
            f = lambda k: float(np.mean([fc[k][i] for i in idx]))
            return {"method": fc["method"], "basis": "forecast", "baseline_level": round(base, 2),
                    "uplift_p10": round(f("p10") / base, 2), "uplift_p50": round(f("p50") / base, 2),
                    "uplift_p90": round(f("p90") / base, 2), "last_observed": fc["last_observed"],
                    "window": [win_start.isoformat(), win_end.isoformat()]}

    ratios: List[float] = []
    offset = (event_date - today).days
    for ev in event_dates.values():
        ws, we = ev - timedelta(days=window_days), ev
        ref_end = ev - timedelta(days=offset)
        in_win = [v for d, v in observed if ws <= d <= we]
        ref = _level(observed, ref_end - timedelta(weeks=13), ref_end)
        if len(in_win) >= 2 and ref and ref > 0:
            ratios.append(float(np.mean(in_win) / ref))
    if len(ratios) < 2:
        return None
    return {"method": "historical_same_window", "basis": "history", "baseline_level": round(base, 2),
            "uplift_p10": round(float(np.min(ratios)), 2), "uplift_p50": round(float(np.median(ratios)), 2),
            "uplift_p90": round(float(np.max(ratios)), 2), "n_years": len(ratios), "last_observed": str(last),
            "window": [win_start.isoformat(), win_end.isoformat()]}


def calibrate_shop_uplift(
    market_uplift: Optional[Dict[str, Any]],
    shop_weekly_orders: List[float],
    trend_weekly_vals: List[float],
) -> Dict[str, Any]:
    """Hiệu chuẩn hệ số co giãn Search-to-Order riêng theo từng shop (Amazon/Shopee style).

    Ước lượng độ co giãn beta giữa biến động tìm kiếm (Google Trends) và biến động đơn hàng thực tế
    của shop bằng Ridge regression 1 biến có kẹp biên an toàn [0.35, 1.45].
    Khi shop có < 12 tuần lịch sử đối soát, giữ nguyên beta = 1.0 (calibrated=False).
    """
    if not market_uplift:
        return {"calibrated": False, "elasticity_beta": 1.0, "n_weeks": 0}

    n = min(len(shop_weekly_orders), len(trend_weekly_vals))
    if n < 12:
        return {
            **market_uplift,
            "calibrated": False,
            "elasticity_beta": 1.0,
            "n_weeks": n,
        }

    s_arr = np.asarray(shop_weekly_orders[-n:], dtype=np.float64)
    t_arr = np.asarray(trend_weekly_vals[-n:], dtype=np.float64)
    t_mean = float(np.mean(t_arr))
    s_mean = float(np.mean(s_arr))
    if t_mean <= 1e-6 or s_mean <= 1e-6:
        return {
            **market_uplift,
            "calibrated": False,
            "elasticity_beta": 1.0,
            "n_weeks": n,
        }

    x = (t_arr - t_mean) / t_mean
    y = (s_arr - s_mean) / s_mean
    denom = float(np.dot(x, x)) + 0.5
    raw_beta = float(np.dot(x, y) / denom) if denom > 1e-8 else 1.0
    beta = float(np.clip(raw_beta if raw_beta > 0 else 0.75, 0.35, 1.45))

    def _adj(u: float) -> float:
        return round(max(0.5, 1.0 + (float(u) - 1.0) * beta), 2)

    return {
        **market_uplift,
        "calibrated": True,
        "elasticity_beta": round(beta, 3),
        "n_weeks": n,
        "uplift_p10": _adj(market_uplift.get("uplift_p10", 1.0)),
        "uplift_p50": _adj(market_uplift.get("uplift_p50", 1.0)),
        "uplift_p90": _adj(market_uplift.get("uplift_p90", 1.0)),
    }
