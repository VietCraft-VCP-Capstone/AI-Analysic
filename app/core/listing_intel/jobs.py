import logging
import subprocess
import sys
from pathlib import Path

from pymongo import MongoClient
from pymongo.errors import PyMongoError

TZ = "Asia/Ho_Chi_Minh"
ROOT = Path(__file__).resolve().parents[3]
TREND_TIMEOUT = 40 * 60
LOCAL_MONGO = "mongodb://127.0.0.1:27017"
log = logging.getLogger(__name__)


def _local_mongo_up() -> bool:
    try:
        with MongoClient(LOCAL_MONGO, serverSelectionTimeoutMS=2000) as client:
            client.admin.command("ping")
        return True
    except PyMongoError:
        return False


def weekly_trends() -> None:
    if not _local_mongo_up():
        log.info("trends: trend collection disabled (local-only)")
        return
    cmd = [sys.executable, "-m", "scripts.li.collect_trend_keywords", "--refresh"]
    try:
        r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=TREND_TIMEOUT)
        log.log(logging.INFO if r.returncode == 0 else logging.ERROR, "trends: %s", (r.stdout + r.stderr)[-2000:])
    except Exception:
        log.exception("trends weekly collection failed")


def register(scheduler) -> None:
    from apscheduler.triggers.cron import CronTrigger

    scheduler.add_job(weekly_trends, CronTrigger(day_of_week="mon", hour=3, minute=0, timezone=TZ),
                      id="li_weekly_trends", max_instances=1, coalesce=True)
