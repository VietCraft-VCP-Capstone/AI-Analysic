import numpy as np

from app.core.f29.checks import category as cat
from app.core.f29.checks.attributes import claims


def predict_types(img: np.ndarray, txt: np.ndarray) -> np.ndarray:
    P = cat.probs(cat._model(), img, txt)
    return np.array(cat.TYPES)[P.argmax(axis=1)]


def row_claims(texts: np.ndarray, types: np.ndarray) -> list[dict]:
    return [claims(str(t), str(ty)) for t, ty in zip(texts, types)]


def claim_index(rows_claims: list[dict], classes: dict[str, list[str]]) -> dict[str, np.ndarray]:
    out = {}
    for g, cls in classes.items():
        pos = {v: i for i, v in enumerate(cls)}
        out[g] = np.array([pos.get(c.get(g), -1) for c in rows_claims], dtype=int)
    return out
