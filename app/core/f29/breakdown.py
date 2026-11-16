from typing import Any, Dict, Set, Tuple

from app.core.f29.factors import KEYS, LABELS


def score_of(rows: list) -> float:
    scored = [r for r in rows if r.get("scored", True)]
    total = sum(r["weight"] for r in scored)
    return round(sum(r["points"] for r in scored) * 100 / total, 1) if total else 0.0


def build(subs: Dict[str, float], values: Dict[str, Any], targets: Dict[str, Any],
          peers: Dict[str, Any], missing: Set[str], weights: Dict[str, int],
          extra: Dict[str, Dict[str, Any]], unscored: Set[str] = frozenset()) -> Tuple[list, float]:
    rows = []
    for key in KEYS:
        scored = key not in unscored
        sub = subs[key]
        rows.append({
            "key": key, "label": LABELS[key], "weight": weights[key], "scored": scored,
            "sub_score": round(sub, 1) if scored else None,
            "points": round(weights[key] * sub / 100, 1) if scored else 0.0,
            "value": values.get(key), "target": targets.get(key), "peer_median": peers.get(key),
            "missing": key in missing, **extra.get(key, {}),
        })
    return rows, score_of(rows)
