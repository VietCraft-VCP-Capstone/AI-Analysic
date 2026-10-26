import logging
import subprocess
import sys
from pathlib import Path

from pymongo import MongoClient
from pymongo.errors import PyMongoError

from . import fusion, live_data, store
from .service import analyze, today

TZ = "Asia/Ho_Chi_Minh"
ROOT = Path(__file__).resolve().parents[3]
TREND_TIMEOUT = 40 * 60
LOCAL_MONGO = "mongodb://127.0.0.1:27017"
log = logging.getLogger(__name__)


def nightly() -> int:
    try:
        version = fusion.load_bundle().meta["model_version"]
    except (FileNotFoundError, RuntimeError) as exc:
        log.warning("listing intel nightly skipped, bundle not ready: %s", exc)
        return 0
    n = 0
    for pid in live_data.updated_since(store.last_computed(version)):
        try:
            inp = live_data.load_listing(pid)
            if inp is not None:
                analyze(inp, today(), persist=True)
                n += 1
        except Exception:
            log.exception("listing intel nightly failed for %s", pid)
    log.info("listing intel nightly: %d listing", n)
    return n


def _local_mongo_up() -> bool:
    try:
        with MongoClient(LOCAL_MONGO, serverSelectionTimeoutMS=2000) as client:
            client.admin.command("ping")
        return True
    except PyMongoError:
        return False


def weekly_trends() -> None:
    if not _local_mongo_up():
        log.info("listing intel: trend collection disabled (local-only)")
        return
    cmd = [sys.executable, "-m", "scripts.li.collect_trend_keywords", "--refresh"]
    try:
        r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=TREND_TIMEOUT)
        log.log(logging.INFO if r.returncode == 0 else logging.ERROR, "listing intel trends: %s",
                (r.stdout + r.stderr)[-2000:])
    except Exception:
        log.exception("listing intel weekly trend collection failed")


def register(scheduler) -> None:
    from apscheduler.triggers.cron import CronTrigger

    scheduler.add_job(nightly, CronTrigger(hour=2, minute=0, timezone=TZ), id="li_nightly",
                      max_instances=1, coalesce=True)
    scheduler.add_job(weekly_trends, CronTrigger(day_of_week="mon", hour=3, minute=0, timezone=TZ),
                      id="li_weekly_trends", max_instances=1, coalesce=True)
