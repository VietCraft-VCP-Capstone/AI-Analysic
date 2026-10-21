import json
from datetime import datetime
from pathlib import Path

from bson import ObjectId

from app.api.v1._live import LOC_SP_THAT, db_live

from .normalize import norm
from .types import ListingInput

_MAP = json.loads((Path(__file__).parent / "data" / "category_map.json").read_text("utf-8"))["vietcraft"]
GROUPS = {norm(k): v for k, v in _MAP.items()}
FIELDS = {"title": 1, "description": 1, "tags": 1, "materials": 1, "categories": 1, "images": 1,
          "shop_id": 1, "updated_at": 1}
PEER_CAP = 300


def group_of(category) -> str | None:
    return GROUPS.get(norm(category)) if category else None


def _oid(x):
    try:
        return ObjectId(x)
    except Exception:
        return None


def _price(x):
    try:
        return float(str(x)) if x is not None else None
    except (TypeError, ValueError):
        return None


def _prices(ids) -> dict:
    out = {}
    for v in db_live()["product_variants"].find({"product_id": {"$in": ids}}, {"product_id": 1, "retail_price": 1, "is_active": 1}):
        p = _price(v.get("retail_price"))
        if v.get("is_active", True) and p and p > 0:
            out.setdefault(v["product_id"], []).append(p)
    return {k: sorted(v)[len(v) // 2] for k, v in out.items()}


def _input(p: dict, price=None) -> ListingInput:
    category = (p.get("categories") or [None])[0]
    return ListingInput(
        title=p.get("title") or "", description=p.get("description") or "",
        tags=list(p.get("tags") or []), materials=list(p.get("materials") or []),
        category=category, group=group_of(category), price=price,
        image_urls=[u for u in p.get("images") or [] if isinstance(u, str)],
        product_id=str(p["_id"]), seller_id=str(p.get("shop_id")),
    )


def _with_prices(products) -> list[ListingInput]:
    prices = _prices([p["_id"] for p in products]) if products else {}
    return [_input(p, prices.get(p["_id"])) for p in products]


def load_listing(product_id) -> ListingInput | None:
    oid = _oid(product_id)
    p = db_live()["products"].find_one({"_id": oid, **LOC_SP_THAT}, FIELDS) if oid else None
    return _with_prices([p])[0] if p else None


def shop_listings(shop_id) -> list[ListingInput]:
    oid = _oid(shop_id)
    return _with_prices(list(db_live()["products"].find({"shop_id": oid, **LOC_SP_THAT}, FIELDS))) if oid else []


def _updated(p) -> datetime:
    return p["updated_at"] if isinstance(p.get("updated_at"), datetime) else datetime.min


def _group(p) -> str | None:
    return group_of((p.get("categories") or [None])[0])


def peer_heads(group, exclude=None) -> list[tuple[str, datetime]]:
    rows = [p for p in db_live()["products"].find(LOC_SP_THAT, {"categories": 1, "updated_at": 1})
            if str(p["_id"]) != exclude and (group is None or _group(p) == group)]
    rows.sort(key=_updated, reverse=True)
    return [(str(p["_id"]), _updated(p)) for p in rows[:PEER_CAP]]


def load_many(product_ids) -> dict[str, ListingInput]:
    oids = [o for o in map(_oid, product_ids) if o is not None]
    rows = db_live()["products"].find({"_id": {"$in": oids}}, FIELDS) if oids else []
    return {str(p["_id"]): _input(p) for p in rows}


def updated_since(products_after: dict) -> list[str]:
    rows = db_live()["products"].find(LOC_SP_THAT, {"_id": 1, "updated_at": 1})
    return [str(p["_id"]) for p in rows
            if str(p["_id"]) not in products_after or (p.get("updated_at") and p["updated_at"] > products_after[str(p["_id"])])]


def tag_sets() -> tuple[set[str], set[str]]:
    rows = db_live()["tags"].find({}, {"name": 1, "status": 1, "review_status": 1})
    rows = [t for t in rows if t.get("name")]
    pending = {t["name"] for t in rows if "pending" in (t.get("status"), t.get("review_status"))}
    approved = {t["name"] for t in rows if t.get("status") == "active" or t.get("review_status") == "approved"}
    return pending, approved - pending
