import json
import re
from functools import lru_cache

import numpy as np

from app.core.f29.paths import DATA
from app.core.f29.score.text_rules import norm as _norm


VOCAB_PATH = DATA / "attributes.json"
NEGATIONS = ("không phải", "không có")
CLAUSE_END = re.compile(r"[.,;!?\n]")


def norm(text: str) -> str:
    return _norm(text).replace("ð", "đ")


@lru_cache(maxsize=1)
def vocab() -> dict:
    return json.loads(VOCAB_PATH.read_text("utf-8"))


@lru_cache(maxsize=1)
def _compiled() -> dict:
    return {g: {v: re.compile("|".join(f"(?:{p})" for p in pats)) for v, pats in spec["values"].items()}
            for g, spec in vocab().items()}


def _negated(text: str, start: int) -> bool:
    clause = CLAUSE_END.split(text[:start])[-1][-20:]
    return any(n in clause for n in NEGATIONS)


def _hits(text: str, group: str) -> set[str]:
    return {v for v, rx in _compiled()[group].items()
            if any(not _negated(text, m.start()) for m in rx.finditer(text))}


def applies(group: str, vtype: str | None) -> bool:
    scope = vocab()[group]["applies_to"]
    return "*" in scope or vtype in scope


def claims(text: str, vtype: str | None = None) -> dict[str, str]:
    text = norm(text)
    out = {}
    for group in vocab():
        hit = _hits(text, group) if applies(group, vtype) else set()
        if len(hit) == 1:
            out[group] = hit.pop()
    return out


def conflicts(group: str, value: str) -> list[str]:
    spec = vocab()[group]
    if spec.get("exclusive"):
        return [v for v in spec["values"] if v != value]
    return spec.get("conflicts", {}).get(value, [])


EPS = 1e-12
TEMP = 100.0


def probe_probs(entry: dict, img: np.ndarray) -> np.ndarray:
    return entry["clf"].predict_proba(np.asarray(img, dtype=np.float32).reshape(len(img), -1))


def zs_probs(V: np.ndarray, img: np.ndarray) -> np.ndarray:
    X = img / np.maximum(np.linalg.norm(img, axis=1, keepdims=True), EPS)
    z = TEMP * X @ V.T
    e = np.exp(z - z.max(axis=1, keepdims=True))
    return e / e.sum(axis=1, keepdims=True)


def method_probs(method: str, entry: dict, V: np.ndarray | None, img: np.ndarray) -> np.ndarray:
    if method == "probe":
        return probe_probs(entry, img)
    zs = zs_probs(V, np.asarray(img, dtype=np.float32).reshape(len(img), -1))
    if method == "zero_shot":
        return zs
    return (probe_probs(entry, img) + zs) / 2
