import numpy as np
from sklearn.metrics import f1_score

from app.core.f29.checks.attributes import method_probs, zs_probs
from scripts.f29.train.b3_attr.attr_fit import labeled
from scripts.f29.eval_kit import mcnemar


def cls_metrics(entry: dict, V: np.ndarray, img: np.ndarray, claims: list[dict], rows: np.ndarray, g: str,
                method: str) -> dict:
    classes = np.array(entry["classes"], dtype=object)
    idx, y = labeled(rows, claims, g)
    sel = np.isin(y, classes)
    idx, y = idx[sel], y[sel]
    if len(idx) == 0:
        return {"n": 0}
    pred = classes[method_probs(method, entry, V, img[idx]).argmax(axis=1)]
    zpred = classes[zs_probs(V, img[idx]).argmax(axis=1)]
    ok, zok = pred == y, zpred == y
    return {"method": method, "n": int(len(y)), "macro_f1": round(float(f1_score(y, pred, average="macro")), 4),
            "macro_f1_zero_shot": round(float(f1_score(y, zpred, average="macro")), 4),
            "acc": round(float(ok.mean()), 4), "acc_zero_shot": round(float(zok.mean()), 4),
            "mcnemar_p_vs_zero_shot": round(mcnemar(ok, zok), 4)}
