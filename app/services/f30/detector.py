from datetime import date

import numpy as np
from scipy.stats import nbinom, norm, poisson

from app.core.calendar_vn import is_vn_holiday
from app.services.f30.rules import MAX_ZERO_RUN, WINDOW, Z_THRESHOLD, passes_gates


def baseline(hist: np.ndarray, hist_dow: np.ndarray, dow_t: int) -> tuple[float, float]:
    m = float(np.mean(hist))
    if m <= 0:
        return 0.0, 0.0
    same = hist[hist_dow == dow_t]
    f = (same.sum() + 2 * m) / (len(same) * m + 2 * m)
    mu = m * f
    k_inv = max(0.0, (float(np.var(hist, ddof=1)) - m) / (m * m))
    return mu, mu + k_inv * mu * mu


def _dist(mu: float, var: float):
    if var <= mu * 1.0001:
        return poisson(mu)
    n = mu * mu / (var - mu)
    return nbinom(n, n / (n + mu))


def pit_z(y: float, mu: float, var: float) -> float:
    if mu <= 0:
        return 0.0
    k = round(y)
    dist = _dist(mu, var)
    u = dist.cdf(k - 1) + 0.5 * dist.pmf(k)
    return float(norm.ppf(np.clip(u, 1e-9, 1 - 1e-9)))


def zero_run_z(series: np.ndarray, dows: np.ndarray, t: int) -> tuple[float, int, float]:
    run = 0
    while run < MAX_ZERO_RUN and t - run >= 0 and series[t - run] == 0:
        run += 1
    end = t - run
    if run < 2 or end - WINDOW + 1 < 0:
        return 0.0, run, 0.0
    hist = series[end - WINDOW + 1:end + 1]
    hist_dow = dows[end - WINDOW + 1:end + 1]
    p_all, mu_sum = 1.0, 0.0
    for i in range(end + 1, t + 1):
        mu, var = baseline(hist, hist_dow, dows[i])
        mu_sum += mu
        if mu > 0:
            p_all *= _dist(mu, var).pmf(0)
    if mu_sum <= 0:
        return 0.0, run, 0.0
    return float(norm.ppf(max(p_all, 1e-12))), run, mu_sum


def _severity(abs_z: float) -> str:
    if abs_z >= 4:
        return "high"
    return "medium" if abs_z >= 3 else "low"


def detect_day(series, dates: list[str], t: int, metric: str, scale: float = 1.0) -> dict | None:
    if t < WINDOW:
        return None
    s = np.asarray(series, dtype=float) / scale
    dows = np.array([date.fromisoformat(d).weekday() for d in dates])
    y = s[t]
    mu, var = baseline(s[t - WINDOW:t], dows[t - WINDOW:t], dows[t])
    z, rule, expected = pit_z(y, mu, var), "daily", mu
    if y == 0:
        z_run, _, mu_run = zero_run_z(s, dows, t)
        if z_run < z:
            z, rule, expected = z_run, "zero_run", mu_run
    if abs(z) <= Z_THRESHOLD:
        return None
    direction = "spike" if z > 0 else "drop"
    expected_vnd, actual_vnd = expected * scale, y * scale
    if not passes_gates(metric, direction, expected, y, expected_vnd, actual_vnd):
        return None
    return {
        "date": dates[t],
        "metric": metric,
        "direction": direction,
        "rule": rule,
        "z": round(z, 2),
        "expected": int(round(expected_vnd)),
        "actual": int(round(actual_vnd)),
        "change_pct": round((y - expected) / expected * 100, 1) if expected > 0 else None,
        "severity": _severity(abs(z)),
        "calendar_sensitive": is_vn_holiday(dates[t]),
    }
