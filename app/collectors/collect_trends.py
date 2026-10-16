import argparse
import datetime as dt
import json
import os
import random
import sys
import time
import uuid

# Run from anywhere: every module here does `import config`, which only
# resolves when the script's own directory is the working directory.
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.getcwd())

import pandas as pd
from trendspy import Trends

import config as cfg

try:
    import store_mongo
except ImportError:                                    # pymongo not installed
    store_mongo = None


# --------------------------------------------------------------------------
# keywords -- from the database when there is one, otherwise from config
# --------------------------------------------------------------------------

def keywords_from_config():
    rows = [{"id": i, "keyword": k, "product_type": p, "topic": t,
             "is_anchor": False}
            for i, (k, p, t) in enumerate(cfg.SEED_KEYWORDS, start=1)]
    anchor = {"id": 0, "keyword": cfg.ANCHOR, "product_type": "generic",
              "topic": "anchor", "is_anchor": True}
    return anchor, rows


def load_keywords(mdb=None):
    """Atlas first, config.py as the fallback."""
    if mdb is not None:
        # Reconcile every run. The stored list is the one the collectors use,
        # so if it drifts from config.py the drift is invisible until you
        # notice retired keywords still arriving in the data.
        store_mongo.upsert_keywords(mdb, cfg.SEED_KEYWORDS, cfg.ANCHOR)
        anchor, others = store_mongo.load_keywords(mdb)
        if anchor:
            return anchor, others
    return keywords_from_config()


# --------------------------------------------------------------------------
# fetching
# --------------------------------------------------------------------------

HTTP_CALLS = {"n": 0}


def make_client():

    client = Trends(
        language="en",
        tzs=cfg.TZ_OFFSET,
        request_delay=cfg.REQUEST_DELAY,
        max_retries=cfg.TRENDSPY_RETRIES,
    )

    original_get = client.session.get

    def counting_get(*args, **kwargs):
        HTTP_CALLS["n"] += 1
        return original_get(*args, **kwargs)

    client.session.get = counting_get
    return client


def chunk(items, size):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def polite_sleep():
    time.sleep(random.uniform(cfg.SLEEP_MIN, cfg.SLEEP_MAX))


def fetch_batch(tr, terms, timeframe):
    for attempt in range(1, cfg.MAX_RETRIES + 1):
        try:
            df = tr.interest_over_time(terms, timeframe=timeframe, geo=cfg.GEO)
            if df is None or len(df) == 0:
                return None
            return df
        except Exception as exc:                       # noqa: BLE001
            message = str(exc)
            rate_limited = "429" in message or "quota" in message.lower()

            if attempt == cfg.MAX_RETRIES:
                print(f"  ! gave up after {attempt} tries: {message[:120]}")
                return None

            if rate_limited:
                wait = cfg.RETRY_BASE * (2 ** (attempt - 1))
                print(f"  . rate limited, waiting {wait/60:.1f} min "
                      f"(attempt {attempt}/{cfg.MAX_RETRIES})")
            else:
                wait = 10.0 * attempt
                print(f"  . retry {attempt}/{cfg.MAX_RETRIES} in {wait:.0f}s "
                      f"({message[:80]})")
            time.sleep(wait)
    return None


CHECKPOINT_DIR = ".checkpoints"


def checkpoint_path(granularity):
    return os.path.join(CHECKPOINT_DIR, f"{granularity}_{cfg.GEO}.json")


def load_checkpoint(granularity):
    """Batches already fetched today, so a blocked run can pick up where it left off."""
    path = checkpoint_path(granularity)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            saved = json.load(fh)
    except (json.JSONDecodeError, OSError):
        return {}
    if saved.get("date") != dt.date.today().isoformat():
        return {}                     # yesterday's work; refetch
    return saved.get("batches", {})


def save_checkpoint(granularity, done):
    os.makedirs(CHECKPOINT_DIR, exist_ok=True)
    with open(checkpoint_path(granularity), "w", encoding="utf-8") as fh:
        json.dump({"date": dt.date.today().isoformat(), "batches": done},
                  fh, ensure_ascii=False)


def clear_checkpoint(granularity):
    path = checkpoint_path(granularity)
    if os.path.exists(path):
        os.remove(path)


_ANCHOR_COPIES = []       # one entry per batch: {"batch_id", "points"}


def collect(granularity, timeframe, out_dir=None, mdb=None):
 
    anchor, others = load_keywords(mdb)
    tr = make_client()
    batches_meta = []
    series = {}                       # keyword -> record
    _ANCHOR_COPIES.clear()

    done = load_checkpoint(granularity)
    groups = list(chunk(others, cfg.BATCH_SIZE))
    print(f"{len(others)} keywords -> {len(groups)} requests "
          f"({granularity}, timeframe='{timeframe}', geo='{cfg.GEO}')")
    if done:
        print(f"resuming: {len(done)} batches already fetched today")
    print(f"pacing: {cfg.REQUEST_DELAY}s request delay + "
          f"{cfg.SLEEP_MIN:.0f}-{cfg.SLEEP_MAX:.0f}s between batches "
          f"(~{len(groups) * (cfg.SLEEP_MIN + cfg.SLEEP_MAX) / 120:.0f} min)\n")

    for i, group in enumerate(groups, 1):
        key = "|".join(sorted(g["keyword"] for g in group))
        terms = [anchor["keyword"]] + [g["keyword"] for g in group]

        if key in done:
            cached = done[key]
            print(f"[{i}/{len(groups)}] skip, already fetched")
            batches_meta.append(cached["meta"])
            for kw, rec in cached["series"].items():
                series.setdefault(kw, rec)
            if "anchor_copy" in cached:
                _ANCHOR_COPIES.append(cached["anchor_copy"])
            if anchor["keyword"] not in series:
                series[anchor["keyword"]] = {
                    "keyword_id": anchor["id"], "product_type": "generic",
                    "topic": "anchor", "is_anchor": True,
                    "batch_id": cached["meta"]["batch_id"], "points": [],
                }
            continue

        batch_id = uuid.uuid4().hex[:8]
        print(f"[{i}/{len(groups)}] {', '.join(t for t in terms[1:])}")

        df = fetch_batch(tr, terms, timeframe)
        ok = df is not None and anchor["keyword"] in getattr(df, "columns", [])

        if not ok:
            print("  ! batch failed or anchor missing")
            batches_meta.append({"batch_id": batch_id, "ok": False,
                                 "keywords": [g["keyword"] for g in group]})
            polite_sleep()
            continue

        anchor_series = pd.to_numeric(df[anchor["keyword"]], errors="coerce")
        anchor_mean = float(anchor_series.mean())

        batches_meta.append({
            "batch_id": batch_id,
            "ok": True,
            "keywords": [g["keyword"] for g in group],
            "anchor_mean": round(anchor_mean, 2),
            "scale_factor": None,          # filled in by rescale()
        })

        # Keep every batch's copy of the anchor; rescale() averages them.
        _ANCHOR_COPIES.append({
            "batch_id": batch_id,
            "points": [
                {"date": pd.Timestamp(ts).date().isoformat(),
                 "raw": round(float(v), 2)}
                for ts, v in anchor_series.items() if not pd.isna(v)
            ],
        })

        for kw in group + [anchor]:
            if kw["keyword"] not in df.columns:
                continue
            if kw["keyword"] in series:    # the anchor appears in every batch
                continue
            values = pd.to_numeric(df[kw["keyword"]], errors="coerce")
            series[kw["keyword"]] = {
                "keyword_id": kw["id"],
                "product_type": kw.get("product_type"),
                "topic": kw.get("topic"),
                "is_anchor": kw.get("is_anchor", False),
                "batch_id": batch_id,
                "points": [
                    {"date": pd.Timestamp(ts).date().isoformat(),
                     "raw": round(float(v), 2), "scaled": None}
                    for ts, v in values.items() if not pd.isna(v)
                ],
            }

        done[key] = {
            "meta": batches_meta[-1],
            "series": {kw["keyword"]: series[kw["keyword"]]
                       for kw in group if kw["keyword"] in series},
            "anchor_copy": _ANCHOR_COPIES[-1],
        }
        save_checkpoint(granularity, done)
        polite_sleep()

    rescale(series, batches_meta)

    if all(b.get("ok") for b in batches_meta):
        clear_checkpoint(granularity)

    payload = {
        "collected_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "geo": cfg.GEO,
        "granularity": granularity,
        "timeframe": timeframe,
        "anchor": anchor["keyword"],
        "note": "raw is normalised within its own batch and is NOT comparable "
                "across keywords. Model on scaled.",
        "batches": batches_meta,
        "series": series,
    }

    print(f"\nHTTP requests used: {HTTP_CALLS['n']} "
          f"({len(groups)} batches x 2, plus retries)")
    print_summary(payload)

    if out_dir:
        write_json(payload, out_dir, granularity)
    if mdb is not None:
        store_mongo.write_interest(mdb, payload)
    if not out_dir and mdb is None:
        print("\nNothing was saved. Pass --mongo, --out DIR, or both.")

    return payload


def rescale(series, batches_meta):
 
    means = {b["batch_id"]: b["anchor_mean"]
             for b in batches_meta if b.get("ok") and b.get("anchor_mean")}
    usable = {b: m for b, m in means.items() if m > 0}
    if not usable:
        print("\n! no usable anchor means -- scaled left null")
        return

    reference = max(usable.values())
    factors = {b: reference / m for b, m in usable.items()}

    for meta in batches_meta:
        if meta.get("batch_id") in factors:
            meta["scale_factor"] = round(factors[meta["batch_id"]], 4)

    for record in series.values():
        if record.get("is_anchor"):
            continue                       # handled below
        factor = factors.get(record["batch_id"])
        if factor is None:
            continue
        for point in record["points"]:
            point["scaled"] = round(point["raw"] * factor, 2)

    anchor_copies = [c for c in _ANCHOR_COPIES if c["batch_id"] in factors]
    anchor_record = next((r for r in series.values() if r.get("is_anchor")), None)
    if anchor_record and anchor_copies:
        by_date = {}
        for copy in anchor_copies:
            f = factors[copy["batch_id"]]
            for p in copy["points"]:
                by_date.setdefault(p["date"], []).append(p["raw"] * f)
        anchor_record["points"] = [
            {"date": d, "raw": None, "scaled": round(sum(v) / len(v), 2)}
            for d, v in sorted(by_date.items())
        ]
        anchor_record["batch_id"] = "anchor-mean"
        anchor_record["note"] = (f"mean of {len(anchor_copies)} rescaled copies; "
                                 f"raw is null because there is no single raw value")

    spread = max(factors.values()) / min(factors.values())
    print(f"\nrescaled {len(factors)} batches "
          f"(reference anchor mean {reference:.1f}, factor spread {spread:.1f}x)")


# --------------------------------------------------------------------------
# output
# --------------------------------------------------------------------------

def print_summary(payload):
    """The eyeball view. A 5-year weekly pull is ~13k points -- this is not."""
    rows = []
    for keyword, rec in payload["series"].items():
        vals = [p["scaled"] for p in rec["points"] if p["scaled"] is not None]
        if not vals:
            vals = [p["raw"] for p in rec["points"]]
        if not vals:
            continue
        rows.append((keyword, rec.get("topic") or "", len(rec["points"]),
                     sum(vals) / len(vals), max(vals), rec["is_anchor"]))

    rows.sort(key=lambda r: r[3], reverse=True)

    print(f"\n{'keyword':<30} {'topic':<14} {'pts':>5} {'mean':>8} {'peak':>8}")
    print("-" * 70)
    for keyword, topic, n, mean, peak, is_anchor in rows:
        mark = " <- anchor" if is_anchor else ""
        print(f"{keyword:<30} {topic:<14} {n:>5} {mean:>8.1f} {peak:>8.1f}{mark}")

    non_anchor = [r for r in rows if not r[5]]
    flat = [r for r in non_anchor if r[3] < 1.0]
    print(f"\n{len(non_anchor)} keywords, {len(flat)} averaging below 1.0")
    if non_anchor and len(flat) / len(non_anchor) > 0.4:
        print("Anchor looks too popular -- it is squashing everything else.")
        print(f"Pick something quieter than '{payload['anchor']}' in config.ANCHOR "
              "and re-run.")
    elif non_anchor:
        print("Anchor looks reasonable.")


def write_json(payload, out_dir, granularity):
    os.makedirs(out_dir, exist_ok=True)
    full = os.path.join(out_dir, f"trends_{granularity}.json")
    with open(full, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)

    # A small companion file you can actually open and read.
    peek = {
        "collected_at": payload["collected_at"],
        "granularity": granularity,
        "anchor": payload["anchor"],
        "keywords": {
            kw: {
                "topic": rec["topic"],
                "points": len(rec["points"]),
                "first": rec["points"][0]["date"] if rec["points"] else None,
                "last": rec["points"][-1]["date"] if rec["points"] else None,
                "sample": rec["points"][-6:],
            }
            for kw, rec in payload["series"].items()
        },
    }
    peek_path = os.path.join(out_dir, f"trends_{granularity}_peek.json")
    with open(peek_path, "w", encoding="utf-8") as fh:
        json.dump(peek, fh, ensure_ascii=False, indent=2)

    size = os.path.getsize(full) / 1024
    print(f"\nwrote {full} ({size:.0f} KB)")
    print(f"wrote {peek_path}  <- open this one first")


def inspect(path):
    """Re-print the summary from a saved JSON file."""
    with open(path, encoding="utf-8") as fh:
        print_summary(json.load(fh))


# --------------------------------------------------------------------------

def collect_related(out_dir=None, mdb=None):
    _, others = load_keywords(mdb)
    tr = make_client()
    today = dt.date.today().isoformat()
    found = {}

    for i, kw in enumerate(others, 1):
        print(f"[{i}/{len(others)}] related: {kw['keyword']}")
        try:
            result = tr.related_queries(kw["keyword"],
                                        timeframe=cfg.TIMEFRAME_DAILY,
                                        geo=cfg.GEO)
        except Exception as exc:                       # noqa: BLE001
            print(f"  ! {exc}")
            polite_sleep()
            continue

        entry = {}
        for kind in ("top", "rising"):
            frame = (result or {}).get(kind)
            if frame is None or len(frame) == 0:
                continue
            entry[kind] = [
                {"query": str(row.get("query", ""))[:200],
                 "value": float(row.get("value") or 0)}
                for _, row in frame.iterrows()
            ]
        if entry:
            found[kw["keyword"]] = {"keyword_id": kw["id"], **entry}
        polite_sleep()

    payload = {"collected_at": today, "geo": cfg.GEO, "related": found}

    rising_total = sum(len(v.get("rising", [])) for v in found.values())
    print(f"\nHTTP requests used: {HTTP_CALLS['n']}")
    print(f"{len(found)}/{len(others)} keywords returned data, "
          f"{rising_total} rising queries")
    if not rising_total:
        print("No rising queries at all. Google often returns none for "
              "low-volume Vietnamese terms -- that is a real finding, and it "
              "means the discovery MVP has no input to work with.")

    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
        path = os.path.join(out_dir, "trends_related.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        print(f"wrote {path}")

    if mdb is not None:
        store_mongo.write_related(mdb, payload)



def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", action="store_true",
                    help="load config.py keywords into Atlas (optional -- the "
                         "collectors do it automatically on first run)")
    ap.add_argument("--backfill", choices=["daily", "weekly"])
    ap.add_argument("--daily", action="store_true", help="the cron job")
    ap.add_argument("--related", action="store_true")
    ap.add_argument("--check-anchor", action="store_true")
    ap.add_argument("--inspect", metavar="FILE",
                    help="re-print the summary from a saved JSON file")
    ap.add_argument("--out", metavar="DIR", help="write JSON here")
    ap.add_argument("--mongo", action="store_true",
                    help="write to MongoDB Atlas (reads MONGODB_URI from .env)")
    ap.add_argument("--no-db", action="store_true",
                    help="do not touch Atlas; pair with --out to inspect JSON")
    ap.add_argument("--mongo-db", metavar="NAME",
                    help="database name (default: MONGODB_DB env, else vietcraft)")
    ap.add_argument("--mongo-health", action="store_true",
                    help="what is in Atlas right now, and did the cron run?")
    ap.add_argument("--purge", action="store_true",
                    help="delete stored points for keywords retired from config.py")
    ap.add_argument("--sync", action="store_true",
                    help="make Atlas keyword list match config.py (implied by --seed)")
    args = ap.parse_args()

    if args.inspect:
        inspect(args.inspect)
        return

    if not any([args.seed, args.sync, args.purge, args.backfill, args.daily,
                args.related, args.check_anchor, args.mongo_health]):
        ap.print_help()
        return

    mdb = None
    if args.mongo or args.mongo_health:
        if store_mongo is None:
            sys.exit('pymongo is missing. pip install "pymongo[srv]"')
        mdb = store_mongo.get_db(db_name=args.mongo_db)

    if args.mongo_health:
        store_mongo.health(mdb)
        if not any([args.seed, args.sync, args.purge, args.backfill,
                    args.daily, args.related, args.check_anchor]):
            return

    if args.seed or args.sync:
        if mdb is None:
            sys.exit("--seed needs --mongo.")
        store_mongo.upsert_keywords(mdb, cfg.SEED_KEYWORDS, cfg.ANCHOR)
    if args.purge:
        if mdb is None:
            sys.exit("--purge needs --mongo.")
        store_mongo.purge_inactive(mdb)
    if args.backfill == "weekly":
        collect("weekly", cfg.TIMEFRAME_WEEKLY, args.out, mdb)
    if args.backfill == "daily":
        collect("daily", cfg.TIMEFRAME_DAILY, args.out, mdb)
    if args.daily:
        # Re-pulling the whole 90-day window each run is deliberate: it
        # self-heals any gap left by a failed night.
        collect("daily", cfg.TIMEFRAME_DAILY, args.out, mdb)
    if args.related:
        collect_related(args.out, mdb)
    if args.check_anchor:
        if mdb is None:
            sys.exit("--check-anchor needs --mongo.")
        rows = mdb.trend_interest.aggregate([
            {"$match": {"granularity": "weekly"}},
            {"$group": {"_id": {"keyword": "$keyword", "topic": "$topic",
                                "is_anchor": "$is_anchor"},
                        "mean": {"$avg": "$scaled"}}},
            {"$sort": {"mean": -1}},
        ])
        for row in rows:
            k = row["_id"]
            mark = " <- anchor" if k.get("is_anchor") else ""
            print(f"{k['keyword']:<30} {k.get('topic') or '':<14} "
                  f"{row['mean']:>8.1f}{mark}")


if __name__ == "__main__":
    main()
