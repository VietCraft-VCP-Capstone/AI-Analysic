import numpy as np
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
