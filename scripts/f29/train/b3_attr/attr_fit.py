from collections import Counter

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score

from app.core.f29.checks.attributes import vocab

C_GRID = (0.1, 1, 10)
MIN_N = 300
MIN_CLS = 10


def labeled(rows: np.ndarray, claims: list[dict], g: str) -> tuple[np.ndarray, np.ndarray]:
    keep = [int(i) for i in rows if g in claims[i]]
    return np.array(keep, dtype=int), np.array([claims[i][g] for i in keep], dtype=object)


def _kept(idx: np.ndarray, y: np.ndarray, keep: set) -> tuple[np.ndarray, np.ndarray]:
    sel = np.array([v in keep for v in y], dtype=bool)
    return idx[sel], y[sel]


def fit_group(X_tr, y_tr, X_va, y_va) -> tuple[dict, dict]:
    fits = {C: LogisticRegression(C=C, class_weight="balanced", max_iter=1000).fit(X_tr, y_tr) for C in C_GRID}
    val_f1 = {str(C): round(float(f1_score(y_va, clf.predict(X_va), average="macro")), 4) for C, clf in fits.items()}
    best = max(C_GRID, key=lambda C: val_f1[str(C)])
    clf = fits[best]
    return {"classes": [str(c) for c in clf.classes_], "clf": clf, "C": best}, val_f1


def fit_all(img: np.ndarray, claims: list[dict], tr: np.ndarray, va: np.ndarray) -> tuple[dict, dict]:
    bundle, report = {}, {}
    for g in vocab():
        tr_idx, tr_y = labeled(tr, claims, g)
        counts = Counter(tr_y.tolist())
        keep = {c for c, n in counts.items() if n >= MIN_CLS}
        tri, ytr = _kept(tr_idx, tr_y, keep)
        vai, yva = _kept(*labeled(va, claims, g), keep)
        if len(tr_idx) < MIN_N or len(keep) < 2 or len(vai) == 0:
            report[g] = {"skip": f"{len(tr_idx)} mẫu train có nhãn, {len(keep)} lớp đủ {MIN_CLS} mẫu"}
            continue
        entry, val_f1 = fit_group(img[tri], ytr, img[vai], yva)
        bundle[g] = entry
        report[g] = {"C": entry["C"], "val_macro_f1_by_C": val_f1, "n_train": len(tri), "n_val": len(vai),
                     "classes": entry["classes"], "dropped": sorted(set(counts) - keep)}
    return bundle, report
