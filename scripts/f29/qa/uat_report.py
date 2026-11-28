import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.api.v1._live import db_live
from app.core.f29 import constants
from app.core.f29.paths import WORKSPACE

SCORE_FIELDS = {"product_id": 1, "score": 1, "computed_at": 1}


def _utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _valid(doc: dict, time_field: str, *fields: str) -> bool:
    return isinstance(doc.get(time_field), datetime) and all(doc.get(f) is not None for f in fields)


def _in_window(docs, time_field: str, since: datetime, *fields: str) -> list:
    return [d for d in docs if _valid(d, time_field, *fields) and _utc(d[time_field]) >= since]


def _history(scores) -> dict:
    hist: dict = {}
    for s in scores:
        if _valid(s, "computed_at", "product_id"):
            hist.setdefault(str(s["product_id"]), []).append((_utc(s["computed_at"]), s.get("score")))
    return {pid: sorted(rows, key=lambda r: r[0]) for pid, rows in hist.items()}


def _delta(rows: list, t0: datetime):
    before = [sc for at, sc in rows if at < t0]
    after = [sc for at, sc in rows if at >= t0]
    if not before or not after or before[-1] is None or after[-1] is None:
        return None
    return after[-1] - before[-1]


def _products(actions: list, hist: dict) -> dict:
    first: dict = {}
    for a in sorted(actions, key=lambda a: _utc(a["created_at"])):
        first.setdefault(str(a["product_id"]), a)
    return {
        pid: {"shop": str(a["shop_id"]), "delta": _delta(hist.get(pid, []), _utc(a["created_at"]))}
        for pid, a in first.items()
    }


def _stats(actions: int, products: list, feedback: list) -> dict:
    deltas = [p["delta"] for p in products if p["delta"] is not None]
    return {
        "actions": actions,
        "products_acted": len(products),
        "ai_wrong": sum(f.get("verdict") == "ai_wrong" for f in feedback),
        "ai_right": sum(f.get("verdict") == "ai_right" for f in feedback),
        "products_with_delta": len(deltas),
        "improved": sum(d > 0 for d in deltas),
        "avg_delta": round(sum(deltas) / len(deltas), 1) if deltas else None,
    }


def collect(live_db, store_db, since: datetime) -> dict:
    since = _utc(since)
    gte = since.astimezone(timezone.utc).replace(tzinfo=None)
    actions = _in_window(live_db["health_action_events"].find({"created_at": {"$gte": gte}}),
                         "created_at", since, "product_id", "shop_id")
    feedback = _in_window(store_db["f29_feedback"].find({"updated_at": {"$gte": gte}}),
                          "updated_at", since, "shop_id")
    acted = list({a["product_id"] for a in actions})
    scores = store_db["listing_health_scores"].find({"product_id": {"$in": acted}}, SCORE_FIELDS)
    products = _products(actions, _history(scores))
    shops = sorted({str(a["shop_id"]) for a in actions} | {str(f["shop_id"]) for f in feedback})
    rows = [{"shop_id": shop, **_stats(
        actions=sum(str(a["shop_id"]) == shop for a in actions),
        products=[p for p in products.values() if p["shop"] == shop],
        feedback=[f for f in feedback if str(f["shop_id"]) == shop],
    )} for shop in shops]
    totals = _stats(len(actions), list(products.values()), feedback)
    return {"since": since.isoformat(), "shops": rows, "totals": totals}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--out", type=Path, default=WORKSPACE / "notes/f29/qa/uat_report.json")
    args = ap.parse_args(argv)
    since = datetime.now(timezone.utc) - timedelta(days=args.days)
    report = collect(db_live(), constants.store_db(), since)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1, default=str)
    print(f"UAT {args.days}d: {report['totals']['actions']} actions, "
          f"{report['totals']['products_acted']} products, {len(report['shops'])} shops -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
