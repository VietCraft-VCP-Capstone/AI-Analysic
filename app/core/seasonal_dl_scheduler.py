"""Scheduler huẩn luyện định kỳ cho Seasonal Deep Learning Forecaster (hằng tuần).

Chạy ngầm theo pattern của `f29_scheduler.py`:
- Dùng distributed lock `scheduler_locks` trên `db_live()` để tránh chạy trùng khi scale nhiều worker.
- Lưu trạng thái lần chạy & kết quả validation gate vào `scheduler_state` (`_id="seasonal_dl_retrain"`).
- Mặc định chỉ tự động bật khi `SEASONAL_DL_SCHEDULER_ENABLED=1` (hoặc gọi trực tiếp `run_once()` từ cron/CLI).
"""
from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime, timedelta
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo

from app.api.v1._live import db_live
from app.core.seasonal_dl import forecaster, train as dl_train

log = logging.getLogger("seasonal_dl_scheduler")
TZ_VN = ZoneInfo("Asia/Ho_Chi_Minh")
LOCK_NAME = "seasonal_dl_weekly_retrain"
STATE_ID = "seasonal_dl_retrain"

_stop_event = threading.Event()
_thread: Optional[threading.Thread] = None


def _acquire_lock(ttl_seconds: int = 1800) -> bool:
    try:
        col = db_live()["scheduler_locks"]
        now = datetime.now(TZ_VN)
        res = col.update_one(
            {
                "_id": LOCK_NAME,
                "$or": [{"expires_at": {"$lte": now}}, {"expires_at": {"$exists": False}}],
            },
            {"$set": {"_id": LOCK_NAME, "locked_at": now, "expires_at": now + timedelta(seconds=ttl_seconds)}},
            upsert=True,
        )
        return bool(res.upserted_id or res.modified_count)
    except Exception as exc:
        log.warning("seasonal_dl lock skipped: %s", exc)
        return False


def _release_lock() -> None:
    try:
        db_live()["scheduler_locks"].delete_one({"_id": LOCK_NAME})
    except Exception:
        pass


def run_once(force: bool = False) -> Dict[str, Any]:
    """Thực thi 1 chu kỳ retrain + validation gate và nạp lại model trong bộ nhớ."""
    if not force and not _acquire_lock():
        return {"status": "skipped_locked"}

    started = datetime.now(TZ_VN)
    try:
        meta = dl_train.train()
        forecaster.reload() if hasattr(forecaster, "reload") else None
        payload = {
            "_id": STATE_ID,
            "last_run_at": started.isoformat(),
            "finished_at": datetime.now(TZ_VN).isoformat(),
            "status": "validated" if meta.get("validated") else "rejected_by_gate",
            "validated": bool(meta.get("validated")),
            "improvement_vs_naive_pct": meta.get("improvement_vs_naive_pct"),
            "avg_coverage_raw": meta.get("avg_coverage_raw"),
        }
        try:
            db_live()["scheduler_state"].replace_one({"_id": STATE_ID}, payload, upsert=True)
        except Exception:
            pass
        return payload
    except Exception as exc:
        log.exception("seasonal_dl retrain failed: %s", exc)
        return {"status": "error", "error": str(exc)}
    finally:
        if not force:
            _release_lock()


def _loop() -> None:
    while not _stop_event.is_set():
        now = datetime.now(TZ_VN)
        # Chạy vào Chủ Nhật lúc 02:00 sáng giờ Việt Nam
        if now.weekday() == 6 and now.hour == 2:
            run_once()
            _stop_event.wait(3600)
        else:
            _stop_event.wait(900)


def start() -> None:
    global _thread
    if os.getenv("SEASONAL_DL_SCHEDULER_ENABLED", "0") != "1":
        return
    if _thread and _thread.is_alive():
        return
    _stop_event.clear()
    _thread = threading.Thread(target=_loop, name="seasonal-dl-scheduler", daemon=True)
    _thread.start()


def stop() -> None:
    _stop_event.set()

