from datetime import date, timedelta

import numpy as np

from app.services.f30.detector import baseline, detect_day, pit_z

START = date(2025, 1, 1)
N = 400
DATES = [(START + timedelta(days=i)).isoformat() for i in range(N)]
DOWS = np.array([date.fromisoformat(d).weekday() for d in DATES])


def _alarm_rate(series: np.ndarray) -> float:
    hits = []
    for t in range(28, N):
        mu, var = baseline(series[t - 28:t], DOWS[t - 28:t], DOWS[t])
        hits.append(abs(pit_z(series[t], mu, var)) > 2.0)
    return float(np.mean(hits))


def test_poisson_false_alarm_rate():
    rates = [_alarm_rate(np.random.default_rng(s).poisson(20, N).astype(float)) for s in range(5)]
    assert 0.03 <= np.mean(rates) <= 0.07


def test_negbin_false_alarm_rate():
    rates = [
        _alarm_rate(np.random.default_rng(s).negative_binomial(5, 5 / 25, N).astype(float))
        for s in range(5)
    ]
    assert 0.03 <= np.mean(rates) <= 0.07


def test_spike_detected():
    s = np.random.default_rng(0).poisson(20, N).astype(float)
    s[-1] = 60
    hit = detect_day(s, DATES, N - 1, "views")
    assert hit is not None and hit["direction"] == "spike"


def test_views_drop_detected():
    s = np.random.default_rng(1).poisson(40, N).astype(float)
    s[-1] = 20
    hit = detect_day(s, DATES, N - 1, "views")
    assert hit is not None and hit["direction"] == "drop"


def test_revenue_zero_run_detected():
    orders = np.random.default_rng(2).poisson(3, N).astype(float)
    orders[-7:] = 0
    revenue = orders * 200_000
    hit = detect_day(revenue, DATES, N - 1, "revenue", scale=200_000)
    assert hit is not None and hit["rule"] == "zero_run"


def test_small_change_rejected_by_pct_gate():
    s = np.full(N, 10_000.0)
    s[-1] = 8_500
    assert detect_day(s, DATES, N - 1, "views") is None
