#!/usr/bin/env python3
"""
Inspect what is actually in Atlas. Costs zero Google Trends quota.

    python verify_data.py --integrity        # is raw -> scaled sound?
    python verify_data.py --quality          # gaps, zeros, coverage
    python verify_data.py --eligibility      # which keywords can feed a model
    python verify_data.py --discovery-stats  # is there enough to build discovery?
    python verify_data.py --all

Written to be run before extending anything. A pipeline you have not
inspected is a pipeline you cannot defend.
"""

import argparse
import os
import sys
import re
from collections import defaultdict

# Run from anywhere: every module here does `import config`, which only
# resolves when the script's own directory is the working directory.
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.getcwd())

import config as cfg
import store_mongo


# ---------------------------------------------------------------------------
# P0.3 -- integrity of the rescaling step
# ---------------------------------------------------------------------------

def check_integrity(db):
    """
    Verify scaled = raw x (one constant factor per batch).

    This is the step everything downstream trusts. Google normalises 0-100
    inside each request, so points from different batches are not comparable
    until the anchor rescale puts them on one scale. If the factor is not
    constant within a batch, the rescale is broken and every cross-keyword
    comparison -- Gap Score above all -- is meaningless.
    """
    print("=" * 68)
    print("INTEGRITY -- raw -> scaled")
    print("=" * 68)

    problems = 0
    for gran in ("weekly", "daily"):
        batches = db.trend_interest.distinct("batch_id", {"granularity": gran})
        if not batches:
            print(f"\n{gran}: no data")
            continue

        print(f"\n{gran}: {len(batches)} batches")
        for batch_id in batches:
            docs = list(db.trend_interest.find(
                {"batch_id": batch_id, "granularity": gran,
                 "is_anchor": False,        # anchor is an average, no raw
                 "raw": {"$gt": 0}, "scaled": {"$ne": None}},
                {"raw": 1, "scaled": 1, "keyword": 1, "_id": 0},
            ))
            if not docs:
                continue

            ratios = {round(d["scaled"] / d["raw"], 3) for d in docs}
            if len(ratios) > 1:
                spread = max(ratios) / min(ratios)
                # Rounding to 2dp on both raw and scaled makes tiny values
                # noisy; only flag a genuinely inconsistent factor.
                if spread > 1.05:
                    print(f"  ! {batch_id}: factor not constant, "
                          f"{len(ratios)} distinct values, spread {spread:.2f}x")
                    problems += 1

    null_scaled = db.trend_interest.count_documents({"scaled": None})
    if null_scaled:
        print(f"\n! {null_scaled} points have scaled=None "
              f"(their batch had no usable anchor mean)")
        problems += 1

    anchors = db.trend_interest.distinct("keyword", {"is_anchor": True})
    print(f"\nanchor in stored data: {anchors}")
    if len(anchors) != 1:
        print("! expected exactly one anchor -- more than one means batches "
              "were rescaled against different references and are not "
              "comparable")
        problems += 1

    print(f"\n{'PASS' if problems == 0 else f'{problems} PROBLEM(S)'}")
    return problems == 0


# ---------------------------------------------------------------------------
# P0.4 -- data quality
# ---------------------------------------------------------------------------

EXPECTED_STEP = {"weekly": 7, "daily": 1}


def check_quality(db):
    """Gaps, duplicates, and how much of each series is actually non-zero."""
    print("=" * 68)
    print("QUALITY")
    print("=" * 68)

    total = db.trend_interest.count_documents({})
    keywords = db.trend_interest.distinct("keyword")
    print(f"\n{total:,} points across {len(keywords)} keywords")

    for gran in ("weekly", "daily"):
        n = db.trend_interest.count_documents({"granularity": gran})
        if not n:
            print(f"\n{gran:<8} MISSING -- run --backfill {gran}")
            continue
        first = db.trend_interest.find_one({"granularity": gran},
                                           sort=[("observed_on", 1)])
        last = db.trend_interest.find_one({"granularity": gran},
                                          sort=[("observed_on", -1)])
        kws = len(db.trend_interest.distinct("keyword", {"granularity": gran}))
        per_kw = n / kws if kws else 0
        print(f"\n{gran:<8} {n:>7,} points  {kws} keywords  "
              f"{per_kw:.0f} per keyword")
        print(f"         {first['observed_on'].date()} -> "
              f"{last['observed_on'].date()}")

        # Date gaps, checked on the anchor since it appears in every batch.
        anchor_dates = sorted(
            d["observed_on"].date() for d in db.trend_interest.find(
                {"granularity": gran, "is_anchor": True},
                {"observed_on": 1, "_id": 0})
        )
        step = EXPECTED_STEP[gran]
        gaps = [
            (a, b) for a, b in zip(anchor_dates, anchor_dates[1:])
            if (b - a).days != step
        ]
        if gaps:
            print(f"         ! {len(gaps)} gap(s), first: "
                  f"{gaps[0][0]} -> {gaps[0][1]}")
        else:
            print("         no gaps")

    # Non-zero ratio is the number that matters. A series of zeros still has
    # the right point count; it is still useless to a model.
    print("\nnon-zero ratio (weekly)")
    print("-" * 68)
    rows = list(db.trend_interest.aggregate([
        {"$match": {"granularity": "weekly"}},
        {"$group": {
            "_id": {"keyword": "$keyword", "topic": "$topic"},
            "n": {"$sum": 1},
            "nonzero": {"$sum": {"$cond": [{"$gt": ["$scaled", 0]}, 1, 0]}},
            "mean": {"$avg": "$scaled"},
            "peak": {"$max": "$scaled"},
        }},
    ]))
    for r in rows:
        r["ratio"] = r["nonzero"] / r["n"] if r["n"] else 0
        steady = r["ratio"] >= FORECAST_ELIGIBILITY["min_nonzero_ratio"]
        seasonal = r["peak"] >= FORECAST_ELIGIBILITY["min_peak_scaled"]
        r["profile"] = ("steady" if steady else
                        "seasonal" if seasonal else "flat")
    rows.sort(key=lambda r: (r["profile"] != "flat", r["ratio"]))

    print(f"{'keyword':<26} {'topic':<13} {'nz':>5} {'mean':>7} {'peak':>7}  profile")
    print("-" * 68)
    for r in rows[:14]:
        k = r["_id"]
        print(f"{k['keyword']:<26} {k.get('topic') or '':<13} "
              f"{r['ratio']:>5.2f} {r['mean']:>7.1f} {r['peak']:>7.1f}  {r['profile']}")
    if len(rows) > 14:
        print(f"... {len(rows) - 14} more")

    flat = [r for r in rows if r["profile"] == "flat"]
    seasonal = [r for r in rows if r["profile"] == "seasonal"]
    print(f"\n{len(flat)} flat, {len(seasonal)} seasonal, "
          f"{len(rows) - len(flat) - len(seasonal)} steady")
    if flat:
        print("Flat = low non-zero ratio AND low peak. Vietnamese searchers "
              "do not use these terms; drop or reword them.")
    if seasonal:
        print("Seasonal = mostly zero but spikes hard. Not dead -- these are "
              "the best STL inputs in the set.")
    return rows


# ---------------------------------------------------------------------------
# P1.4 -- forecast eligibility
# ---------------------------------------------------------------------------

FORECAST_ELIGIBILITY = {
    "min_weekly_points": 104,   # 2 full periods, required by STL(period=52)
    "min_daily_points":   60,   # floor for auto_arima to fit anything useful
    "min_nonzero_ratio": 0.30,  # steady series must be mostly non-zero...
    "min_peak_scaled":   30.0,  # ...UNLESS they spike hard: that is seasonal
    "min_mean_scaled":    1.0,  # below this the series is rounding noise
}

# A series that is zero 80% of the year but hits 300 at Tet is not dead --
# it is the strongest seasonal signal in the set, and exactly what STL is
# for. The first cut of this filter threw those out along with the genuinely
# flat ones. So: a keyword passes if EITHER it is mostly non-zero (steady)
# OR its peak is high (seasonal). Only low-ratio AND low-peak is dead.


def check_eligibility(db, write=False):
    """
    Decide which keywords a model is allowed to consume.

    Deliberately separate from `active`. A keyword can be worth collecting
    (it is a real market signal) while still being unfit for ARIMA, because
    the series is mostly zeros. Conflating the two is how a forecast on a
    flat-zero series ends up in a dashboard.
    """
    print("=" * 68)
    print("FORECAST ELIGIBILITY")
    print("=" * 68)
    for key, value in FORECAST_ELIGIBILITY.items():
        print(f"  {key:<20} {value}")

    stats = defaultdict(dict)
    for gran in ("weekly", "daily"):
        for r in db.trend_interest.aggregate([
            {"$match": {"granularity": gran}},
            {"$group": {
                "_id": "$keyword",
                "n": {"$sum": 1},
                "nonzero": {"$sum": {"$cond": [{"$gt": ["$scaled", 0]}, 1, 0]}},
                "mean": {"$avg": "$scaled"},
                "peak": {"$max": "$scaled"},
            }},
        ]):
            stats[r["_id"]][gran] = r

    eligible, rejected = [], []
    for keyword, by_gran in stats.items():
        w = by_gran.get("weekly", {})
        d = by_gran.get("daily", {})
        wn, dn = w.get("n", 0), d.get("n", 0)
        ratio = (w.get("nonzero", 0) / wn) if wn else 0
        mean = w.get("mean") or 0
        peak = w.get("peak") or 0

        steady = ratio >= FORECAST_ELIGIBILITY["min_nonzero_ratio"]
        seasonal = peak >= FORECAST_ELIGIBILITY["min_peak_scaled"]

        reasons = []
        if wn < FORECAST_ELIGIBILITY["min_weekly_points"]:
            reasons.append(f"weekly {wn}<{FORECAST_ELIGIBILITY['min_weekly_points']}")
        if dn < FORECAST_ELIGIBILITY["min_daily_points"]:
            reasons.append(f"daily {dn}<{FORECAST_ELIGIBILITY['min_daily_points']}")
        if not steady and not seasonal:
            reasons.append(f"nonzero {ratio:.2f} and peak {peak:.1f}: flat")
        if mean < FORECAST_ELIGIBILITY["min_mean_scaled"] and not seasonal:
            reasons.append(f"mean {mean:.2f}")

        profile = "seasonal" if (seasonal and not steady) else \
                  ("steady" if steady else "flat")
        (eligible if not reasons else rejected).append(
            (keyword, wn, dn, ratio, mean, reasons, profile, peak))

    n_seasonal = sum(1 for e in eligible if e[6] == "seasonal")
    n_steady = sum(1 for e in eligible if e[6] == "steady")
    print(f"\nELIGIBLE: {len(eligible)}  ({n_steady} steady, {n_seasonal} seasonal)")
    for kw, wn, dn, ratio, mean, _, profile, peak in sorted(
            eligible, key=lambda r: (r[6] != "seasonal", -r[7]))[:20]:
        print(f"  {kw:<26} {profile:<9} nz={ratio:.2f} mean={mean:>6.1f} "
              f"peak={peak:>6.1f}")
    if len(eligible) > 20:
        print(f"  ... {len(eligible) - 20} more")

    print(f"\nNOT ELIGIBLE: {len(rejected)}")
    for kw, _, _, _, _, reasons, _, _ in rejected[:15]:
        print(f"  {kw:<26} {', '.join(reasons)}")
    if len(rejected) > 15:
        print(f"  ... {len(rejected) - 15} more")

    if write:
        for kw, _, _, _, _, _, profile, _ in eligible:
            db.trend_keyword.update_one(
                {"keyword": kw},
                {"$set": {"forecast_eligible": True, "profile": profile}})
        for kw, _, _, _, _, reasons, _, _ in rejected:
            db.trend_keyword.update_one(
                {"keyword": kw},
                {"$set": {"forecast_eligible": False, "profile": "flat",
                          "ineligible_reason": ", ".join(reasons)}})
        print(f"\nwrote forecast_eligible for {len(eligible) + len(rejected)} keywords")

    if not eligible:
        print("\nNothing is eligible. Most likely --backfill daily has not "
              "run yet, so every keyword fails the daily-points test.")
    return eligible, rejected


# ---------------------------------------------------------------------------
# P1.3 -- the go/no-go number for discovery
# ---------------------------------------------------------------------------

def normalise(query):
    q = query.lower().strip()
    q = re.sub(r"\s+", " ", q)
    return re.sub(r"[^\w\s/+áàảãạăắằẳẵặâấầẩẫậéèẻẽẹêếềểễệ"
                  r"íìỉĩịóòỏõọôốồổỗộơớờởỡợúùủũụưứừửữựýỳỷỹỵđ]", "", q).strip()


def check_discovery_stats(db):
    """
    Count what discovery would have to work with. Run --related first.

    This is the gate. Build the discovery pipeline only if these numbers say
    there is something to discover.
    """
    print("=" * 68)
    print("DISCOVERY INPUT")
    print("=" * 68)

    seeds = db.trend_keyword.count_documents({"active": True})
    total = db.trend_related.count_documents({})
    rising = list(db.trend_related.find({"kind": "rising"}))

    if total == 0:
        print("\ntrend_related is empty. Run:")
        print("  python collect_trends.py --related --mongo --out ./data")
        print("\nCost: 44 calls x 2 = 88 HTTP requests. Consider splitting "
              "over two days.")
        return None

    with_rising = len({r["seed_keyword"] for r in rising})
    canonical = {normalise(r["query"]) for r in rising}
    canonical.discard("")

    known = {k.lower() for k in db.trend_keyword.distinct("keyword")}
    novel = {c for c in canonical if c not in known}

    def has(words, text):
        return any(w in text for w in words)

    product = {c for c in novel if has(cfg.PRODUCT_WORDS, c)}
    relevant = {c for c in product if not has(cfg.NON_COMMERCIAL_WORDS, c)}

    print(f"\n{'Seed keywords:':<32}{seeds:>6}")
    print(f"{'With rising queries:':<32}{with_rising:>6}")
    print(f"{'Total rising queries:':<32}{len(rising):>6}")
    print(f"{'Unique after normalising:':<32}{len(canonical):>6}")
    print(f"{'Novel (not already tracked):':<32}{len(novel):>6}")
    print(f"{'Contains a product word:':<32}{len(product):>6}")
    print(f"{'POD-relevant candidates:':<32}{len(relevant):>6}")

    if relevant:
        print("\nTop candidates by rising value:")
        by_value = sorted(
            ((normalise(r["query"]), r.get("value") or 0, r["seed_keyword"])
             for r in rising if normalise(r["query"]) in relevant),
            key=lambda x: -x[1])[:15]
        seen = set()
        for q, v, seed in by_value:
            if q in seen:
                continue
            seen.add(q)
            print(f"  {q:<38} {v:>8.0f}  <- {seed}")

    print("\n" + "-" * 68)
    n = len(relevant)
    if n >= 60:
        print(f"{n} usable candidates. Discovery MVP is worth building.")
    elif n >= 20:
        print(f"{n} usable candidates. Enough for a demo, thin for a "
              f"continuous pipeline. Build the scorer and the review CLI, "
              f"skip the budgeted rotation.")
    else:
        print(f"Only {n} usable candidates. Google Trends VN does not return "
              f"enough related queries for low-volume Vietnamese terms.")
        print("This is a real finding, not a failure -- report it, and put "
              "the effort into STL/ARIMA/Gap Score instead. Etsy tags would "
              "be the stronger discovery source if that app is approved.")
    return len(relevant)
    


# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--integrity", action="store_true")
    ap.add_argument("--quality", action="store_true")
    ap.add_argument("--eligibility", action="store_true")
    ap.add_argument("--write-eligibility", action="store_true",
                    help="persist forecast_eligible onto trend_keyword")
    ap.add_argument("--discovery-stats", action="store_true")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--mongo-db", metavar="NAME")
    args = ap.parse_args()

    if not any([args.integrity, args.quality, args.eligibility,
                args.discovery_stats, args.all, args.write_eligibility]):
        ap.print_help()
        return

    db = store_mongo.get_db(db_name=args.mongo_db)

    if args.integrity or args.all:
        check_integrity(db)
        print()
    if args.quality or args.all:
        check_quality(db)
        print()
    if args.eligibility or args.write_eligibility or args.all:
        check_eligibility(db, write=args.write_eligibility)
        print()
    if args.discovery_stats or args.all:
        check_discovery_stats(db)


if __name__ == "__main__":
    main()