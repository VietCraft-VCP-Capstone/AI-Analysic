"""Scheduler huẩn luyện định kỳ cho Seasonal Deep Learning Forecaster (hằng tuần).

Chạy ngầm theo pattern của `f29_scheduler.py`:
- Dùng distributed lock `scheduler_locks` trên `db_live()` để tránh chạy trùng khi scale nhiều worker.
- Lưu trạng thái lần chạy & kết quả validation gate vào `scheduler_state` (`_id="seasonal_dl_retrain"`).
- Mặc định chỉ tự động bật khi `SEASONAL_DL_SCHEDULER_ENABLED=1` (hoặc gọi trực tiếp `run_once()` từ cron/CLI).
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo

from app.api.v1._live import db_live
from app.core.seasonal_dl import forecaster, train as dl_train

log = logging.getLogger("seasonal_dl_scheduler")
TZ_VN = ZoneInfo("Asia/Ho_Chi_Minh")
LOCK_NAME = "seasonal_dl_weekly_retrain"
STATE_ID = "seasonal_dl_retrain"
MARKET_LOCK_NAME = "seasonal_market_daily_collect"
MARKET_STATE_ID = "seasonal_market_collect"

_stop_event = threading.Event()
_thread: Optional[threading.Thread] = None


def _acquire_lock(lock_name: str = LOCK_NAME, ttl_seconds: int = 1800) -> bool:
    try:
        col = db_live()["scheduler_locks"]
        now = datetime.now(TZ_VN)
        res = col.update_one(
            {
                "_id": lock_name,
                "$or": [{"expires_at": {"$lte": now}}, {"expires_at": {"$exists": False}}],
            },
            {"$set": {"_id": lock_name, "locked_at": now, "expires_at": now + timedelta(seconds=ttl_seconds)}},
            upsert=True,
        )
        return bool(res.upserted_id or res.modified_count)
    except Exception as exc:
        log.warning("seasonal scheduler lock skipped (%s): %s", lock_name, exc)
        return False


def _release_lock(lock_name: str = LOCK_NAME) -> None:
    try:
        db_live()["scheduler_locks"].delete_one({"_id": lock_name})
    except Exception:
        pass


def run_market_collector_once(force: bool = False) -> Dict[str, Any]:
    """Chạy cron thu thập dữ liệu đa sàn hằng ngày (Tiki + Etsy v3 + Printify + VietCraft + Snapshot 30d)."""
    if not force and not _acquire_lock(MARKET_LOCK_NAME, ttl_seconds=2400):
        return {"status": "skipped_locked"}

    started = datetime.now(TZ_VN)
    try:
        app_root = Path(__file__).resolve().parents[2]
        subprocess.run(
            [sys.executable, "-m", "app.collectors.collect_external_products"],
            cwd=str(app_root),
            check=True,
        )
        payload = {
            "_id": MARKET_STATE_ID,
            "last_run_at": started.isoformat(),
            "finished_at": datetime.now(TZ_VN).isoformat(),
            "status": "ok",
        }
        try:
            db_live()["scheduler_state"].replace_one({"_id": MARKET_STATE_ID}, payload, upsert=True)
        except Exception as exc:
            log.warning("seasonal market collector state save failed: %s", exc)
        return payload
    except Exception as exc:
        log.exception("seasonal market collector failed: %s", exc)
        return {"status": "error", "error": str(exc)}
    finally:
        if not force:
            _release_lock(MARKET_LOCK_NAME)


def _run_training_subprocess() -> Dict[str, Any]:
    """Chạy train.py trong tiến trình con tách biệt khỏi web server để tránh nghẽn GIL/RAM."""
    app_root = Path(__file__).resolve().parents[2]
    subprocess.run(
        [sys.executable, "-m", "app.core.seasonal_dl.train"],
        cwd=str(app_root),
        check=True,
    )
    meta_path = Path(__file__).resolve().parent / "seasonal_dl" / "model" / "meta.json"
    if meta_path.exists():
        return json.loads(meta_path.read_text("utf-8"))
    return {}


def run_once(force: bool = False, use_subprocess: bool = True) -> Dict[str, Any]:
    """Thực thi 1 chu kỳ retrain + validation gate và nạp lại model trong bộ nhớ."""
    if not force and not _acquire_lock():
        return {"status": "skipped_locked"}

    started = datetime.now(TZ_VN)
    try:
        meta = _run_training_subprocess() if use_subprocess else (dl_train.train() or {})
        if hasattr(forecaster, "reload"):
            forecaster.reload()
        payload = {
            "_id": STATE_ID,
            "last_run_at": started.isoformat(),
            "finished_at": datetime.now(TZ_VN).isoformat(),
            "status": "validated" if meta.get("validated") else "rejected_by_gate",
            "validated": bool(meta.get("validated")),
            "improvement_vs_naive_scaled_mae_pct": meta.get("improvement_vs_naive_scaled_mae_pct"),
            "avg_coverage_p10_p90": meta.get("avg_coverage_p10_p90"),
        }
        try:
            db_live()["scheduler_state"].replace_one({"_id": STATE_ID}, payload, upsert=True)
        except Exception as exc:
            log.warning("seasonal_dl scheduler_state save failed: %s", exc)
        return payload
    except Exception as exc:
        log.exception("seasonal_dl retrain failed: %s", exc)
        return {"status": "error", "error": str(exc)}
    finally:
        if not force:
            _release_lock()


def _loop() -> None:
    last_market_day: Optional[str] = None
    last_dl_day: Optional[str] = None
    while not _stop_event.is_set():
        now = datetime.now(TZ_VN)
        day_key = now.date().isoformat()
        # Thu thập dữ liệu đa sàn hằng ngày lúc 02:30 giờ Việt Nam (giữ độ tươi <= 30 ngày & snapshot 30d)
        if now.hour == 2 and now.minute >= 30 and last_market_day != day_key:
            last_market_day = day_key
            if os.getenv("SEASONAL_MARKET_COLLECTOR_ENABLED", "1") == "1":
                run_market_collector_once()
        # Huấn luyện lại mô hình Seasonal DL vào Chủ Nhật 02:00 sáng giờ Việt Nam
        if now.weekday() == 6 and now.hour == 2 and last_dl_day != day_key:
            last_dl_day = day_key
            if os.getenv("SEASONAL_DL_SCHEDULER_ENABLED", "0") == "1":
                run_once()
        _stop_event.wait(900)


def start() -> None:
    global _thread
    dl_on = os.getenv("SEASONAL_DL_SCHEDULER_ENABLED", "0") == "1"
    mkt_on = os.getenv("SEASONAL_MARKET_COLLECTOR_ENABLED", "0") == "1"
    if not (dl_on or mkt_on):
        return
    if _thread and _thread.is_alive():
        return
    _stop_event.clear()
    _thread = threading.Thread(target=_loop, name="seasonal-dl-scheduler", daemon=True)
    _thread.start()


def stop() -> None:
    global _thread
    _stop_event.set()
    if _thread and _thread.is_alive():
        _thread.join(timeout=2.0)
    _thread = None

