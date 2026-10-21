import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, List, Optional

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.api.v1._live import db_live, LOC_SP_THAT
from app.core.f29.calculator import HealthScoreCalculator

STATE_COLLECTION = "scheduler_state"
STATE_ID_MINUTE_SCAN = "f29_minute_scan"
STATE_ID_NIGHTLY = "f29_nightly_rescan"

DEFAULT_LOOKBACK_MINUTES = 24 * 60


def _get_last_scan_time(job_id: str, default_lookback_minutes: int = DEFAULT_LOOKBACK_MINUTES) -> datetime:
    db = db_live()
    doc = db[STATE_COLLECTION].find_one({"_id": job_id})
    if doc and doc.get("last_scan_time"):
        ts = doc["last_scan_time"]
        if isinstance(ts, datetime) and ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts
    return datetime.now(timezone.utc) - timedelta(minutes=default_lookback_minutes)


def _set_last_scan_time(job_id: str, ts: datetime) -> None:
    db = db_live()
    db[STATE_COLLECTION].update_one(
        {"_id": job_id},
        {"$set": {"last_scan_time": ts, "updated_at": datetime.now(timezone.utc)}},
        upsert=True,
    )


def _recalculate_and_save(
    product_ids: Iterable, calculator: Optional[HealthScoreCalculator] = None
) -> int:
    calc = calculator or HealthScoreCalculator()
    n_ok = 0
    for pid in product_ids:
        try:
            result = calc.calculate(str(pid))
            if result is not None:
                calc.save(result)
                n_ok += 1
        except Exception as e:  # noqa: BLE001
            print(f"[f29_scheduler] Loi cham diem product_id={pid}: "
                  f"{type(e).__name__}: {e}", flush=True)
    return n_ok


def scan_changed_products() -> int:
    db = db_live()
    scan_started_at = datetime.now(timezone.utc)
    last_scan_time = _get_last_scan_time(STATE_ID_MINUTE_SCAN)

    changed_ids = {
        p["_id"] for p in db["products"].find(
            {**LOC_SP_THAT, "updated_at": {"$gt": last_scan_time}}, {"_id": 1}
        )
    }

    changed_variant_product_ids = list({
        v["product_id"] for v in db["product_variants"].find(
            {"updated_at": {"$gt": last_scan_time}}, {"product_id": 1}
        )
    })
    activity_product_ids = {
        e["product_id"] for e in db["product_events"].find(
            {"event_type": "view", "created_at": {"$gt": last_scan_time}}, {"product_id": 1}
        )
    }
    for o in db["orders"].find({"created_at": {"$gt": last_scan_time}}, {"items.product_id": 1}):
        activity_product_ids |= {i.get("product_id") for i in (o.get("items") or []) if i.get("product_id")}

    related_ids = list(set(changed_variant_product_ids) | activity_product_ids)
    if related_ids:
        changed_ids |= {
            p["_id"] for p in db["products"].find(
                {**LOC_SP_THAT, "_id": {"$in": related_ids}}, {"_id": 1}
            )
        }

    n_ok = _recalculate_and_save(changed_ids) if changed_ids else 0
    _set_last_scan_time(STATE_ID_MINUTE_SCAN, scan_started_at)
    return n_ok


def nightly_full_rescan() -> int:
    db = db_live()
    scan_started_at = datetime.now(timezone.utc)

    all_ids = [p["_id"] for p in db["products"].find(LOC_SP_THAT, {"_id": 1})]
    n_ok = _recalculate_and_save(all_ids) if all_ids else 0

    _set_last_scan_time(STATE_ID_NIGHTLY, scan_started_at)
    _set_last_scan_time(STATE_ID_MINUTE_SCAN, scan_started_at)
    return n_ok


_scheduler = None


def start_scheduler():
    global _scheduler
    if _scheduler is not None:
        return _scheduler

    # pyrefly: ignore[missing-import]
    from apscheduler.schedulers.background import BackgroundScheduler
    # pyrefly: ignore[missing-import]
    from apscheduler.triggers.cron import CronTrigger

    scheduler = BackgroundScheduler(timezone=timezone.utc)
    scheduler.add_job(
        scan_changed_products,
        "interval",
        seconds=60,
        id="f29_scan_changed",
        max_instances=1,
        coalesce=True,
        next_run_time=datetime.now(timezone.utc),
    )
    scheduler.add_job(
        nightly_full_rescan,
        CronTrigger(hour=0, minute=0, timezone=timezone.utc),
        id="f29_nightly_rescan",
        max_instances=1,
        coalesce=True,
    )
    try:
        from app.core.listing_intel.jobs import register
        register(scheduler)
    except Exception as e:  # noqa: BLE001
        print(f"[f29_scheduler] Khong dang ky duoc job Listing Intel: {type(e).__name__}: {e}", flush=True)
    scheduler.start()
    _scheduler = scheduler
    return scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None


if __name__ == "__main__":
    print("Quét thay đổi (F29 BR-181)...", flush=True)
    n = scan_changed_products()
    print(f"Đã chấm lại {n} sản phẩm thay đổi.", flush=True)
