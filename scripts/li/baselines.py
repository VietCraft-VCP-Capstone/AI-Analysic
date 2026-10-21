import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline

from app.core.f29.scoring import content_axis_score, content_component_scores
from app.core.listing_intel.normalize import tokens
from scripts.li.fit import fit, predict


def _val(v):
    return None if v is None or np.isnan(v) else float(v)


def random_score(train, ev):
    return np.random.default_rng(42).random(len(ev))


def health_v1(train, ev):
    parts = zip(ev["n_images"].to_numpy(float), ev["desc_len"].to_numpy(float))
    scores = [content_axis_score(content_component_scores(_val(i), _val(d), None)) for i, d in parts]
    return np.array([0.0 if s is None else s for s in scores], dtype=float)


def single(col):
    def run(train, ev):
        return predict(fit(train, [col, "group"]), ev, [col, "group"])
    return run


def tfidf_model():
    vec = TfidfVectorizer(tokenizer=tokens, ngram_range=(1, 2), min_df=3, lowercase=False, token_pattern=None)
    return make_pipeline(vec, LogisticRegression(max_iter=2000))


def tfidf_title(train, ev):
    model = tfidf_model().fit(train["title"].fillna(""), train["top25"])
    return model.predict_proba(ev["title"].fillna(""))[:, 1]


BASELINES = {
    "Ngẫu nhiên": random_score,
    "health-1.0 (ảnh ≥5, mô tả ≥150)": health_v1,
    "Chỉ giá (log_price) + nhóm": single("log_price"),
    "Chỉ số ảnh (n_images) + nhóm": single("n_images"),
    "TF-IDF tiêu đề + logistic": tfidf_title,
}


def available(table):
    return {k: f for k, f in BASELINES.items() if f is not tfidf_title or "title" in table}
