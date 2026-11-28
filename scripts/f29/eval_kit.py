import math

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.stats import binomtest
from sklearn.metrics import average_precision_score, roc_auc_score


def top_hit_rate(y, s, frac=0.2):
    k = max(1, int(len(s) * frac))
    return float(y[np.argsort(-s, kind="stable")[:k]].mean())


def within_category_auc(y, s, cat, min_n=30):
    aucs, sizes = [], []
    for c in np.unique(cat):
        m = cat == c
        if m.sum() >= min_n and 0 < y[m].sum() < m.sum():
            aucs.append(roc_auc_score(y[m], s[m]))
            sizes.append(m.sum())
    return float(np.average(aucs, weights=sizes)) if aucs else float("nan")


def _resamples(groups, n=200, seed=42):
    _, inv = np.unique(np.asarray(groups, dtype=str), return_inverse=True)
    members = np.split(np.argsort(inv, kind="stable"), np.cumsum(np.bincount(inv))[:-1])
    rng = np.random.default_rng(seed)
    for _ in range(n):
        yield np.concatenate([members[j] for j in rng.integers(0, len(members), len(members))])


def _ci(vals):
    return [round(float(v), 3) for v in np.percentile(vals, [2.5, 97.5])]


def auc_ci(y, s, groups):
    return _ci([roc_auc_score(y[i], s[i]) for i in _resamples(groups) if 0 < y[i].sum() < len(i)])


def delta_ci(y, a, b, groups):
    y, a, b = np.asarray(y), np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    return _ci([roc_auc_score(y[i], a[i]) - roc_auc_score(y[i], b[i])
                for i in _resamples(groups) if 0 < y[i].sum() < len(i)])


def score_all(y, s, cat, groups):
    y, s, cat = np.asarray(y), np.asarray(s, dtype=float), np.asarray(cat, dtype=str)
    return {
        "roc_auc": round(float(roc_auc_score(y, s)), 3),
        "auc_ci95": auc_ci(y, s, groups),
        "pr_auc": round(float(average_precision_score(y, s)), 3),
        "within_cat_auc": round(within_category_auc(y, s, cat), 3),
        "top20_hit": round(top_hit_rate(y, s), 3),
        "base_rate": round(float(y.mean()), 3),
    }


def group_split(groups: np.ndarray, seed: int = 0, frac=(0.7, 0.15, 0.15)) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    _, inv = np.unique(np.asarray(groups, dtype=str), return_inverse=True)
    order = np.random.default_rng(seed).permutation(inv.max() + 1)
    sizes = np.bincount(inv)[order]
    pos = (np.cumsum(sizes) - sizes / 2) / sizes.sum()
    part = np.empty(len(order), dtype=int)
    part[order] = np.searchsorted(np.cumsum(frac)[:-1], pos)
    return tuple(np.flatnonzero(part[inv] == k) for k in range(len(frac)))


def near_dup_clusters(X: np.ndarray, thr: float = 0.95) -> np.ndarray:
    X = np.asarray(X, dtype=np.float32)
    X = X / np.maximum(np.linalg.norm(X, axis=1, keepdims=True), 1e-12)
    n, rows, cols = len(X), [], []
    for s in range(0, n, 1024):
        r, c = np.nonzero(X[s:s + 1024] @ X.T > thr)
        keep = r + s < c
        rows.append(r[keep] + s)
        cols.append(c[keep])
    rows, cols = np.concatenate(rows), np.concatenate(cols)
    g = coo_matrix((np.ones(len(rows), dtype=np.int8), (rows, cols)), shape=(n, n))
    return connected_components(g, directed=False)[1]


def bootstrap_ci(metric, y, s, groups, n: int = 1000, seed: int = 0) -> tuple[float, float, float]:
    y, s = np.asarray(y), np.asarray(s, dtype=float)
    vals = [metric(y[i], s[i]) for i in _resamples(groups, n, seed) if 0 < y[i].sum() < len(i)]
    lo, hi = np.percentile(vals, [2.5, 97.5])
    return float(metric(y, s)), float(lo), float(hi)


def mcnemar(a_ok: np.ndarray, b_ok: np.ndarray) -> float:
    a_ok, b_ok = np.asarray(a_ok, dtype=bool), np.asarray(b_ok, dtype=bool)
    b, c = int((a_ok & ~b_ok).sum()), int((~a_ok & b_ok).sum())
    if b + c == 0:
        return 1.0
    return float(min(1.0, 2 * binomtest(min(b, c), b + c, 0.5, alternative="less").pvalue))


def holm(p: list[float]) -> list[float]:
    p = np.asarray(p, dtype=float)
    m, order = len(p), np.argsort(p)
    adj = np.empty(m)
    adj[order] = np.minimum(1.0, np.maximum.accumulate((m - np.arange(m)) * p[order]))
    return adj.tolist()


def conformal_threshold(clean_scores: np.ndarray, alpha: float) -> float:
    s = np.sort(np.asarray(clean_scores, dtype=float))
    k = math.ceil(round((len(s) + 1) * (1 - alpha), 9))
    return float(s[k - 1]) if k <= len(s) else float("inf")


def md_table(rows: list[dict], cols: list[str]) -> str:
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    lines += ["| " + " | ".join(str(r.get(c, "")).replace("|", "\\|") for c in cols) + " |" for r in rows]
    return "\n".join(lines)
