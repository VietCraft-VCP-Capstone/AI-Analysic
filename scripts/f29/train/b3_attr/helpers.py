import numpy as np
from sklearn.metrics import average_precision_score

from app.core.f29.checks.attributes import conflicts

METHODS = ("probe", "zero_shot", "blend")


def conflict_matrix(group: str, classes: list[str]) -> np.ndarray:
    pos = {v: i for i, v in enumerate(classes)}
    M = np.zeros((len(classes), len(classes)), dtype=bool)
    for v in classes:
        for c in conflicts(group, v):
            if c in pos:
                M[pos[v], pos[c]] = True
    return M


def gaps(P: np.ndarray, idx: np.ndarray, M: np.ndarray) -> np.ndarray:
    ok = idx >= 0
    safe = np.where(ok, idx, 0)
    rival = np.where(M[safe], P, -np.inf).max(axis=1)
    out = rival - P[np.arange(len(P)), safe]
    return np.where(ok & np.isfinite(rival), out, np.nan)


def max_gap(P: dict, idx: dict, M: dict, img_rows: np.ndarray, txt_rows: np.ndarray) -> np.ndarray:
    G = np.column_stack([gaps(P[g][img_rows], idx[g][txt_rows], M[g]) for g in P])
    s = np.where(np.isnan(G), -np.inf, G).max(axis=1)
    return np.where(np.isfinite(s), s, np.nan)


def ap(y, s) -> float:
    return float(average_precision_score(y, s)) if np.sum(y) else float("nan")


def delta_ci(y, a, b, groups, n=1000, seed=0) -> list[float]:
    rng = np.random.default_rng(seed)
    _, inv = np.unique(groups, return_inverse=True)
    members = np.split(np.argsort(inv, kind="stable"), np.cumsum(np.bincount(inv))[:-1])
    diffs = []
    for _ in range(n):
        idx = np.concatenate([members[j] for j in rng.integers(0, len(members), len(members))])
        if 0 < y[idx].sum() < len(idx):
            diffs.append(ap(y[idx], a[idx]) - ap(y[idx], b[idx]))
    return [round(float(v), 4) for v in np.percentile(diffs, [2.5, 97.5])]
