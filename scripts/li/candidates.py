import numpy as np
import pandas as pd
from sklearn.decomposition import PCA

from scripts.li.baselines import tfidf_model
from scripts.li.embed_cache import as_f16, features_dir
from scripts.li.fit_context import N_FOLDS, seller_folds

PCA_DIM = 16
TITLE_PCA_COLS = [f"title_pca_{i}" for i in range(PCA_DIM)]
CANDIDATES = {"text_lr": ["text_lr"], "title_pca": TITLE_PCA_COLS}


def text_lr_oof(table: pd.DataFrame) -> np.ndarray:
    train = (table["split"] == "train").to_numpy()
    seller = table["seller"].astype(object)
    folds = seller_folds(table.assign(seller=seller.where(seller.notna(), None)), train)
    titles, groups = table["title"].fillna("").astype(str).to_numpy(), table["group"].to_numpy(str)
    top, out = table["top25"].to_numpy(bool), np.full(len(table), np.nan)
    for k in [-1, *range(N_FOLDS)]:
        fit, rows = (train & (folds != k), folds == k) if k >= 0 else (train, ~train)
        for g in np.unique(groups[fit]):
            m, r = fit & (groups == g), rows & (groups == g)
            if r.any() and 0 < top[m].sum() < m.sum():
                out[r] = tfidf_model().fit(titles[m], top[m]).predict_proba(titles[r])[:, 1]
    return out


def title_pca(table: pd.DataFrame) -> np.ndarray:
    z = np.load(features_dir() / "emb.npz")
    assert np.array_equal(z["listing_id"], table["listing_id"].to_numpy())
    assert np.array_equal(z["source"], table["source"].to_numpy(str))
    txt = as_f16(z["txt"]).astype(np.float64)
    train = (table["split"] == "train").to_numpy()
    return PCA(PCA_DIM, random_state=42).fit(txt[train]).transform(txt)


def add(table: pd.DataFrame) -> pd.DataFrame:
    out = table.assign(text_lr=text_lr_oof(table))
    out[TITLE_PCA_COLS] = title_pca(table)
    return out
