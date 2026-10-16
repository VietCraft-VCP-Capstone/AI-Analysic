import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from fastapi import APIRouter

from app.api.v1._live import la_shop_live
from app.api.v1._live_category_revenue import category_revenue_live
from app.api.v1._mart import cua_so, db, doc_khoang, ngay_moi_nhat, tien
from app.api.v1._template import CurrentShop, build_meta, insufficient, mart_not_ready, ok

router = APIRouter()

THU_VI = {1: "Thứ Hai", 2: "Thứ Ba", 3: "Thứ Tư", 4: "Thứ Năm",
          5: "Thứ Sáu", 6: "Thứ Bảy", 7: "Chủ Nhật"}


@router.get("/api/analytics/shop/categories/revenue", tags=["F31 · Hiếu"])
def category_revenue(shop_id: str = CurrentShop, timeRange: str = "30d"):
    if la_shop_live(shop_id):
        return category_revenue_live(shop_id, timeRange)

    so_ngay = doc_khoang(timeRange)
    moi_nhat = ngay_moi_nhat({"shop_id": shop_id})
    if moi_nhat is None:
        mart_not_ready("listing_daily")
    tu, den = cua_so(moi_nhat, so_ngay)

    theo_loai = list(db()["listing_daily"].aggregate([
        {"$match": {"shop_id": shop_id, "date": {"$gte": tu, "$lte": den}}},
        {"$group": {"_id": "$product_type_id", "revenue_vnd": {"$sum": "$revenue_vnd"},
                    "orders": {"$sum": "$orders"}, "units": {"$sum": "$units_sold"}}},
        {"$sort": {"revenue_vnd": -1}},
    ]))

    meta = build_meta(model_version="live-read-1.0", scope="shop", scope_id=shop_id,
                      database="vietcraft-seed", collection="listing_daily",
                      mode="seed_demo", sample_size=len(theo_loai))

    if not theo_loai:
        return insufficient(f"Shop chưa có doanh thu nào trong {so_ngay} ngày tính tới {den}", meta)

    tong = sum(r["revenue_vnd"] for r in theo_loai) or 1
    ten_loai = {p["product_type_id"]: p.get("name_vi") for p in
                db()["vc_product_type"].find({}, {"product_type_id": 1, "name_vi": 1})}

    khung = list(db()["mart_shop_hour"].find({"shop_id": shop_id}, {"_id": 0})
                 .sort("orders", -1))
    dinh = khung[0] if khung else None

    return ok({
        "range": timeRange, "from": tu, "to": den, "anchored_to_latest_data": True,
        "by_product_type": [{
            "product_type_id": r["_id"],
            "name_vi": ten_loai.get(r["_id"]),
            "revenue_vnd": tien(r["revenue_vnd"]),
            "orders": int(r["orders"]),
            "units": int(r["units"]),
            "share_pct": round(r["revenue_vnd"] / tong * 100, 2),
        } for r in theo_loai],
        "total_revenue_vnd": tien(tong),
        "heatmap": [{"dow": k["dow"], "hour": k["hour"], "orders": k["orders"],
                     "revenue_vnd": k.get("revenue_vnd")} for k in khung],
        "heatmap_tz": "Asia/Ho_Chi_Minh",
        "peak_window": None if not dinh else {
            "dow": dinh["dow"], "dow_vi": THU_VI.get(dinh["dow"]), "hour": dinh["hour"],
            "orders": dinh["orders"],
            "note": f"{dinh['share_pct']}% đơn của shop rơi vào khung này",
        },
        "heatmap_window": "toàn bộ lịch sử đơn hàng",
        "limitation": ("Nhịp giờ/thứ kế thừa từ phân phối Olist (Brazil) trong dữ liệu mồi, "
                       "CHƯA phản ánh thói quen người mua Việt Nam."),
    }, meta)
