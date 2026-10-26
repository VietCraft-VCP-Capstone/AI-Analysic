import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from fastapi import APIRouter

from app.api.v1._live import la_shop_live
from app.api.v1._live_listing import conversion_live
from app.api.v1._mart import db
from app.api.v1._template import CurrentShop, forbidden, insufficient, mart_not_ready, meta_from_record, not_found, ok

router = APIRouter()

MART = "mart_listing_quality"
TOI_THIEU_VIEW = 30      # dưới ngưỡng này thì tỉ lệ % là nhiễu


@router.get("/api/analytics/listings/{id}/conversion", tags=["F28 · Hạt"])
def conversion(id: str, shop_id: str = CurrentShop):
    if la_shop_live(shop_id):
        kq = conversion_live(id, shop_id, TOI_THIEU_VIEW)
        return ok(*kq) if isinstance(kq, tuple) else kq

    l = db()["listings"].find_one({"listing_id": id}, {"_id": 0, "shop_id": 1, "title": 1})
    if l is None:
        not_found("listing")
    if l.get("shop_id") != shop_id:
        forbidden()

    coll = db()[MART]
    if coll.estimated_document_count() == 0:
        mart_not_ready(MART)

    r = coll.find_one({"listing_id": id}, {"_id": 0})
    if r is None:
        return insufficient(
            f"Listing `{id}` chưa có lượt xem nào trong 90 ngày gần nhất nên chưa dựng được phễu")

    meta = meta_from_record(r, scope="listing", scope_id=id, collection=MART,
                            mode="seed_demo", sample_size=r["funnel"]["views"])

    if r["funnel"]["views"] < TOI_THIEU_VIEW:
        return insufficient(
            f"Listing mới có {r['funnel']['views']} lượt xem trong 90 ngày, "
            f"cần tối thiểu {TOI_THIEU_VIEW} thì tỉ lệ % mới có nghĩa", meta)

    return ok({
        "listing_id": id,
        "title": l.get("title"),
        "funnel": r["funnel"],
        "view_to_cart_pct": r["view_to_cart_pct"],
        "cart_to_order_pct": r["cart_to_order_pct"],
        "view_to_order_pct": r["view_to_order_pct"],
        "category_avg_pct": r["category_avg_pct"],
        "category_id": r.get("category_id"),
        "cr_index": r["cr_index"],
        "weakest_step": r["weakest_step"],
        "tips": r.get("tips") or [],
        "window": {"from": r.get("window_from"), "to": r.get("window_to")},
    }, meta)
