from pathlib import Path

import numpy as np
import pandas as pd
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

from app.core.f29.checks import category as cat
from scripts.f29.eval_kit import group_split, near_dup_clusters

ROOT = Path(__file__).resolve().parents[5]
DATA = ROOT / "agent-skills/ai-data-train-prod/data-li"
NPZ = DATA / "features/emb_tikifashion.npz"
PARQUET = DATA / "clean/tikifashion.parquet"


def load() -> dict:
    d = np.load(NPZ)
    labels = [cat.TREE["tikifashion"][c] for c in d["category"]]
    keep = np.array([t is not None for t in labels])
    ids = d["listing_id"][keep]
    caption = pd.read_parquet(PARQUET).set_index("listing_id")["caption"]
    return {"img": d["img"][keep], "txt": d["txt"][keep], "y": np.array([t for t in labels if t is not None]),
            "name": caption.loc[ids].to_numpy()}


def _star_edges(labels: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    _, first, inv = np.unique(labels, return_index=True, return_inverse=True)
    return np.arange(len(labels)), first[inv]


def split_indices(img: np.ndarray, txt: np.ndarray, seed: int = 0) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    n = len(img)
    edges = [_star_edges(near_dup_clusters(img, 0.95)), _star_edges(near_dup_clusters(txt, 0.999))]
    rows = np.concatenate([r for r, _ in edges])
    cols = np.concatenate([c for _, c in edges])
    graph = coo_matrix((np.ones(len(rows), dtype=np.int8), (rows, cols)), shape=(n, n))
    groups = connected_components(graph, directed=False)[1]
    return (*group_split(groups, seed=seed), groups)
