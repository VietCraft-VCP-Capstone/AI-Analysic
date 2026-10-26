import numpy as np

from app.core.f29 import factors
from app.core.f29.constants import MODEL_VERSION
from scripts.f29_ml import baselines, evaluate, models
from scripts.f29_health import evidence
from scripts.f29_ml.evaluate import delta_ci
from scripts.li import measure

LEARNED = f"Học ({MODEL_VERSION})"
EQUAL = "Chia đều"
V1 = "health-1.0 (luật hiện tại)"
BOOST = "HistGB trên điểm con"
RANDOM = "Ngẫu nhiên"
RECENCY = "Đơn gần nhất"
MARKETS = ("olist_test", "tiki_test", "shopee_test")
CI_MARKETS = ("tiki_test", "shopee_test")
LIFT_MIN = 1.2


def _linear(sub, weights):
    return sub.to_numpy() @ np.array([weights[k] for k in sub.columns], dtype=float)


def _boost(train_sub, train_y, sub):
    return models.boosting().fit(train_sub, train_y).predict_proba(sub)[:, 1]


def _single(sub):
    return {f"Chỉ {factors.LABELS[k].lower()}": sub[k].to_numpy() for k in sub.columns}


def olist(train_sub, train_y, sub, df, weights):
    out = {
        LEARNED: _linear(sub, weights),
        EQUAL: sub.mean(axis=1).to_numpy(),
        V1: baselines.health_v1(df),
        RECENCY: baselines.recency(df),
        RANDOM: baselines.random_score(df),
        BOOST: _boost(train_sub, train_y, sub),
    }
    return out | _single(sub)


def _v1_c(n, d):
    comps = [min(100.0, max(0.0, float(n) / 5.0 * 100.0))] if n is not None and not (isinstance(n, float) and np.isnan(n)) else []
    if d is not None and not (isinstance(d, float) and np.isnan(d)):
        comps.append(min(100.0, max(0.0, float(d) / 150.0 * 100.0)))
    return sum(comps) / len(comps) if comps else 0.0


def tiki(train_sub, train_y, sub, df, weights):
    v1 = [_v1_c(n, d) for n, d in zip(df["n_images"], df["desc_len"])]
    out = {
        LEARNED: _linear(sub, weights),
        EQUAL: sub.mean(axis=1).to_numpy(),
        V1: np.array(v1, dtype=float),
        RANDOM: baselines.random_score(df),
        BOOST: _boost(train_sub, train_y, sub),
    }
    return out | _single(sub)


def _auc(d):
    return {"roc_auc": d["roc_auc"], "auc_ci95": d["auc_ci95"]}


def olist_metrics(df, scores):
    return {n: _auc(evaluate.score_all(df["top25"], s, df["category"], df["seller_id"])) for n, s in scores.items()}


def tiki_metrics(df, scores):
    return {n: _auc(measure.measure(df, s)) for n, s in scores.items()}


def _market(df, scores, ci):
    y = df["top25"].to_numpy()
    out = {"lift": evidence.lift(y, scores[LEARNED])}
    if ci:
        out["vs_equal_ci"] = delta_ci(y, scores[LEARNED], scores[EQUAL], measure.sellers(df))
    return out


def gate(sets):
    per = {m: _market(*sets[m], m in CI_MARKETS) for m in MARKETS}
    ci_ok = all(per[m]["vs_equal_ci"][1] >= 0 for m in CI_MARKETS)
    lift_ok = all(per[m]["lift"] >= LIFT_MIN for m in MARKETS)
    return {"per_market": per, "passed": ci_ok and lift_ok}
