import numpy as np
import pandas as pd
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

from scripts.f29.eval_kit import near_dup_clusters


def _seller_codes(seller: np.ndarray) -> np.ndarray:
    codes = pd.factorize(pd.Series(seller, dtype=object))[0]
    n = len(codes)
    return np.where(codes < 0, n + np.arange(n), codes)


def _components(partitions: list[np.ndarray]) -> np.ndarray:
    n = len(partitions[0])
    rows, cols = [], []
    for lab in partitions:
        _, first, inv = np.unique(lab, return_index=True, return_inverse=True)
        rows.append(np.arange(n))
        cols.append(first[inv])
    r, c = np.concatenate(rows), np.concatenate(cols)
    g = coo_matrix((np.ones(len(r), dtype=np.int8), (r, c)), shape=(n, n))
    return connected_components(g, directed=False)[1]


def group_ids(seller: np.ndarray, img: np.ndarray, txt: np.ndarray) -> np.ndarray:
    return _components([_seller_codes(seller), near_dup_clusters(img, 0.95), near_dup_clusters(txt, 0.999)])
