from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.api.v1._mart import db
from app.services.f30.rules import MODEL_VERSION

ENTITY = "shop"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def save_events(shop_id: str, events: List[Dict[str, Any]], mode: str) -> None:
    coll = db()["anomaly_event"]
    for ev in events:
        key = {"entity_type": ENTITY, "entity_id": shop_id,
               "metric": ev["metric"], "event_date": ev["date"]}
        doc = {k: v for k, v in ev.items() if k not in ("date", "metric")}
        coll.update_one(key, {"$set": {**doc, "mode": mode, "computed_at": _now()}}, upsert=True)


def save_run(shop_id: str, run_date: str, status: str, skip_reason: Optional[str],
             history_days: int, metrics: Dict[str, Any], mode: str) -> None:
    key = {"entity_type": ENTITY, "entity_id": shop_id, "run_date": run_date}
    doc = {"status": status, "skip_reason": skip_reason, "history_days": history_days,
           "metrics": metrics, "mode": mode, "computed_at": _now(), "model_version": MODEL_VERSION}
    db()["anomaly_run"].update_one(key, {"$set": doc}, upsert=True)


def read_events(shop_id: str, from_date: Optional[str] = None) -> List[Dict[str, Any]]:
    loc: Dict[str, Any] = {"entity_type": ENTITY, "entity_id": shop_id}
    if from_date:
        loc["event_date"] = {"$gte": from_date}
    return list(db()["anomaly_event"].find(loc, {"_id": 0}).sort("event_date", -1))


def latest_run(shop_id: str) -> Optional[Dict[str, Any]]:
    return db()["anomaly_run"].find_one(
        {"entity_type": ENTITY, "entity_id": shop_id}, {"_id": 0}, sort=[("run_date", -1)])
