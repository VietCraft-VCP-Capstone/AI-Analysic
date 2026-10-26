import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

LOCAL = "mongodb://127.0.0.1:27017"
os.environ["MONGODB_URI"] = LOCAL
os.environ["MONGODB_DB"] = os.environ.get("LI_TREND_DB", "data-collection")

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "app" / "collectors"))

import collect_trends as ct

KEYWORDS = ROOT / "app" / "core" / "listing_intel" / "data" / "trend_keywords.json"
OUT = Path(os.environ.get("LI_DATA_DIR", ROOT.parent / "ai-data-train-prod" / "data-li")) / "clean"
BUDGET = 20 * 60
STALE = timedelta(days=7)
MISSING = "trend_missing.json"


def rescale_to_existing(payload, db):
    row = next(db.trend_interest.aggregate([
        {"$match": {"keyword": ct.cfg.ANCHOR, "granularity": "weekly"}},
        {"$group": {"_id": None, "m": {"$avg": "$scaled"}}}]))
    factor = row["m"] / payload["batches"][0]["anchor_mean"]
    payload["series"] = {k: r for k, r in payload["series"].items() if not r["is_anchor"]}
    for rec in payload["series"].values():
        for p in rec["points"]:
            p["scaled"] = round(p["raw"] * factor, 2)


def weekly_keywords(db) -> set:
    return set(db.trend_interest.distinct("keyword", {"granularity": "weekly"}))


def stale(db, keywords, now=None):
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    last = {r["_id"]: r["last"] for r in db.trend_interest.aggregate([
        {"$match": {"granularity": "weekly", "keyword": {"$in": keywords}}},
        {"$group": {"_id": "$keyword", "last": {"$max": "$observed_on"}}}])}
    return [k for k in keywords if k not in last or last[k] < now - STALE]


def fetch_and_store(db, todo, deadline) -> list:
    saved = []
    for i in range(0, len(todo), ct.cfg.BATCH_SIZE):
        group = todo[i:i + ct.cfg.BATCH_SIZE]
        if time.monotonic() > deadline:
            print("stopping: time budget used, the rest waits for the next run")
            break
        ct.cfg.SEED_KEYWORDS = [(k, "generic", "li_trend") for k in group]
        payload = ct.collect("weekly", ct.cfg.TIMEFRAME_WEEKLY)
        meta = payload["batches"][0]
        if not meta["ok"] or not meta.get("anchor_mean"):
            print(f"stopping: batch {group} failed (rate limit or no data), the rest waits for the next run")
            break
        rescale_to_existing(payload, db)
        ct.store_mongo.write_interest(db, payload)
        saved += [k for k in group if k in payload["series"]]
    return saved


def write_missing(missing) -> None:
    path = OUT / MISSING
    if missing:
        OUT.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(missing, ensure_ascii=False, indent=1), "utf-8")
    else:
        path.unlink(missing_ok=True)


def main(refresh=False):
    db = ct.store_mongo.get_db()
    if db.client.address != ("127.0.0.1", 27017):
        sys.exit(f"refusing non-local mongo: {db.client.address}")
    keywords = [k for k in json.loads(KEYWORDS.read_text("utf-8")) if k != ct.cfg.ANCHOR]
    have = weekly_keywords(db)
    todo = stale(db, keywords) if refresh else [k for k in keywords if k not in have]
    todo = sorted(todo, key=lambda k: k in have)
    ct.cfg.REQUEST_DELAY, ct.cfg.MAX_RETRIES = 6.0, 2
    saved = fetch_and_store(db, todo, time.monotonic() + BUDGET)
    have = weekly_keywords(db)
    missing = [k for k in keywords if k not in have]
    write_missing(missing)
    print(f"selected {len(todo)}/{len(keywords)}; saved {len(saved)}; still stale {len(todo) - len(saved)}; "
          f"missing {missing}")
    return saved


if __name__ == "__main__":
    main(refresh="--refresh" in sys.argv)
