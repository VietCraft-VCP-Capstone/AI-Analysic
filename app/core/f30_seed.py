"""F30 · dữ liệu mồi: dò bất thường trên listing_daily, ghi anomaly_event + anomaly_run."""
from typing import Any, Dict, List, Tuple

import numpy as np

from app.core.f30_batch import analyse_shop
from app.core.writer import finish_model_run, save_model_output, start_model_run
from app.services.f30.rules import MODEL_VERSION, WINDOW

MODE = "seed_demo"
ENTITY = "shop"
METRICS = ("views", "revenue", "orders")


def _lay_du_lieu(db, days: List[str]) -> Dict[str, Tuple[Dict[str, Any], int]]:
    """shop_id -> (dữ liệu theo listing, số ngày tới ngày cuối của shop)."""
    pos = {d: i for i, d in enumerate(days)}
    n = len(days)
    tieu_de = {str(r["listing_id"]): r.get("title") or "" for r in
               db["listings"].find({}, {"_id": 0, "listing_id": 1, "title": 1})}
    rows = db["listing_daily"].aggregate([
        {"$group": {"_id": {"shop": "$shop_id", "listing": "$listing_id", "date": "$date"},
                    "views": {"$sum": "$views"}, "revenue": {"$sum": "$revenue_vnd"},
                    "orders": {"$sum": "$orders"}}},
    ], allowDiskUse=True)

    shops: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        k = r["_id"]
        if k["shop"] is None or k["listing"] is None:
            continue
        shop, pid, i = str(k["shop"]), str(k["listing"]), pos[k["date"]]
        sh = shops.setdefault(shop, {"titles": {}, "last": 0, "views": {}, "revenue": {}, "orders": {}})
        sh["last"] = max(sh["last"], i + 1)
        sh["titles"][pid] = tieu_de.get(pid, "")
        for m in METRICS:
            sh[m].setdefault(pid, np.zeros(n))[i] += float(r[m] or 0)
    return {shop: (sh, sh["last"]) for shop, sh in shops.items()}


def _cat(sh: Dict[str, Any], k: int) -> Dict[str, Any]:
    return {"titles": sh["titles"], **{m: {p: a[:k] for p, a in sh[m].items()} for m in METRICS}}


def _dong_event(shop: str, ev: Dict[str, Any]) -> Dict[str, Any]:
    bo = {k: v for k, v in ev.items() if k not in ("date", "id")}
    return {"entity_type": ENTITY, "entity_id": shop, "event_date": ev["date"], **bo}


def _dong_run(shop: str, run_date: str, info: Dict[str, Any]) -> Dict[str, Any]:
    return {"entity_type": ENTITY, "entity_id": shop, "run_date": run_date, "mode": MODE,
            "status": info["status"], "skip_reason": info["skip_reason"],
            "history_days": info["history_days"], "metrics": info["metrics"]}


def _ghi_run(runs: List[Dict[str, Any]]) -> None:
    run_id = start_model_run("anomaly_run", MODEL_VERSION, {"rows": len(runs)})
    n = save_model_output("anomaly_run", run_id, MODEL_VERSION, runs)
    finish_model_run(run_id, "COMPLETED", {"rows_written": n})


def build_anomaly_event(db, dry_run: bool = False) -> List[Dict[str, Any]]:
    days = sorted(db["listing_daily"].distinct("date"))
    ban_ghi, runs = [], []
    for shop, (sh, k) in _lay_du_lieu(db, days).items():
        sd = days[:k]
        events, info = analyse_shop(shop, _cat(sh, k), sd, list(range(WINDOW, k)),
                                    mode=MODE, listing_prefix="")
        ban_ghi += [_dong_event(shop, e) for e in events]
        runs.append(_dong_run(shop, sd[-1], info))
    if not dry_run:
        _ghi_run(runs)
    ban_ghi.sort(key=lambda r: (r["event_date"], -abs(r["z"])))
    print(f"   [anomaly] {len(runs)} shop, {sum(r['status'] == 'analysed' for r in runs)} đã dò")
    return ban_ghi
