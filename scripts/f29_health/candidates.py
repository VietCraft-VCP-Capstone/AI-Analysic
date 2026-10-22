import numpy as np

from app.core.f29 import factors
from app.core.f29.scoring import content_axis_score, content_component_scores
from scripts.f29_ml import baselines, evaluate, models
from scripts.f29_ml.evaluate import delta_ci
from scripts.li import measure

LEARNED = "Học (health-2.0)"
EQUAL = "Chia đều"
V1 = "health-1.0 (luật hiện tại)"
BOOST = "HistGB trên điểm con"
RANDOM = "Ngẫu nhiên"
RECENCY = "Đơn gần nhất"


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


def tiki(train_sub, train_y, sub, df, weights):
    v1 = [content_axis_score(content_component_scores(n, d, None)) for n, d in zip(df["n_images"], df["desc_len"])]
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


def gate(df, scores):
    y, groups = df["top25"].to_numpy(), measure.sellers(df)
    vs_equal = delta_ci(y, scores[LEARNED], scores[EQUAL], groups)
    vs_v1 = delta_ci(y, scores[LEARNED], scores[V1], groups)
    return {"vs_equal_ci": vs_equal, "vs_v1_ci": vs_v1, "passed": vs_equal[1] >= 0 and vs_v1[1] >= 0}
