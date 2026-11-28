import numpy as np
from sklearn.metrics import f1_score

from app.core.f29.checks import category as cat
from scripts.f29.eval_kit import _resamples, holm, mcnemar

NAMES = np.array(cat.TYPES)
CMP = ("img", "txt", "probe", "zeroshot", "tfidf")


def macro_f1(y, pred) -> float:
    return float(f1_score(y, pred, labels=np.unique(y), average="macro", zero_division=0))


def cluster_ci(fn, groups, n: int = 1000) -> list[float]:
    vals = [fn(i) for i in _resamples(groups, n, seed=0)]
    return [round(float(v), 4) for v in np.percentile(vals, [2.5, 97.5])]


def scores(P, y, groups) -> dict:
    pred, hit = NAMES[P.argmax(1)], NAMES[P.argmax(1)] == y
    top = NAMES[np.argsort(-P, axis=1)[:, :3]]
    return {"macro_f1": round(macro_f1(y, pred), 4),
            "macro_f1_ci95": cluster_ci(lambda i: macro_f1(y[i], pred[i]), groups),
            "top1": round(float(hit.mean()), 4), "top1_ci95": cluster_ci(lambda i: hit[i].mean(), groups),
            "top3": round(float((top == y[:, None]).any(1).mean()), 4)}


def compare(hit: dict, groups) -> dict:
    fused, out = hit["fused"], {}
    for k in (c for c in CMP if c in hit):
        d = fused.astype(float) - hit[k].astype(float)
        out[k] = {"delta_top1": round(float(d.mean()), 4), "delta_ci95": cluster_ci(lambda i: d[i].mean(), groups),
                  "mcnemar_p": mcnemar(fused, hit[k])}
    for v, adj in zip(out.values(), holm([v["mcnemar_p"] for v in out.values()])):
        v["holm_p"] = adj
    return out


def reject(P, y, tau) -> dict:
    ans, pred = P.max(1) >= tau, NAMES[P.argmax(1)]
    if not ans.any():
        return {"rate": 1.0, "acc_answered": None, "macro_f1_answered": None}
    return {"rate": round(float(1 - ans.mean()), 4),
            "acc_answered": round(float((pred[ans] == y[ans]).mean()), 4),
            "macro_f1_answered": round(macro_f1(y[ans], pred[ans]), 4)}
