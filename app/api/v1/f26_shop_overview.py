
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from fastapi import APIRouter

from app.api.v1._mart import (
    cua_so, cua_so_truoc, db, doc_khoang, gop, ngay_moi_nhat,
    phan_tram_thay_doi, tien, ty_le_chuyen_doi,
)
from app.api.v1._live import la_shop_live
from app.api.v1._live_overview import overview_live
from app.api.v1._template import CurrentShop, build_meta, insufficient, mart_not_ready, ok

router = APIRouter()

TOI_THIEU_NGAY = 7          # dưới ngưỡng này thì không kết luận gì
SO_TOP_PRODUCT = 5


@router.get("/api/analytics/shop/overview", tags=["F26 · Hiếu"])
def shop_overview(shop_id: str = CurrentShop, timeRange: str = "30d"):
    so_ngay = doc_khoang(timeRange)

    if la_shop_live(shop_id):
        return overview_live(shop_id, so_ngay, timeRange)

    moi_nhat = ngay_moi_nhat({"shop_id": shop_id})
    if moi_nhat is None:
        mart_not_ready("listing_daily")

    tu, den = cua_so(moi_nhat, so_ngay)
    tu_truoc, den_truoc = cua_so_truoc(tu, so_ngay)

    cot = {"views": "$views", "carts": "$add_to_carts", "orders": "$orders",
           "units": "$units_sold", "revenue_vnd": "$revenue_vnd"}
    tong = {k: {"$sum": v} for k, v in cot.items()}

    (kq,) = db()["listing_daily"].aggregate([
        {"$match": {"shop_id": shop_id, "date": {"$gte": tu_truoc, "$lte": den}}},
        {"$facet": {
            "chuoi": [{"$match": {"date": {"$gte": tu}}},
                      {"$group": {"_id": "$date", **tong}},
                      {"$sort": {"_id": 1}}],
            "truoc": [{"$match": {"date": {"$lte": den_truoc}}},
                      {"$group": {"_id": None, **tong}}],
            "top": [{"$match": {"date": {"$gte": tu}}},
                    {"$group": {"_id": "$listing_id", "revenue_vnd": {"$sum": "$revenue_vnd"},
                                "orders": {"$sum": "$orders"}}},
                    {"$sort": {"revenue_vnd": -1}}, {"$limit": SO_TOP_PRODUCT},
                    {"$lookup": {"from": "listings", "localField": "_id",
                                 "foreignField": "listing_id", "as": "l"}},
                    {"$project": {"revenue_vnd": 1, "orders": 1,
                                  "title": {"$first": "$l.title"}}}],
        }},
    ])

    nay = {k: sum(r.get(k, 0) for r in kq["chuoi"]) for k in cot} if kq["chuoi"] else {}
    if not nay:
        return insufficient(
            f"Shop chưa có số liệu nào trong {so_ngay} ngày tính tới {den}",
            _meta(shop_id, tu, den, 0))

    truoc = kq["truoc"][0] if kq["truoc"] else {}
    chuoi = kq["chuoi"]
    co_ngay = len(chuoi)

    meta = _meta(shop_id, tu, den, co_ngay)
    if co_ngay < TOI_THIEU_NGAY:
        return insufficient(
            f"Shop mới, chỉ có {co_ngay} ngày dữ liệu trong khoảng đã chọn, "
            f"cần tối thiểu {TOI_THIEU_NGAY}", meta)

    def kpi(ten, lam_tron=tien):
        gia_tri = lam_tron(nay.get(ten, 0))
        return {"value": gia_tri, "pop_pct": phan_tram_thay_doi(gia_tri, lam_tron(truoc.get(ten, 0)))}

    cr_nay = ty_le_chuyen_doi(nay.get("orders", 0), nay.get("views", 0))
    cr_truoc = ty_le_chuyen_doi(truoc.get("orders", 0), truoc.get("views", 0))

    return ok({
        "range": timeRange,
        "from": tu,
        "to": den,
        "anchored_to_latest_data": True,
        "compare_from": tu_truoc,
        "compare_to": den_truoc,
        "kpi": {
            "views": kpi("views", int),
            "orders": kpi("orders", int),
            "revenue_vnd": kpi("revenue_vnd"),
            "conversion_pct": {
                "value": cr_nay,
                "pop_pct": phan_tram_thay_doi(cr_nay, cr_truoc) if (cr_nay is not None and cr_truoc) else None,
            },
        },
        "series": [{"date": r["_id"], "views": int(r["views"]), "orders": int(r["orders"]),
                    "revenue_vnd": tien(r["revenue_vnd"])} for r in chuoi],
        "top_products": [{"listing_id": t["_id"], "title": t.get("title"),
                          "orders": int(t["orders"]), "revenue_vnd": tien(t["revenue_vnd"])}
                         for t in kq["top"]],
        "recent_feedback": [],
    }, meta)


def _meta(shop_id, tu, den, co_ngay):
    return build_meta(
        model_version="live-read-1.0",
        scope="shop", scope_id=shop_id,
        database="vietcraft-seed", collection="listing_daily",
        mode="seed_demo",
        attributed_to_live_shop=False,
        sample_size=co_ngay, identity_linked=False,
        confidence="high" if co_ngay >= 30 else "medium",
    )
