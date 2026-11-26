import numpy as np

from app.core.f29.checks.attributes import EPS
from app.core.f29.checks.attributes import vocab
from app.core.f29.shared import embedder


def class_matrix(group: str, classes: list[str]) -> np.ndarray:
    prompts = [(v, p) for v in classes for p in vocab()[group]["prompts"][v]]
    E = embedder.embed_texts([p for _, p in prompts])
    E = E / np.maximum(np.linalg.norm(E, axis=1, keepdims=True), EPS)
    V = np.stack([E[[i for i, (u, _) in enumerate(prompts) if u == v]].mean(axis=0) for v in classes])
    return V / np.maximum(np.linalg.norm(V, axis=1, keepdims=True), EPS)
