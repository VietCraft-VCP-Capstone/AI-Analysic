import numpy as np
from sklearn.metrics import average_precision_score

from scripts.f29.train.b3_attr.helpers import delta_ci

GATE = ("cosine",)


def ap(y, s) -> float:
    return float(average_precision_score(y, s)) if np.sum(y) else float("nan")


def baseline_scores(img, txt, types, S) -> dict:
    a, b = img[S["img"]], txt[S["txt"]]
    cos = np.sum(a * b, axis=1) / np.maximum(np.linalg.norm(a, axis=1) * np.linalg.norm(b, axis=1), 1e-12)
    return {"cosine": 1 - cos}


def candidate_ap(S, cand: dict) -> dict:
    y = S["y"]
    mask = np.all([np.isfinite(v) for v in cand.values()], axis=0)
    return {k: round(ap(y[mask], v[mask]), 4) for k, v in cand.items()}


def eval_prev(S, scores: dict, chosen: str, groups: np.ndarray, t_warn: float | None) -> dict:
    y = S["y"]
    mask = np.isfinite(scores[chosen])
    yy, gg = y[mask], groups[S["txt"][mask]]
    s = {k: v[mask] for k, v in scores.items()}
    aps = {k: ap(yy, v) for k, v in s.items()}
    best = max(GATE, key=lambda k: aps[k])
    neg = yy == 0
    ok = bool(yy.sum() and neg.any())
    lo, hi = delta_ci(yy, s[chosen], s[best], gg) if ok else (float("nan"), float("nan"))
    return {"n_pos": int(yy.sum()), "n_neg": int(neg.sum()), "pr_auc": {k: round(v, 4) for k, v in aps.items()},
            "best_baseline": best, "delta_ci95": [round(lo, 4), round(hi, 4)],
            "live": bool(aps[chosen] > aps[best] and lo > 0),
            "false_alarm_clean": round(float(np.mean(s[chosen][neg] > t_warn)), 4) if ok and t_warn is not None else None,
            "n_pair_anchors": S["n_candidates"]}
