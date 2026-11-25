import math
from typing import Any, Dict, List

from app.core.f29.score import scoring
from app.core.f29.score.recommend import METHOD_RANK

STATES = ("scored", "seller_missing", "not_applicable")


def _bad_numbers(obj: Any, path: str = "") -> List[str]:
    if isinstance(obj, float) and not math.isfinite(obj):
        return [f"{path or 'root'} is {obj}"]
    if isinstance(obj, dict):
        return [p for k, v in obj.items() for p in _bad_numbers(v, f"{path}.{k}")]
    if isinstance(obj, list):
        return [p for i, v in enumerate(obj) for p in _bad_numbers(v, f"{path}[{i}]")]
    return []


def _in_range(name: str, value: Any, lo: float, hi: float) -> List[str]:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
        return [f"{name} not a finite number: {value!r}"]
    return [] if lo <= value <= hi else [f"{name}={value} outside [{lo}, {hi}]"]


def _rec_key(r: Dict[str, Any]) -> tuple:
    return (r["kind"] != "blocker", "check" not in (r.get("evidence") or {}),
            -r["gain_points"] / (r.get("effort") or 1), METHOD_RANK.get(r["method"], 99))


def _check_factor(f: Dict[str, Any], weights: Dict[str, float]) -> List[str]:
    miss = [k for k in ("key", "state", "weight", "points") if k not in f]
    if miss:
        return [f"factor {f.get('key')} missing {miss}"]
    key, out = f["key"], []
    if key in weights and abs(f["weight"] - weights[key]) > 1e-9:
        out.append(f"{key} weight {f['weight']} != configured {weights[key]}")
    out += _in_range(f"{key} points", f["points"], 0, f["weight"] + 0.06)
    if f["state"] not in STATES:
        out.append(f"{key} state {f['state']!r} unknown")
    sub = f.get("sub_score")
    if sub is not None:
        out += _in_range(f"{key} sub_score", sub, 0, 100)
    if f["state"] == "scored" and sub is None:
        out.append(f"{key} sub_score is None but state is scored")
    if f["state"] == "scored" and sub is not None and abs(f["points"] - f["weight"] * sub / 100) > 0.07:
        out.append(f"{key} points {f['points']} != weight*sub_score/100")
    if f["state"] == "seller_missing" and f["points"] != 0:
        out.append(f"{key} seller_missing has points {f['points']}")
    if f["state"] == "not_applicable" and (f["points"] != 0 or sub is not None):
        out.append(f"{key} state not_applicable has points {f['points']} sub_score {sub}")
    return out


def _check_score(r: Dict[str, Any]) -> List[str]:
    out = _in_range("score", r.get("score"), 0, 100)
    if not out and r.get("status") != scoring.status_from_score(r["score"]):
        out.append(f"status {r.get('status')} != {scoring.status_from_score(r['score'])} for score {r['score']}")
    return out


def _check_recs(recs: List[Dict[str, Any]]) -> List[str]:
    out = []
    for i, r in enumerate(recs):
        out += _in_range(f"recommendation[{i}] gain_points", r.get("gain_points"), 0, 100)
        if not all(k in r for k in ("kind", "method")):
            out.append(f"recommendation[{i}] missing kind/method")
    if out:
        return out
    keys = [_rec_key(r) for r in recs]
    return ["recommendations not sorted blockers first then by gain/effort"] if any(
        a > b for a, b in zip(keys, keys[1:])) else []


def check_health(result: Dict[str, Any], weights: Dict[str, float]) -> List[str]:
    out = _bad_numbers(result) + _check_score(result)
    factors = result.get("factors") or []
    if not factors:
        return out + ["no factors"]
    for f in factors:
        out += _check_factor(f, weights)
    if {f.get("key") for f in factors} != set(weights):
        out.append(f"factor keys {sorted(str(f.get('key')) for f in factors)} != configured {sorted(weights)}")
    if out:
        return out
    counted = [f for f in factors if f["state"] in scoring.COUNTED]
    budget = sum(f["weight"] for f in counted)
    expect = round(sum(f["points"] for f in counted) * 100 / budget, 1) if budget else 0.0
    if abs(expect - result["score"]) > 0.5:
        out.append(f"score {result['score']} != points-weighted {expect}")
    if result.get("coverage") != {"evaluated": len(counted), "total": len(factors)}:
        out.append(f"coverage {result.get('coverage')} != {len(counted)}/{len(factors)}")
    conf = result.get("confidence") or {}
    want = scoring.confidence(factors, conf.get("peers", 0))
    if conf != want:
        out.append(f"confidence {conf} != recomputed {want}")
    return out + _check_recs(result.get("recommendations") or [])


def check_preview(result: Dict[str, Any], empty: bool = False) -> List[str]:
    miss = [k for k in ("score", "current_score", "delta_vs_current") if k not in result]
    if miss:
        return [f"preview missing {miss}"]
    out = _bad_numbers(result) + _check_score(result)
    if out:
        return out
    if abs(result["score"] - result["current_score"] - result["delta_vs_current"]) > 0.11:
        out.append(f"delta_vs_current {result['delta_vs_current']} != score - current_score")
    if empty and abs(result["delta_vs_current"]) > 0.11:
        out.append(f"empty body changed the score by {result['delta_vs_current']}")
    return out
