import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, List, Optional, Tuple
from zoneinfo import ZoneInfo

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from bson import ObjectId
from app.api.v1._live import db_live, LOC_SP_THAT
from app.core.f29.calculator import HealthScoreCalculator
from app.core.f29.constants import MODEL_VERSION

STATE_COLLECTION = "scheduler_state"
STATE_ID_MINUTE_SCAN = "f29_minute_scan"
STATE_ID_NIGHTLY = "f29_nightly_rescan"

DEFAULT_LOOKBACK_MINUTES = 24 * 60
VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


def _get_last_scan_time(job_id: str, default_lookback_minutes: int = DEFAULT_LOOKBACK_MINUTES) -> datetime:
    db = db_live()
    doc = db[STATE_COLLECTION].find_one({"_id": job_id})
    if doc and doc.get("last_scan_time"):
        ts = doc["last_scan_time"]
        if isinstance(ts, datetime) and ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts
    return datetime.now(timezone.utc) - timedelta(minutes=default_lookback_minutes)


def _set_last_scan_time(job_id: str, ts: datetime, failed_ids: Optional[List[str]] = None) -> None:
    db = db_live()
    data = {"last_scan_time": ts, "updated_at": datetime.now(timezone.utc)}
    if failed_ids is not None:
        data["failed_product_ids"] = failed_ids
    db[STATE_COLLECTION].update_one(
        {"_id": job_id},
        {"$set": data},
        upsert=True,
    )


def _recalculate_and_save(
    product_ids: Iterable, calculator: Optional[HealthScoreCalculator] = None
) -> Tuple[int, bool, List[str]]:
    calc = calculator or HealthScoreCalculator()
    n_ok = 0
    failed_ids: List[str] = []
    for pid in product_ids:
        try:
            result = calc.calculate(str(pid))
            if result is not None and "error" in result:
                print(f"[f29_scheduler] Bo qua: {result['error']}", flush=True)
                return n_ok, True, failed_ids
            if result is not None:
                calc.save(result)
                n_ok += 1
        except Exception as e:  # noqa: BLE001
            failed_ids.append(str(pid))
            print(f"[f29_scheduler] Loi cham diem product_id={pid}: "
                  f"{type(e).__name__}: {e}", flush=True)
    print(f"[f29_scheduler] Quet hoan tat: {n_ok} thanh cong, {len(failed_ids)} loi", flush=True)
    return n_ok, False, failed_ids


def scan_changed_products() -> int:
    db = db_live()
    scan_started_at = datetime.now(timezone.utc)
    last_scan_time = _get_last_scan_time(STATE_ID_MINUTE_SCAN)

    state_doc = db[STATE_COLLECTION].find_one({"_id": STATE_ID_MINUTE_SCAN}) or {}
    retry_ids = [ObjectId(i) for i in state_doc.get("failed_product_ids", []) if ObjectId.is_valid(i)]

    changed_ids = {
        p["_id"] for p in db["products"].find(
            {**LOC_SP_THAT, "updated_at": {"$gt": last_scan_time}}, {"_id": 1}
        )
    } | set(retry_ids)

    changed_variant_product_ids = list({
        v["product_id"] for v in db["product_variants"].find(
            {"updated_at": {"$gt": last_scan_time}}, {"product_id": 1}
        )
    })
    changed_review_product_ids = {
        r["product_id"] for r in db["reviews"].find(
            {"updated_at": {"$gt": last_scan_time}}, {"product_id": 1}
        ) if r.get("product_id")
    }

    related_ids = list(set(changed_variant_product_ids) | changed_review_product_ids)
    if related_ids:
        changed_ids |= {
            p["_id"] for p in db["products"].find(
                {**LOC_SP_THAT, "_id": {"$in": related_ids}}, {"_id": 1}
            )
        }

    n_ok, stopped, failed_ids = _recalculate_and_save(changed_ids)
    if not stopped:
        _set_last_scan_time(STATE_ID_MINUTE_SCAN, scan_started_at, failed_ids)
    return n_ok


def needs_full_rescan(db) -> bool:
    latest = db["listing_health_scores"].find_one({}, sort=[("computed_at", -1)])
    return latest is None or latest.get("model_version") != MODEL_VERSION


def nightly_full_rescan() -> int:
    db = db_live()
    scan_started_at = datetime.now(timezone.utc)

    all_ids = [p["_id"] for p in db["products"].find(LOC_SP_THAT, {"_id": 1})]
    n_ok, stopped, failed_ids = _recalculate_and_save(all_ids) if all_ids else (0, False, [])
    if not stopped:
        _set_last_scan_time(STATE_ID_NIGHTLY, scan_started_at)
        _set_last_scan_time(STATE_ID_MINUTE_SCAN, scan_started_at, failed_ids)
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

    scheduler = BackgroundScheduler(timezone=VN_TZ)
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
        CronTrigger(hour=0, minute=0, timezone=VN_TZ),
        id="f29_nightly_rescan",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
    )
    try:
        if needs_full_rescan(db_live()):
            scheduler.add_job(
                nightly_full_rescan,
                id="f29_boot_rescan",
                next_run_time=datetime.now(timezone.utc),
                max_instances=1,
                coalesce=True,
            )
    except Exception as e:  # noqa: BLE001
        print(f"[f29_scheduler] Khong kiem tra duoc quet lai khi khoi dong: {type(e).__name__}: {e}", flush=True)
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
