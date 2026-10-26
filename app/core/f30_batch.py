import logging
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from app.api.v1._f30_store import save_events, save_run
from app.api.v1._live_data import GIO_VN, cac_ngay
from app.services.f30.detector import baseline, detect_day, pit_z
from app.services.f30.explain import top_listings
from app.services.f30.live_loader import live_shop_ids, load_shop
from app.services.f30.rules import MAX_ZERO_RUN, MIN_HISTORY_DAYS, WINDOW

logger = logging.getLogger("f30_batch")
LOAD_DAYS = 120          # đủ để xét ngưỡng confidence 56 ngày
CONFIDENT_DAYS = 56
METRICS = ("views", "revenue")


def _skip(reason: str, history: int) -> Dict[str, Any]:
    return {"status": "skipped", "skip_reason": reason, "history_days": history, "metrics": {}}


def _total(per_listing: Dict[str, np.ndarray], n: int) -> np.ndarray:
    return np.sum(list(per_listing.values()), axis=0) if per_listing else np.zeros(n)


def _history_days(data: Dict[str, Any], n: int) -> int:
    active = np.zeros(n, dtype=bool)
    for arr in list(data["views"].values()) + list(data["orders"].values()):
        active |= arr > 0
    idx = np.flatnonzero(active)
    return 0 if idx.size == 0 else int(n - idx[0])


def _scale(metric: str, totals: Dict[str, np.ndarray], t: int) -> float:
    if metric == "views":
        return 1.0
    rev, orders = totals["revenue"][t - WINDOW:t].sum(), totals["orders"][t - WINDOW:t].sum()
    return float(rev / max(1.0, orders))


def _summary(series: np.ndarray, days: List[str], t: int, scale: float) -> Dict[str, Any]:
    s = series / scale
    dows = np.array([date.fromisoformat(d).weekday() for d in days])
    mu, var = baseline(s[t - WINDOW:t], dows[t - WINDOW:t], dows[t])
    return {"expected": int(round(mu * scale)), "actual": int(round(float(series[t]))),
            "z": round(pit_z(float(s[t]), mu, var), 2)}


def analyse_shop(shop_id: str, data: Dict[str, Any], days: List[str], t_indexes: List[int],
                 mode: str = "live", listing_prefix: str = "live_") -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Thuần: không ghi DB. Trả (sự kiện, thông tin run của ngày cuối)."""
    n = len(days)
    if not data["titles"]:
        return [], _skip("khong_co_san_pham", 0)
    history = _history_days(data, n)
    if history < MIN_HISTORY_DAYS:
        return [], _skip("qua_ngan", history)

    totals = {m: _total(data[m], n) for m in (*METRICS, "orders")}
    confidence = "ok" if history >= CONFIDENT_DAYS else "low_history"
    events = []
    for t in t_indexes:
        for metric in METRICS:
            scale = _scale(metric, totals, t)
            ev = detect_day(totals[metric], days, t, metric, scale) if scale > 0 else None
            if ev is None:
                continue
            ev.update(id=f"{shop_id}:{metric}:{ev['date']}", confidence=confidence, mode=mode,
                      top_listings=top_listings(data[metric], data["titles"], t,
                                                ev["direction"], listing_prefix))
            events.append(ev)

    t_last = n - 1
    metrics = {}
    for metric in METRICS:
        scale = _scale(metric, totals, t_last)
        if scale > 0:
            metrics[metric] = _summary(totals[metric], days, t_last, scale)
    info = {"status": "analysed", "skip_reason": None, "history_days": history, "metrics": metrics}
    return events, info


def run_live(run_date: Optional[str] = None, backfill_days: int = 0) -> Dict[str, Any]:
    run_date = run_date or (datetime.now(GIO_VN).date() - timedelta(days=1)).isoformat()
    n = max(LOAD_DAYS, WINDOW + MAX_ZERO_RUN + backfill_days + 1)
    days = cac_ngay(n, run_date)
    t_indexes = list(range(n - 1 - backfill_days, n))
    shops = live_shop_ids()
    out: Dict[str, Any] = {"run_date": run_date, "shops_total": len(shops),
                           "shops_analysed": 0, "skipped": {}, "events": []}
    for shop_id in shops:
        try:
            events, info = analyse_shop(shop_id, load_shop(shop_id, days), days, t_indexes,
                                        mode="live", listing_prefix="live_")
        except Exception:
            logger.exception("F30 loi shop %s", shop_id)
            events, info = [], _skip("loi", 0)
        save_events(shop_id, events, mode="live")
        save_run(shop_id, run_date, info["status"], info["skip_reason"],
                 info["history_days"], info["metrics"], mode="live")
        if info["status"] == "analysed":
            out["shops_analysed"] += 1
        else:
            out["skipped"][info["skip_reason"]] = out["skipped"].get(info["skip_reason"], 0) + 1
        out["events"] += [{**e, "shop_id": shop_id} for e in events if e["date"] == run_date]
    return out
