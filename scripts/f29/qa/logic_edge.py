from typing import Any, Dict, List

from bson import ObjectId

from app.core.f29.score import factors, peers, scoring
from app.core.f29.score.price import product_price

CASES = ("no_images", "no_price", "no_variants", "no_reviews", "empty_description", "zero_tags")


def _row(r: Dict[str, Any], key: str) -> Dict[str, Any]:
    return next(f for f in r["factors"] if f["key"] == key)


def cases_of(calc, product: Dict[str, Any], variants: List[Dict[str, Any]]) -> List[str]:
    raw = product.get("description")
    found = {
        "no_images": not factors.image_urls(product),
        "no_price": product_price(variants) is None,
        "no_variants": not variants,
        "no_reviews": peers.product_counts(calc.live_db, product["_id"])[1] == 0,
        "empty_description": not (isinstance(raw, str) and raw.strip()),
        "zero_tags": scoring.count_approved_tags(product, calc.pending_tag_ids()) == 0,
    }
    return [c for c in CASES if found[c]]


def expected(case: str, r: Dict[str, Any]) -> List[str]:
    out = []
    if case == "no_images":
        img = _row(r, "image")
        out += [] if img["state"] == "seller_missing" and img["sub_score"] == 0 else [f"image {img['state']}"]
        out += [] if any(b["field"] == "images" for b in r["blockers"]) else ["no images blocker"]
    if case == "no_price":
        p = _row(r, "price")
        out += [] if p["state"] == "seller_missing" and p["sub_score"] == 0 else [f"price {p['state']}"]
    if case == "no_variants" and not any(b["field"] == "variants.stock" for b in r["blockers"]):
        out.append("no stock blocker")
    if case == "no_reviews" and _row(r, "review")["state"] != "not_applicable":
        out.append(f"review {_row(r, 'review')['state']}")
    if case == "empty_description" and _row(r, "description")["state"] != "seller_missing":
        out.append(f"description {_row(r, 'description')['state']}")
    if case == "zero_tags":
        t = _row(r, "tags")
        out += [] if t["evidence"]["approved"] == 0 and t["sub_score"] == 0 else [f"tags sub {t['sub_score']}"]
    return out


def check(calc, r: Dict[str, Any], edge: Dict[str, Dict[str, Any]]) -> None:
    oid = ObjectId(r["product_id"])
    product = calc.live_db["products"].find_one({"_id": oid})
    for case in cases_of(calc, product, calc._variants(oid)):
        slot = edge.setdefault(case, {"n": 0, "ids": [], "violations": []})
        slot["n"] += 1
        slot["ids"] = (slot["ids"] + [r["product_id"]])[:5]
        slot["violations"] += [{"product_id": r["product_id"], "problem": p} for p in expected(case, r)]
