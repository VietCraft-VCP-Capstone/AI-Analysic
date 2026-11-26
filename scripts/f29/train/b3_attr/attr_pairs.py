from collections import defaultdict

import numpy as np

from app.core.f29.checks.attributes import conflicts

PER_ANCHOR = 3


def _agrees(ca: dict, cb: dict, g: str) -> bool:
    return all(ca[h] == cb[h] for h in ca.keys() & cb.keys() if h != g)


def _candidates(a: int, claims: list[dict], index: dict, types: np.ndarray, only: str | None) -> list[tuple]:
    out = {}
    for g, v in claims[a].items():
        if only and g != only:
            continue
        for c in conflicts(g, v):
            for b in index.get((types[a], g, c), []):
                if b != a and b not in out and _agrees(claims[a], claims[b], g):
                    out[b] = g
    return list(out.items())


def pool(rows: np.ndarray, claims: list[dict], types: np.ndarray, rng, only: str | None = None) -> list[tuple]:
    index = defaultdict(list)
    for i in rows:
        for g, v in claims[i].items():
            index[(types[i], g, v)].append(int(i))
    out = []
    for a in rng.permutation(rows):
        a = int(a)
        if not claims[a]:
            continue
        cands = _candidates(a, claims, index, types, only)
        for k in rng.permutation(len(cands))[:PER_ANCHOR]:
            b, g = cands[k]
            out.append((a, b, g))
    return out


def make_set(rows: np.ndarray, claims: list[dict], types: np.ndarray, prev: float, seed: int,
             group: str | None = None) -> dict:
    rng = np.random.default_rng(seed)
    base = [int(i) for i in rows if (group in claims[i] if group else claims[i])]
    n_pos = round(prev * len(base) / (1 - prev))
    cands = pool(np.asarray(rows, dtype=int), claims, types, rng, group)
    picks = [cands[k] for k in rng.permutation(len(cands))[:n_pos]]
    img = base + [b for _, b, _ in picks]
    txt = base + [a for a, _, _ in picks]
    y = [0] * len(base) + [1] * len(picks)
    attr = [""] * len(base) + [g for _, _, g in picks]
    return {"img": np.array(img, dtype=int), "txt": np.array(txt, dtype=int), "y": np.array(y, dtype=int),
            "attr": np.array(attr, dtype=object), "n_candidates": len({a for a, _, _ in cands}),
            "n_pool": len(cands)}
