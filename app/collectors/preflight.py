#!/usr/bin/env python3
"""
Check everything that can be checked without spending Google Trends quota.

    python preflight.py

Run this first, every time, before any collector. Each failure below is one
you would otherwise discover halfway through a backfill -- after the requests
are already gone and the rate limit is already ticking.
"""

import importlib
import os
import sys

# Run from anywhere: every module here does `import config`, which only
# resolves when the script's own directory is the working directory.
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.getcwd())

CHECKS = []


def check(name):
    def wrap(fn):
        CHECKS.append((name, fn))
        return fn
    return wrap


class Fail(Exception):
    """Stops the run. Anything raised here means do not collect yet."""


class Warn(Exception):
    """Worth knowing, not worth stopping for."""


# ---------------------------------------------------------------------------

@check("Python packages")
def _packages():
    required = {
        "trendspy": "trendspy",
        "pandas": "pandas",
        "pymongo": "pymongo",
        "dns": "dnspython",
        "requests": "requests",
        "dotenv": "python-dotenv",
    }
    missing = []
    for module, package in required.items():
        try:
            importlib.import_module(module)
        except ImportError:
            missing.append(package)
    if missing:
        raise Fail(f"missing: {' '.join(missing)}\n"
                   f"     pip install {' '.join(missing)}")
    import trendspy
    return f"trendspy {getattr(trendspy, '__version__', '?')}, all present"


@check(".env file")
def _env():
    if not os.path.exists(".env"):
        raise Fail("no .env -- run: cp .env.example .env, then fill it in")

    import config as cfg
    if not hasattr(cfg, "SEED_KEYWORDS"):
        raise Fail("config.py loaded but has no SEED_KEYWORDS")

    uri = os.environ.get("MONGODB_URI", "")
    if not uri:
        raise Fail("MONGODB_URI is empty in .env")
    if "REPLACE_ME" in uri or "<password>" in uri:
        raise Fail("MONGODB_URI still has the placeholder password")

    # A password containing @ / : # ? breaks URI parsing unless encoded, and
    # the resulting error names the wrong host, which is very confusing.
    if "://" not in uri:
        raise Fail("MONGODB_URI is not a valid connection string")

    # Only look at credentials when there actually are any -- a URI with no
    # '@' has no user:pass section, and splitting on it grabs the host.
    netloc = uri.split("://", 1)[1]
    if "@" in netloc:
        password = netloc.rsplit("@", 1)[0].partition(":")[2]
        if any(c in password for c in "/:#?@"):
            raise Warn("password contains a character that needs "
                       "URL-encoding (/ : # ? @) -- letters and digits only "
                       "is safest, otherwise the URI parses wrong and the "
                       "error names the wrong host")

    db_name = os.environ.get("MONGODB_DB", "data-collection")
    return f"MONGODB_DB={db_name}"



@check("Atlas connection + permissions")
def _atlas():
    import store_mongo
    db = store_mongo.get_db()          # raises with a readable message
    name = db.name

    # A read proves connection; a write proves the grant. Only the write
    # catches a user with readWrite on the wrong database -- the exact
    # failure mode when the database gets renamed.
    db.command("ping")
    # db["..."] not db.__getattr__: PyMongo refuses attribute access for
    # names starting with an underscore.
    probe = db["_preflight"]
    probe.update_one({"_id": "probe"}, {"$set": {"ok": True}}, upsert=True)
    probe.delete_one({"_id": "probe"})
    return f"read + write OK on '{name}'"


@check("config.py sanity")
def _config():
    import config as cfg

    problems = []
    keywords = [k for k, _, _ in cfg.SEED_KEYWORDS]

    duplicates = {k for k in keywords if keywords.count(k) > 1}
    if duplicates:
        problems.append(f"duplicate keywords: {', '.join(sorted(duplicates))}")

    # The anchor rides in every batch, so having it in SEED_KEYWORDS too just
    # means paying for the same series twice.
    if cfg.ANCHOR in keywords:
        problems.append(f"ANCHOR '{cfg.ANCHOR}' is also in SEED_KEYWORDS "
                        f"-- remove it, it is collected either way")

    if not 1 <= cfg.BATCH_SIZE <= 4:
        problems.append(f"BATCH_SIZE={cfg.BATCH_SIZE}; Google allows 5 terms "
                        f"per request and the anchor takes one, so 4 is the max")

    if getattr(cfg, "TRENDSPY_RETRIES", None) != 1:
        problems.append("TRENDSPY_RETRIES should be 1 -- above that it nests "
                        "under our own retry loop and multiplies requests")

    if cfg.SLEEP_MIN < 10:
        problems.append(f"SLEEP_MIN={cfg.SLEEP_MIN}s is aggressive for "
                        f"Google Trends; 15s+ is safer")

    if cfg.TZ_OFFSET != -420:
        problems.append(f"TZ_OFFSET={cfg.TZ_OFFSET}; Vietnam (UTC+7) is -420")

    if problems:
        raise Fail("\n     ".join(problems))
    return f"{len(keywords)} keywords, anchor '{cfg.ANCHOR}', batch {cfg.BATCH_SIZE}"


@check("Trends client")
def _trends():
    import config as cfg
    from trendspy import Trends
    client = Trends(language="en", tzs=cfg.TZ_OFFSET,
                    request_delay=cfg.REQUEST_DELAY,
                    max_retries=cfg.TRENDSPY_RETRIES)
    if not hasattr(client, "session"):
        raise Fail("trendspy API changed -- no .session, the HTTP counter "
                   "in collect_trends.py will not work")
    return "constructs OK (no network call made)"


@check("Request budget")
def _budget():
    import config as cfg
    batches = -(-len(cfg.SEED_KEYWORDS) // cfg.BATCH_SIZE)
    # Verified by counting session.get: one logical call is two HTTP requests,
    # because Google returns a token first and the data second.
    print(f"\n     {'command':<26}{'calls':>7}{'HTTP':>7}{'minutes':>9}")
    print("     " + "-" * 49)
    pace = (cfg.SLEEP_MIN + cfg.SLEEP_MAX) / 2
    for label, calls in (("--backfill weekly", batches),
                         ("--backfill daily", batches),
                         ("--daily (cron)", batches),
                         ("--related", len(cfg.SEED_KEYWORDS))):
        print(f"     {label:<26}{calls:>7}{calls * 2:>7}{calls * pace / 60:>9.0f}")
    return "counts printed above"


@check("Existing data")
def _existing():
    import store_mongo
    db = store_mongo.get_db()
    points = db.trend_interest.count_documents({})
    if points == 0:
        return "database empty -- start with --backfill weekly"

    keywords = len(db.trend_interest.distinct("keyword"))
    anchors = db.trend_interest.distinct("keyword", {"is_anchor": True})
    parts = [f"{points:,} points, {keywords} keywords"]

    import config as cfg
    if len(anchors) > 1:
        raise Warn(f"{len(anchors)} anchors in stored data: {anchors}. "
                   f"Batches were rescaled against different references and "
                   f"are not comparable. Run: --sync --purge --mongo")
    if anchors and anchors[0] != cfg.ANCHOR:
        raise Warn(f"stored anchor '{anchors[0]}' != config '{cfg.ANCHOR}'. "
                   f"Run: --sync --purge --mongo, then backfill again")

    for granularity in ("weekly", "daily"):
        n = db.trend_interest.count_documents({"granularity": granularity})
        parts.append(f"{granularity} {n:,}")
    return " | ".join(parts)


# ---------------------------------------------------------------------------

def main():
    print("PREFLIGHT -- nothing here spends Google Trends quota\n")
    failures = warnings = 0

    for name, fn in CHECKS:
        try:
            detail = fn()
            print(f"  OK    {name:<28} {detail}")
        except Warn as exc:
            print(f"  WARN  {name:<28} {exc}")
            warnings += 1
        except Fail as exc:
            print(f"  FAIL  {name:<28} {exc}")
            failures += 1
        except SystemExit as exc:
            print(f"  FAIL  {name:<28} {exc}")
            failures += 1
        except Exception as exc:                       # noqa: BLE001
            print(f"  FAIL  {name:<28} {type(exc).__name__}: {exc}")
            failures += 1

    print()
    if failures:
        print(f"{failures} failure(s). Fix these before collecting -- "
              f"a failed backfill still spends the requests.")
        sys.exit(1)
    if warnings:
        print(f"{warnings} warning(s). Readable, but check them.")
    print("Ready. Next:  python collect_trends.py --backfill weekly "
          "--mongo --out ./data")


if __name__ == "__main__":
    main()
