"""
MongoDB Atlas storage for the trend collectors.

    pip install "pymongo[srv]"
    export MONGODB_URI="mongodb+srv://user:pass@cluster.xxxxx.mongodb.net/"

Collections
-----------
trend_keyword     one doc per keyword
trend_interest    one doc per (keyword, date, granularity, geo)
trend_related     one doc per (keyword, query, kind, date, geo)
collector_run     one doc per collector run -- the audit trail

Every write is an upsert on a unique index, so re-running a job is safe.
That matters: the daily job re-pulls the whole 90-day window each night to
heal any gap left by a failed run, and upserts keep that from duplicating.
"""

import datetime as dt
import os

from pymongo import MongoClient, UpdateOne, ASCENDING

try:
    from dotenv import load_dotenv
    load_dotenv(override=False)
except ImportError:
    pass

DB_NAME = os.environ.get("MONGODB_DB", "vietcraft")


def get_db(uri=None, db_name=None):
    """
    Connect and hand back a database handle.

    The database name comes from --mongo-db, then MONGODB_DB, then the
    default. Any database in the connection string path is ignored on
    purpose -- being explicit here beats a surprise from a copied URI.
    """
    global DB_NAME
    uri = uri or os.environ.get("MONGODB_URI")
    if not uri:
        raise SystemExit(
            "Set MONGODB_URI, e.g.\n"
            '  export MONGODB_URI="mongodb+srv://user:pass@cluster.mongodb.net/"'
        )
    if db_name:
        DB_NAME = db_name

    client = MongoClient(uri, serverSelectionTimeoutMS=20000)
    try:
        client.admin.command("ping")      # fail fast on bad URI or blocked IP
    except Exception as exc:              # noqa: BLE001
        raise SystemExit(
            f"Cannot reach Atlas: {exc}\n\n"
            "Usual causes:\n"
            "  - Network Access does not allow this IP (use 0.0.0.0/0)\n"
            "  - wrong password, or a special character that needs URL-encoding\n"
        ) from exc

    db = client[DB_NAME]
    try:
        db.command("ping")                # auth check against THIS database
    except Exception as exc:              # noqa: BLE001
        raise SystemExit(
            f"Connected to Atlas, but cannot use database '{DB_NAME}': {exc}\n\n"
            f"The database user probably has no readWrite grant on '{DB_NAME}'.\n"
            "Atlas -> Database Access -> Edit user -> add a role:\n"
            f"  readWrite @ {DB_NAME}\n"
        ) from exc

    print(f"mongo: connected to database '{DB_NAME}'")
    return db


def ensure_indexes(db):
    """Safe to call every run."""
    db.trend_keyword.create_index([("keyword", ASCENDING)], unique=True)

    db.trend_interest.create_index(
        [("keyword", ASCENDING), ("observed_on", ASCENDING),
         ("granularity", ASCENDING), ("geo", ASCENDING)],
        unique=True, name="uniq_point",
    )
    # The shape almost every query uses: one keyword's series in date order.
    db.trend_interest.create_index(
        [("keyword", ASCENDING), ("granularity", ASCENDING),
         ("observed_on", ASCENDING)],
        name="series_lookup",
    )
    db.trend_interest.create_index([("topic", ASCENDING)], name="by_topic")

    db.trend_related.create_index(
        [("seed_keyword", ASCENDING), ("query", ASCENDING),
         ("kind", ASCENDING), ("observed_on", ASCENDING), ("geo", ASCENDING)],
        unique=True, name="uniq_related",
    )
    db.trend_related.create_index([("kind", ASCENDING), ("value", -1)],
                                  name="rising_rank")


def start_run(db, job):
    return db.collector_run.insert_one({
        "job": job,
        "started_at": dt.datetime.now(dt.timezone.utc),
        "status": "running",
    }).inserted_id


def finish_run(db, run_id, status, rows_written, note=""):
    db.collector_run.update_one(
        {"_id": run_id},
        {"$set": {"finished_at": dt.datetime.now(dt.timezone.utc),
                  "status": status,
                  "rows_written": rows_written,
                  "note": note[:500]}},
    )


def upsert_keywords(db, seed_keywords, anchor):
    """
    Make Atlas match config.py exactly.

    Upserting alone is not enough. The collectors read their keyword list from
    Atlas, not from config.py, so a keyword deleted from config but left
    active in the database keeps getting collected forever. The same goes for
    a former anchor: leave is_anchor set on it and you end up with two, and
    which one wins is down to sort order.

    So this deactivates anything no longer in config, and clears is_anchor
    from everything that is not the current anchor. Nothing is deleted --
    old rows stay in trend_interest, they just stop being refreshed.
    """
    wanted = {k for k, _, _ in seed_keywords} | {anchor}

    ops = [
        UpdateOne({"keyword": k},
                  {"$set": {"product_type": p, "topic": t,
                            "is_anchor": False, "active": True}},
                  upsert=True)
        for k, p, t in seed_keywords
    ]
    ops.append(UpdateOne(
        {"keyword": anchor},
        {"$set": {"is_anchor": True, "active": True}},
        upsert=True,
    ))
    db.trend_keyword.bulk_write(ops, ordered=False)

    retired = db.trend_keyword.update_many(
        {"keyword": {"$nin": list(wanted)}},
        {"$set": {"active": False, "is_anchor": False}},
    )
    demoted = db.trend_keyword.update_many(
        {"keyword": {"$ne": anchor}, "is_anchor": True},
        {"$set": {"is_anchor": False}},
    )

    if retired.modified_count:
        print(f"mongo: retired {retired.modified_count} keywords no longer in config.py")
    if demoted.modified_count:
        print(f"mongo: cleared is_anchor from {demoted.modified_count} old anchor(s)")

    active = db.trend_keyword.count_documents({"active": True})
    print(f"mongo: {active} active keywords, anchor = '{anchor}'")
    return len(ops)


def purge_inactive(db):
    """Delete trend_interest points belonging to retired keywords."""
    dead = db.trend_keyword.distinct("keyword", {"active": False})
    if not dead:
        print("Nothing to purge.")
        return 0
    result = db.trend_interest.delete_many({"keyword": {"$in": dead}})
    db.trend_related.delete_many({"seed_keyword": {"$in": dead}})
    print(f"purged {result.deleted_count} points from {len(dead)} retired keywords:")
    print("  " + ", ".join(sorted(dead)[:12]) + ("..." if len(dead) > 12 else ""))
    return result.deleted_count


def load_keywords(db):
    """Return (anchor, others) the same shape collect_trends.py expects."""
    rows = list(db.trend_keyword.find({"active": True}).sort("keyword", 1))
    if not rows:
        return None, []
    anchors = [r for r in rows if r.get("is_anchor")]
    if not anchors:
        return None, []

    def norm(r):
        return {"id": str(r["_id"]), "keyword": r["keyword"],
                "product_type": r.get("product_type"),
                "topic": r.get("topic"),
                "is_anchor": bool(r.get("is_anchor"))}

    return norm(anchors[0]), [norm(r) for r in rows if not r.get("is_anchor")]


def write_interest(db, payload):
    """Store one collect() payload. Returns the number of points written."""
    ensure_indexes(db)
    granularity = payload["granularity"]
    geo = payload["geo"]
    collected_at = dt.datetime.now(dt.timezone.utc)

    run_id = start_run(db, f"trends_{granularity}")

    ops = []
    for keyword, rec in payload["series"].items():
        for point in rec["points"]:
            # Store the date as a real datetime so Mongo can sort and range it.
            observed = dt.datetime.fromisoformat(point["date"]).replace(
                tzinfo=dt.timezone.utc)
            ops.append(UpdateOne(
                {"keyword": keyword, "observed_on": observed,
                 "granularity": granularity, "geo": geo},
                {"$set": {
                    "raw": point.get("raw"),   # None for the averaged anchor
                    "scaled": point["scaled"],
                    "topic": rec.get("topic"),
                    "product_type": rec.get("product_type"),
                    "is_anchor": rec.get("is_anchor", False),
                    "batch_id": rec["batch_id"],
                    "collected_at": collected_at,
                }},
                upsert=True,
            ))

    written = 0
    for i in range(0, len(ops), 1000):          # chunk so Atlas M0 stays happy
        result = db.trend_interest.bulk_write(ops[i:i + 1000], ordered=False)
        written += result.upserted_count + result.modified_count

    failed = sum(1 for b in payload["batches"] if not b.get("ok"))
    finish_run(db, run_id, "ok" if failed == 0 else "partial",
               len(ops), f"{failed} batches failed")

    print(f"mongo: {len(ops)} points upserted into {DB_NAME}.trend_interest")
    return len(ops)


def write_related(db, payload):
    ensure_indexes(db)
    observed = dt.datetime.fromisoformat(payload["collected_at"]).replace(
        tzinfo=dt.timezone.utc)
    run_id = start_run(db, "trends_related")

    ops = []
    for seed, rec in payload["related"].items():
        for kind in ("top", "rising"):
            for item in rec.get(kind, []):
                ops.append(UpdateOne(
                    {"seed_keyword": seed, "query": item["query"],
                     "kind": kind, "observed_on": observed,
                     "geo": payload["geo"]},
                    {"$set": {"value": item["value"]}},
                    upsert=True,
                ))

    if ops:
        for i in range(0, len(ops), 1000):
            db.trend_related.bulk_write(ops[i:i + 1000], ordered=False)

    finish_run(db, run_id, "ok", len(ops))
    print(f"mongo: {len(ops)} related queries upserted")
    return len(ops)


def health(db):
    """`--mongo-health` -- proof for yourself and for the defence."""
    points = db.trend_interest.count_documents({})
    keywords = len(db.trend_interest.distinct("keyword"))
    print(f"{points} points across {keywords} keywords\n")

    for gran in ("weekly", "daily"):
        first = db.trend_interest.find_one({"granularity": gran},
                                           sort=[("observed_on", 1)])
        last = db.trend_interest.find_one({"granularity": gran},
                                          sort=[("observed_on", -1)])
        if first:
            n = db.trend_interest.count_documents({"granularity": gran})
            print(f"{gran:<8} {n:>7} points  "
                  f"{first['observed_on'].date()} -> {last['observed_on'].date()}")

    print("\nlast 10 runs")
    print("-" * 62)
    for run in db.collector_run.find().sort("started_at", -1).limit(10):
        started = run["started_at"].strftime("%Y-%m-%d %H:%M")
        print(f"{started}  {run['job']:<16} {run.get('status','?'):<8} "
              f"{run.get('rows_written', 0):>7}")
