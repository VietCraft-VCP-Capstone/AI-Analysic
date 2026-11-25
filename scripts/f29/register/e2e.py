import json
from collections import defaultdict

import numpy as np

from app.api.v1._live import db_live
from app.core.f29.score.scoring import COUNTED
from app.core.f29.score.calculator import HealthScoreCalculator
from scripts.f29.register.learn import ROOT
from scripts.f29.register.learn import HAND

OUT = ROOT / "notes/f29/register/e2e.json"
MIN_VIEWS = 30
BUDGET = 8.0


def outcomes(live) -> dict:
    out = defaultdict(lambda: {"views": 0.0, "orders": 0.0, "ev_views": 0, "carts": 0})
    for m in live["product_daily_metrics"].find({}, {"product_id": 1, "views": 1, "orders_count": 1}):
        o = out[str(m["product_id"])]
        o["views"] += m.get("views") or 0
        o["orders"] += m.get("orders_count") or 0
    for e in live["product_events"].find({}, {"product_id": 1, "event_type": 1}):
        o = out[str(e["product_id"])]
        o["ev_views" if e["event_type"] == "view" else "carts"] += 1
    return out


def hand_score(factors: list) -> float:
    rows = [f for f in factors if f["state"] in COUNTED and f["sub_score"] is not None]
    total = sum(HAND[f["key"]] for f in rows)
    return sum(HAND[f["key"]] * f["sub_score"] for f in rows) / total if total else 0.0


def _r(x, y) -> float | None:
    return round(float(np.corrcoef(x, y)[0, 1]), 3) if len(x) > 2 and np.std(x) > 0 and np.std(y) > 0 else None


def main() -> dict:
    live = db_live()
    calc, rows = HealthScoreCalculator(), []
    for pid, o in outcomes(live).items():
        if o["views"] < MIN_VIEWS:
            continue
        r = calc.calculate(pid, image_budget=BUDGET)
        if r and "error" not in r:
            rows.append({"id": pid, "score": r["score"], "hand": round(hand_score(r["factors"]), 1),
                         "confidence": r["confidence"]["level"], "cvr": o["orders"] / o["views"],
                         "cart": o["carts"] / max(o["ev_views"], 1)})
    s, h = np.array([x["score"] for x in rows]), np.array([x["hand"] for x in rows])
    cvr, cart = np.array([x["cvr"] for x in rows]), np.array([x["cart"] for x in rows])
    report = {"n": len(rows), "note": "lượt truy cập VietCraft trông như do script tạo ra; chỉ là chỉ dấu",
              "r_cvr": {"chính thức": _r(s, cvr), "đặt tay": _r(h, cvr)},
              "r_cart": {"chính thức": _r(s, cart), "đặt tay": _r(h, cart)},
              "confidence": {k: sum(x["confidence"] == k for x in rows) for k in ("Cao", "Vừa", "Thấp")}}
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", "utf-8")
    return report


if __name__ == "__main__":
    print(json.dumps(main(), ensure_ascii=False, indent=1))
