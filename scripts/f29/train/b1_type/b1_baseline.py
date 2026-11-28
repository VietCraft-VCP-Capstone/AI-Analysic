import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression

from app.core.f29.checks import category as cat


def tfidf_probs(names_tr, y_tr, names_te) -> np.ndarray:
    vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), min_df=2)
    clf = LogisticRegression(class_weight="balanced", max_iter=3000).fit(vec.fit_transform(names_tr), y_tr)
    P = np.zeros((len(names_te), len(cat.TYPES)))
    P[:, [cat.TYPES.index(c) for c in clf.classes_]] = clf.predict_proba(vec.transform(names_te))
    return P
