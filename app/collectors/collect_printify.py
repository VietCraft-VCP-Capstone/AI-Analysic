import argparse
import json
import os
import sys
import time

# Run from anywhere: every module here does `import config`, which only
# resolves when the script's own directory is the working directory.
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.getcwd())

import requests

import config as cfg  # noqa: F401  -- imported for its .env side effect

try:
    import store_mongo
except ImportError:
    store_mongo = None

API = "https://api.printify.com/v1"

import re

PATTERNS = [
    # Drinkware (mugs, tumblers, bottles)
    (r"\b(mug|mugs|tumbler|tumblers|cup|cups|bottle|bottles|glass|flask|coaster)\b", "mug"),
    # Bags and Totes (checked before poster so 'canvas tote bag' maps to tote)
    (r"\b(tote|totes|backpack|drawstring|duffle|waist\s*bag|handbag|cosmetic\s*bag|shoulder\s*bag)\b", "tote"),
    # T-shirts & Tops (word boundary prevents matching 'steel')
    (r"\b(t-shirt|t-shirts|tshirt|tshirts|tee|tees|tank\s*top|hoodie|sweatshirt|crewneck|longsleeve|crop\s*top|polo)\b", "tshirt"),
    # Posters & Wallart
    (r"\b(poster|posters|canvas|metal\s*print|acrylic\s*print|wood\s*print|wall\s*art|tapestry)\b", "poster"),
]

# One print provider per blueprint is plenty for a cost floor.
PROVIDERS_PER_BLUEPRINT = 1


def get(path):
    resp = requests.get(
        f"{API}{path}",
        headers={"Authorization": f"Bearer {os.environ['PRINTIFY_TOKEN']}",
                 "User-Agent": "VietCraft-Research/1.0"},
        timeout=30,
    )
    if resp.status_code == 429:
        wait = int(resp.headers.get("Retry-After", 30))
        print(f"  . rate limited, waiting {wait}s")
        time.sleep(wait)
        return get(path)
    resp.raise_for_status()
    return resp.json()


def classify(title):
    low = (title or "").lower()
    for pattern, product_type in PATTERNS:
        if re.search(pattern, low):
            return product_type
    return None


def write_mongo(mdb, rows):
    """One doc per variant, keyed so re-running is idempotent."""
    import datetime as dt
    from pymongo import UpdateOne, ASCENDING

    mdb.printify_variant.create_index(
        [("blueprint_id", ASCENDING), ("print_provider_id", ASCENDING),
         ("variant_id", ASCENDING)],
        unique=True, name="uniq_variant")
    mdb.printify_variant.create_index([("product_type", ASCENDING)],
                                      name="by_product_type")

    now = dt.datetime.now(dt.timezone.utc)
    ops = [
        UpdateOne(
            {"blueprint_id": r[0], "print_provider_id": r[2], "variant_id": r[4]},
            {"$set": {"blueprint_title": r[1], "print_provider_title": r[3],
                      "variant_title": r[5], "color": r[6], "size": r[7],
                      "cost_cents": r[8], "product_type": r[9],
                      "fetched_at": now}},
            upsert=True)
        for r in rows
    ]
    for i in range(0, len(ops), 1000):
        mdb.printify_variant.bulk_write(ops[i:i + 1000], ordered=False)
    print(f"mongo: {len(ops)} variants upserted")


def summarise(rows):
    """Cost floor per product type -- the number the pricing model needs."""
    by_type = {}
    for r in rows:
        if r[8] is None:
            continue
        by_type.setdefault(r[9], []).append(r[8])

    print(f"\n{'product type':<12} {'variants':>9} {'min cost':>10} "
          f"{'median':>9} {'max':>9}")
    print("-" * 54)
    for ptype, costs in sorted(by_type.items()):
        costs.sort()
        mid = costs[len(costs) // 2]
        print(f"{ptype:<12} {len(costs):>9} {costs[0]/100:>9.2f}$ "
              f"{mid/100:>8.2f}$ {costs[-1]/100:>8.2f}$")
    print("\nThis is what YOU pay the print provider. Any suggested retail")
    print("price must sit above it, or the seller loses money on every order.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mongo", action="store_true", help="write to MongoDB Atlas")
    ap.add_argument("--mongo-db", metavar="NAME", help="database name")
    ap.add_argument("--out", metavar="DIR", help="also write JSON here")
    args = ap.parse_args()

    if not os.environ.get("PRINTIFY_TOKEN"):
        sys.exit("Set PRINTIFY_TOKEN in .env (Printify -> Account -> "
                 "Connections -> Generate token).")

    print("fetching blueprints...")
    blueprints = get("/catalog/blueprints.json")
    picked = [(b, classify(b.get("title"))) for b in blueprints]
    picked = [(b, t) for b, t in picked if t]
    print(f"{len(picked)} of {len(blueprints)} blueprints match the four product types")

    rows = []
    for i, (bp, product_type) in enumerate(picked, 1):
        bp_id, bp_title = bp["id"], bp.get("title", "")
        print(f"[{i}/{len(picked)}] {bp_title} ({product_type})")

        try:
            providers = get(f"/catalog/blueprints/{bp_id}/print_providers.json")
        except Exception as exc:                       # noqa: BLE001
            print(f"  ! {exc}")
            continue

        for provider in providers[:PROVIDERS_PER_BLUEPRINT]:
            pp_id, pp_title = provider["id"], provider.get("title", "")
            time.sleep(0.8)
            try:
                payload = get(
                    f"/catalog/blueprints/{bp_id}/print_providers/{pp_id}/variants.json"
                )
            except Exception as exc:                   # noqa: BLE001
                print(f"  ! variants: {exc}")
                continue

            for variant in payload.get("variants", []):
                options = variant.get("options", {}) or {}
                rows.append((
                    bp_id, bp_title, pp_id, pp_title,
                    variant.get("id"), variant.get("title"),
                    options.get("color"), options.get("size"),
                    variant.get("cost"),        # minor units: 1992 == $19.92
                    product_type,
                ))
        time.sleep(0.8)

    if not rows:
        sys.exit("No variants collected.")

    summarise(rows)

    if args.out:
        os.makedirs(args.out, exist_ok=True)
        path = os.path.join(args.out, "printify_variants.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump([{
                "blueprint_id": r[0], "blueprint_title": r[1],
                "print_provider_id": r[2], "print_provider_title": r[3],
                "variant_id": r[4], "variant_title": r[5],
                "color": r[6], "size": r[7],
                "cost_cents": r[8], "product_type": r[9],
            } for r in rows], fh, ensure_ascii=False, indent=2)
        print(f"\nwrote {path}")

    if args.mongo:
        if store_mongo is None:
            sys.exit('pymongo missing. pip install pymongo dnspython')
        write_mongo(store_mongo.get_db(db_name=args.mongo_db), rows)
    if not any([args.out, args.mongo]):
        print("\nNothing saved. Pass --mongo, --out DIR, or both.")


if __name__ == "__main__":
    main()
