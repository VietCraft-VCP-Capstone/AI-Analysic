from typing import Any, Dict, Set, Tuple

from app.core.f29.factors import KEYS, LABELS


def build(subs: Dict[str, float], values: Dict[str, Any], targets: Dict[str, Any],
          peers: Dict[str, Any], missing: Set[str], weights: Dict[str, int],
          extra: Dict[str, Dict[str, Any]]) -> Tuple[list, float]:
    rows = []
    for key in KEYS:
        sub = subs[key]
        rows.append({
            "key": key, "label": LABELS[key], "weight": weights[key],
            "sub_score": round(sub, 1), "points": round(weights[key] * sub / 100, 1),
            "value": values.get(key), "target": targets.get(key), "peer_median": peers.get(key),
            "missing": key in missing, **extra.get(key, {}),
        })
    return rows, round(sum(r["points"] for r in rows), 1)
