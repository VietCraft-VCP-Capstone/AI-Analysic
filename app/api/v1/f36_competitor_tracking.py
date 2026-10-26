import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from fastapi import APIRouter, Body
from pymongo import ASCENDING

from app.api.v1._competitor_live import theo_doi_live
from app.api.v1._live import la_shop_live
from app.api.v1._mart import db
from app.api.v1._template import CurrentShop, build_meta, invalid_param, mart_not_ready, not_found, ok

router = APIRouter()

COLL = "competitor_tracker"
MART = "mart_competitor"
TOI_DA = 10          # BR-201
_da_tao_index = False


def _kho():
    global _da_tao_index
    c = db()[COLL]
    if not _da_tao_index:
        c.create_index([("shop_id", ASCENDING), ("tracked_shop_id", ASCENDING)],
                       unique=True, name="uniq_tracking")
        _da_tao_index = True
    return c


def _now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _chan_shop_live(shop_id):
    """Shop thật thêm/bỏ theo dõi bằng follow của sàn, do BE ghi (seller-analytics.router.ts)."""
    if la_shop_live(shop_id):
        invalid_param("shop_id", "shop trên sàn thêm hoặc bỏ theo dõi qua BE, không qua module AI")


def _meta(shop_id, n):
    return build_meta(model_version="tracker-1.0", scope="shop", scope_id=shop_id,
                      database="vietcraft-seed", collection=COLL,
                      mode="seed_demo", sample_size=n)


@router.get("/api/analytics/competitor-tracking", tags=["F36 · Đạt"])
def danh_sach(shop_id: str = CurrentShop):
    if la_shop_live(shop_id):
        return theo_doi_live(shop_id, TOI_DA)

    if db()[MART].estimated_document_count() == 0:
        mart_not_ready(MART)

    theo_doi = list(_kho().find({"shop_id": shop_id, "active": True}, {"_id": 0}))
    ma = [t["tracked_shop_id"] for t in theo_doi]

    # BR-203: ngách đang hoạt động của tôi = tập tag tôi đang bán.
    tag_toi = {t for r in db()[MART].find({"shop_id": shop_id}, {"_id": 0, "tags": 1})
               for t in r.get("tags") or []}

    dem_moi = {}
    if ma:
        for r in db()[MART].find({"shop_id": {"$in": ma}}, {"_id": 0, "shop_id": 1}):
            dem_moi[r["shop_id"]] = dem_moi.get(r["shop_id"], 0) + 1

    return ok({
        "tracked": [{
            "shop_id": t["tracked_shop_id"],
            "shop_name": t.get("tracked_shop_name"),
            "added_at": t.get("added_at"),
            "listings_total": dem_moi.get(t["tracked_shop_id"], 0),
        } for t in theo_doi],
        "slots_used": len(theo_doi), "slots_limit": TOI_DA,
        # BR-203 chỉ báo hàng MỚI; dữ liệu mồi không có ngày đăng thật nên không báo, tránh báo cả kho hàng cũ.
        "alerts": [],
        "alerts_total": 0,
        "my_niche_tags": sorted(tag_toi),
        "limitation": ("Dữ liệu mồi không có ngày đăng sản phẩm thật nên không biết hàng nào là mới; "
                       "cảnh báo hàng mới chỉ có ở shop trên sàn thật."),
    }, _meta(shop_id, len(theo_doi)))


@router.post("/api/analytics/competitor-tracking", tags=["F36 · Đạt"])
def them(shop_id: str = CurrentShop, body: dict = Body(default={})):
    _chan_shop_live(shop_id)
    muc_tieu = (body or {}).get("shop_id") or (body or {}).get("tracked_shop_id")
    if not muc_tieu:
        invalid_param("shop_id", "mã shop cần theo dõi, ví dụ shp_00042")
    if muc_tieu == shop_id:
        invalid_param("shop_id", "không thể tự theo dõi chính shop mình")

    s = db()["shops"].find_one({"shop_id": muc_tieu}, {"_id": 0, "name": 1})
    if s is None:
        not_found("shop")

    kho = _kho()
    if kho.find_one({"shop_id": shop_id, "tracked_shop_id": muc_tieu, "active": True}):
        invalid_param("shop_id", "already_tracked")            # BR-202
    if kho.count_documents({"shop_id": shop_id, "active": True}) >= TOI_DA:
        from fastapi import HTTPException
        raise HTTPException(status_code=400,
                            detail={"error": "tracking_limit_reached", "limit": TOI_DA})  # BR-201

    kho.update_one(
        {"shop_id": shop_id, "tracked_shop_id": muc_tieu},
        {"$set": {"active": True, "tracked_shop_name": s.get("name"), "added_at": _now()}},
        upsert=True)
    return ok({"tracked_shop_id": muc_tieu, "tracked_shop_name": s.get("name"),
               "slots_used": kho.count_documents({"shop_id": shop_id, "active": True}),
               "slots_limit": TOI_DA},
              _meta(shop_id, 1))


@router.delete("/api/analytics/competitor-tracking", tags=["F36 · Đạt"])
def bo(shop_id: str = CurrentShop, body: dict = Body(default={}),
       shopId: Optional[str] = None):
    _chan_shop_live(shop_id)
    muc_tieu = (body or {}).get("shop_id") or shopId
    if not muc_tieu:
        invalid_param("shop_id", "mã shop cần bỏ theo dõi")

    # BR-204: chỉ tắt cờ, KHÔNG xoá bản ghi — cảnh báo cũ phải còn tra được.
    kq = _kho().update_one({"shop_id": shop_id, "tracked_shop_id": muc_tieu},
                           {"$set": {"active": False, "removed_at": _now()}})
    if not kq.matched_count:
        not_found("tracking")
    return ok({"tracked_shop_id": muc_tieu, "active": False,
               "note": "Đã dừng theo dõi. Hệ thống chưa lưu lịch sử cảnh báo nên cảnh báo cũ của shop này cũng không còn hiện.",
               "slots_used": _kho().count_documents({"shop_id": shop_id, "active": True}),
               "slots_limit": TOI_DA},
              _meta(shop_id, 0))


@router.delete("/api/analytics/competitor-tracking/{shopId}", tags=["F36 · Đạt"])
def bo_theo_duong_dan(shopId: str, shop_id: str = CurrentShop):
    """Đúng dạng SRS 3.9.5; bản nhận body ở trên giữ lại cho client cũ."""
    return bo(shop_id=shop_id, body={}, shopId=shopId)
