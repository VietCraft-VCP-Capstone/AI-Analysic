import math
from bisect import bisect_left, bisect_right
from typing import Any, Dict, List

from app.core.f29.constants import review_score

COUNTED = ("scored", "seller_missing")
ZERO_KEYS = ("image", "description", "tags")


def band(score: float) -> str:
    return "good" if score >= 80 else "needs_improvement" if score >= 50 else "poor"


def pct(value: float, peers: List[float]) -> float:
    a = sorted(peers)
    return 100 * (bisect_left(a, value) + bisect_right(a, value)) / (2 * len(a)) if a else 50.0


def _finite(x: Any) -> bool:
    return isinstance(x, (int, float)) and math.isfinite(x)


def _row_problems(f: Dict[str, Any]) -> List[str]:
    key, ev, sub = f["key"], f["evidence"], f["sub_score"]
    if f["state"] not in COUNTED:
        return [f"{key}: uncounted row has points {f['points']}"] if f["points"] else []
    if not _finite(sub):
        return [f"{key}: counted row without sub_score"]
    out = []
    if f["state"] == "seller_missing" and sub != 0:
        out.append(f"{key}: seller_missing sub {sub}")
    if abs(f["points"] - f["weight"] * sub / 100) > 0.06:
        out.append(f"{key}: points {f['points']} != weight*sub {f['weight'] * sub / 100:.2f}")
    if "peers" in ev:
        value = review_score(ev["good"], ev["total"], ev["p0"], ev["m"]) if key == "review" and "p0" in ev else ev.get("value")
        want = 100 - ev["pct"] if key == "price" else (
            0.0 if key in ZERO_KEYS and not value else pct(value, ev["peers"]))
        if abs(sub - want) > 0.1:
            out.append(f"{key}: sub {sub} != recomputed {want:.1f}")
    return out


def recompute(r: Dict[str, Any]) -> List[str]:
    rows = r["factors"]
    counted = [f for f in rows if f["state"] in COUNTED]
    out = [p for f in rows for p in _row_problems(f)]
    budget = sum(f["weight"] for f in counted)
    want = sum(f["weight"] * (f["sub_score"] or 0) for f in counted) / budget if budget else 0.0
    if not _finite(r["score"]) or not 0 <= r["score"] <= 100:
        out.append(f"score out of range: {r['score']}")
    elif abs(r["score"] - want) > 0.5:
        out.append(f"score {r['score']} != recomputed {want:.2f}")
    if r["status"] != band(r["score"]):
        out.append(f"status {r['status']} for score {r['score']}")
    if r["coverage"] != {"evaluated": len(counted), "total": len(rows)}:
        out.append(f"coverage {r['coverage']}")
    return out


def _expected(rec_id: str, rows: Dict[str, Dict[str, Any]]) -> float:
    def gain(key: str, new: float) -> float:
        row = rows[key]
        if "peers" not in row["evidence"]:
            return 0.0
        return max(0.0, round(row["weight"] * (pct(new, row["evidence"]["peers"]) - (row["sub_score"] or 0)) / 100, 1))

    ev = {k: r["evidence"] for k, r in rows.items()}
    if rec_id == "price:missing":
        return rows["price"]["weight"]
    if rec_id in ("info:empty", "info:words"):
        return gain("description", ev["description"]["median_words"])
    if rec_id == "info:tags":
        return gain("tags", 1)
    if rec_id == "info:review":
        e = ev["review"]
        return gain("review", review_score(e["good"] + 1, e["total"] + 1, e["p0"], e["m"]))
    if rec_id == "image:coverage":
        return gain("image", ev["image"]["useful"] + 1)
    return 0.0


def gains(r: Dict[str, Any]) -> List[str]:
    rows = {f["key"]: f for f in r["factors"]}
    out = []
    for rec in r["recommendations"]:
        rid, got = rec["id"], rec["gain_points"]
        per_image = rid.startswith("image:") and rid != "image:coverage"
        want = _expected("image:coverage" if per_image else rid, rows)
        ok = abs(got - want) <= 0.15 or (per_image and got == 0)
        if not ok:
            out.append(f"{rid}: gain {got} != expected {want}")
    return out
