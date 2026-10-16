import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from fastapi import APIRouter

from app.api.v1._live import la_shop_live
from app.api.v1._live_guard import THIEU_LUOT_XEM, chan_shop_live, dem_luot_xem_listing_30ngay
from app.api.v1._mart import cua_so, db, doc_khoang, ngay_moi_nhat, tien, ty_le_chuyen_doi
from app.api.v1._template import CurrentShop, forbidden, insufficient, mart_not_ready, build_meta, not_found, ok

router = APIRouter()

TOI_THIEU_NGAY = 7
NGUONG_DOC = 5.0        # BR-178: ±5% mỗi ngày so với mức trung bình
NGUONG_LUOT_XEM = 100   # §9.2: ≥100 lượt xem/listing/30 ngày


def _xu_huong(gia_tri):
    """Độ dốc hồi quy tuyến tính, quy về % thay đổi mỗi ngày so với mức trung bình.

    Dùng hồi quy chứ không so điểm đầu với điểm cuối: chuỗi ngày rất nhiễu, hai
    điểm mút có thể là ngày lễ hoặc ngày chết và cho kết luận ngược hẳn.
    """
    n = len(gia_tri)
    if n < TOI_THIEU_NGAY:
        return "unknown", None
    tb_x = (n - 1) / 2
    tb_y = sum(gia_tri) / n
    mau = sum((i - tb_x) ** 2 for i in range(n))
    if not mau or not tb_y:
        return "flat", 0.0
    doc = sum((i - tb_x) * (y - tb_y) for i, y in enumerate(gia_tri)) / mau
    pct = round(doc / tb_y * 100, 2)
    return ("up" if pct > NGUONG_DOC else "down" if pct < -NGUONG_DOC else "flat"), pct


@router.get("/api/analytics/listings/{id}/timeseries", tags=["F27 · Hiếu"])
def listing_timeseries(id: str, shop_id: str = CurrentShop, timeRange: str = "30d"):
    unlock = None
    if la_shop_live(shop_id):
        unlock = {"requirement": "lượt xem/listing, 30 ngày", "unit": "lượt xem",
                  "current": dem_luot_xem_listing_30ngay(id), "target": NGUONG_LUOT_XEM}
    chan = chan_shop_live(shop_id, THIEU_LUOT_XEM, "product_events", unlock=unlock)
    if chan is not None:
        return chan

    so_ngay = doc_khoang(timeRange)

    l = db()["listings"].find_one({"listing_id": id},
                                  {"_id": 0, "shop_id": 1, "title": 1, "category_id": 1})
    if l is None:
        not_found("listing")
    if l.get("shop_id") != shop_id:
        forbidden()

    moi_nhat = ngay_moi_nhat({"listing_id": id})
    if moi_nhat is None:
        mart_not_ready("listing_daily")
    tu, den = cua_so(moi_nhat, so_ngay)

    rows = list(db()["listing_daily"].find(
        {"listing_id": id, "date": {"$gte": tu, "$lte": den}},
        {"_id": 0, "date": 1, "views": 1, "add_to_carts": 1, "orders": 1, "revenue_vnd": 1},
    ).sort("date", 1))

    meta = build_meta(model_version="live-read-1.0", scope="listing", scope_id=id,
                      database="vietcraft-seed", collection="listing_daily",
                      mode="seed_demo", sample_size=len(rows),
                      confidence="high" if len(rows) >= 30 else "medium")

    if len(rows) < TOI_THIEU_NGAY:
        return insufficient(
            f"Listing chỉ có {len(rows)} ngày dữ liệu trong khoảng đã chọn, "
            f"cần tối thiểu {TOI_THIEU_NGAY} ngày mới kết luận xu hướng", meta)

    chuoi = [{"date": r["date"], "views": int(r["views"]), "carts": int(r["add_to_carts"]),
              "orders": int(r["orders"]), "revenue_vnd": tien(r["revenue_vnd"])} for r in rows]

    # Trung vị danh mục cùng kỳ, để người bán biết mình so với mặt bằng.
    trung_vi = list(db()["listing_daily"].aggregate([
        {"$match": {"category_id": l.get("category_id"), "date": {"$gte": tu, "$lte": den}}},
        {"$group": {"_id": {"d": "$date", "l": "$listing_id"}, "v": {"$sum": "$views"}}},
        {"$group": {"_id": "$_id.d", "views": {"$avg": "$v"}}},
        {"$sort": {"_id": 1}},
    ]))

    xu_xem, doc_xem = _xu_huong([c["views"] for c in chuoi])
    xu_don, doc_don = _xu_huong([c["orders"] for c in chuoi])

    return ok({
        "listing_id": id,
        "title": l.get("title"),
        "category_id": l.get("category_id"),
        "from": tu, "to": den, "anchored_to_latest_data": True,
        "series": chuoi,
        "category_median": [{"date": r["_id"], "views": round(r["views"], 1)} for r in trung_vi],
        "totals": {
            "views": sum(c["views"] for c in chuoi),
            "carts": sum(c["carts"] for c in chuoi),
            "orders": sum(c["orders"] for c in chuoi),
            "revenue_vnd": sum(c["revenue_vnd"] for c in chuoi),
            "conversion_pct": ty_le_chuyen_doi(sum(c["orders"] for c in chuoi),
                                               sum(c["views"] for c in chuoi)),
        },
        "trend": {"views": xu_xem, "orders": xu_don,
                  "views_slope_pct_per_day": doc_xem, "orders_slope_pct_per_day": doc_don,
                  "threshold_pct": NGUONG_DOC},
    }, meta)
