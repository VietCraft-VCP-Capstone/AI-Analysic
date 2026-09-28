"""
F29 · GET /api/analytics/listings/{id}/health — điểm sức khoẻ 0-100 kèm việc cần sửa.

  BR-181  chấm lại mỗi 24h (job build_marts chạy đêm)
  BR-182  >= 80 `tốt` · 50-79 `cần cải thiện` · < 50 `kém`
          Trọng số phải cộng đúng 1.0 — cổng ra kiểm
  Listing chưa có đánh giá -> `rating_shrunk: null`, KHÔNG mặc định 4.0 sao
"""

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from fastapi import APIRouter

from app.api.v1._live import THIEU_LUOT_XEM, chan_shop_live
from app.api.v1._mart import db
from app.api.v1._template import CurrentShop, forbidden, insufficient, mart_not_ready, meta_from_record, not_found, ok

router = APIRouter()

MART = "listing_health"


@router.get("/api/analytics/listings/{id}/health", tags=["F29 · Hạt"])
def health(id: str, shop_id: str = CurrentShop):
    chan = chan_shop_live(shop_id, THIEU_LUOT_XEM, "product_events")
    if chan is not None:
        return chan

    l = db()["listings"].find_one({"listing_id": id}, {"_id": 0, "shop_id": 1})
    if l is None:
        not_found("listing")
    if l.get("shop_id") != shop_id:
        forbidden()

    coll = db()[MART]
    if coll.estimated_document_count() == 0:
        mart_not_ready(MART)

    r = coll.find_one({"listing_id": id}, {"_id": 0}, sort=[("date", -1)])
    if r is None:
        return insufficient(f"Listing `{id}` chưa được chấm điểm — job chấm mỗi 24h, "
                            f"listing mới tạo phải chờ lượt chạy tới")

    meta = meta_from_record(r, scope="listing", scope_id=id, collection=MART,
                            mode="seed_demo", sample_size=r.get("n_reviews", 0),
                            confidence="high" if not r.get("axes_missing") else "medium")

    if r.get("health_score") is None:
        return insufficient(
            "Không trục nào đủ dữ liệu để chấm điểm listing này", meta)

    return ok({
        "listing_id": id,
        "title": r.get("title"),
        "date": r["date"],
        "health_score": r["health_score"],
        "band": r["band"],
        "conversion_rate": r.get("conversion_rate"),
        "category_avg_cr": r.get("category_avg_cr"),
        "cr_index": r.get("cr_index"),
        "rating_shrunk": r.get("rating_shrunk"),     # null khi chưa có đánh giá
        "n_reviews": r.get("n_reviews", 0),
        "breakdown": r["breakdown"],
        "axes_missing": r.get("axes_missing") or [],
        "todo": r.get("todo") or [],
        "note": ("Trục thiếu dữ liệu bị LOẠI khỏi phép tính và trọng số chia lại cho "
                 "các trục còn lại — không cho 0 điểm, vì thiếu dữ liệu khác với kém."),
    }, meta)
