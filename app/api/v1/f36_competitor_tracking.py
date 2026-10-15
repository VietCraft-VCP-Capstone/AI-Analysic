"""
F36 · /api/analytics/competitor-tracking — theo dõi shop đối thủ.

Endpoint DUY NHẤT trong 16 cái có ghi. 15 cái còn lại chỉ đọc.

  BR-201  tối đa 10 shop -> vượt thì 400 {"error":"tracking_limit_reached","limit":10}
  BR-202  trùng shop -> 400 {"error":"already_tracked"}
  BR-203  chỉ báo khi sản phẩm mới rơi vào ngách đang hoạt động của người bán
  BR-204  bỏ theo dõi DỪNG cảnh báo tương lai, KHÔNG xoá cảnh báo cũ

Trạng thái nằm ở `vietcraft-seed.competitor_tracker`. Đây KHÔNG phải mart (mart do
job ghi, API đọc) mà là dữ liệu người dùng tạo ra, nên không khai trong MART_SCHEMA
và không đi qua writer.save_model_output().
"""

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from fastapi import APIRouter, Body
from pymongo import ASCENDING

from app.api.v1._live import la_shop_live, san_pham_live
from app.api.v1._live_guard import dem_shop_cung_danh_muc
from app.api.v1._mart import db
from app.api.v1._template import (
    CurrentShop, build_meta, invalid_param, mart_not_ready, not_found, ok, partial,
)
from app.config import settings

router = APIRouter()

COLL = "competitor_tracker"
MART = "mart_competitor"
TOI_DA = 10          # BR-201
NGUONG_SHOP_CUNG_DM = 5     # §9.2: ≥5 shop cùng danh mục
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


def _meta(shop_id, n, live=False, unlock=None):
    return build_meta(model_version="tracker-1.0", scope="shop", scope_id=shop_id,
                      database=settings.MONGO_DB_LIVE if live else "vietcraft-seed",
                      collection=COLL, mode="live" if live else "seed_demo",
                      attributed_to_live_shop=live, sample_size=n, unlock=unlock)


@router.get("/api/analytics/competitor-tracking", tags=["F36 · Đạt"])
def danh_sach(shop_id: str = CurrentShop):
    # Danh sách theo dõi (CRUD) là dữ liệu NGƯỜI DÙNG tạo, không phải mart — luôn hiển
    # thị được bất kể shop mồi hay shop thật, bất kể đủ dữ liệu hay chưa (thêm/xoá vẫn
    # chạy được qua them()/bo() bên dưới, không bị guard này đụng tới).
    theo_doi = list(_kho().find({"shop_id": shop_id, "active": True}, {"_id": 0}))
    ma = [t["tracked_shop_id"] for t in theo_doi]

    co_live = la_shop_live(shop_id)

    # Chỉ phần HIỂN THỊ CẢNH BÁO (listing mới của đối thủ) mới cần đủ dữ liệu — và với
    # shop mồi, phần đó đọc mart `mart_competitor`, nên mart rỗng thì vẫn phải báo 503
    # như cũ. Shop thật không đọc mart này nên không áp dụng mart_not_ready.
    if not co_live and db()[MART].estimated_document_count() == 0:
        mart_not_ready(MART)

    du_du_lieu = True
    unlock = None
    tag_toi: set = set()
    canh_bao, dem_moi = [], {}

    if co_live:
        so_doi_thu = dem_shop_cung_danh_muc(shop_id)
        du_du_lieu = so_doi_thu >= NGUONG_SHOP_CUNG_DM
        if not du_du_lieu:
            unlock = {"requirement": "shop cùng danh mục", "unit": "shop",
                      "current": so_doi_thu, "target": NGUONG_SHOP_CUNG_DM}
        # BR-203: ngách đang hoạt động của tôi = tập tag trên sản phẩm THẬT đang bán.
        tag_toi = {t for p in san_pham_live(shop_id) for t in p.get("tags") or []}
        # Cảnh báo "listing mới của đối thủ" đọc mart `mart_competitor` — mart đó là
        # dữ liệu mồi, không khớp shop thật, nên để trống thay vì trộn hai miền dữ liệu.
        # Xem ghi chú mismatch BE ở cuối file: chưa có nguồn "sản phẩm mới của đối thủ"
        # cho sàn thật.
    else:
        tag_toi = {t for r in db()[MART].find({"shop_id": shop_id}, {"_id": 0, "tags": 1})
                   for t in r.get("tags") or []}
        if ma:
            for r in db()[MART].find({"shop_id": {"$in": ma}},
                                     {"_id": 0, "shop_id": 1, "shop_name": 1, "listing_id": 1,
                                      "title": 1, "tags": 1, "est_sales_90d": 1, "computed_at": 1}):
                dem_moi[r["shop_id"]] = dem_moi.get(r["shop_id"], 0) + 1
                trung = sorted(set(r.get("tags") or []) & tag_toi)
                if trung:
                    canh_bao.append({
                        "shop_id": r["shop_id"], "shop_name": r.get("shop_name"),
                        "listing_id": r["listing_id"], "title": r.get("title"),
                        "detected_at": r.get("computed_at"),
                        "in_my_niche": True, "matched_tags": trung,
                        "est_sales_90d": r.get("est_sales_90d"),
                    })
        canh_bao.sort(key=lambda a: -(a.get("est_sales_90d") or 0))

    data = {
        "tracked": [{
            "shop_id": t["tracked_shop_id"],
            "shop_name": t.get("tracked_shop_name"),
            "added_at": t.get("added_at"),
            "listings_total": dem_moi.get(t["tracked_shop_id"], 0),
        } for t in theo_doi],
        "slots_used": len(theo_doi), "slots_limit": TOI_DA,
        "alerts": canh_bao[:50],
        "alerts_total": len(canh_bao),
        "my_niche_tags": sorted(tag_toi),
        "limitation": (
            "Sàn thật chưa có nguồn 'sản phẩm mới của đối thủ' nối được tới đây, nên "
            "cảnh báo để trống — KHÔNG phải không có shop nào mới ra hàng." if co_live else
            "Dữ liệu mồi không có mốc thời gian đăng listing đáng tin, nên "
            "`detected_at` là lúc job chạy chứ KHÔNG phải lúc đối thủ ra hàng. "
            "Cảnh báo 'sản phẩm mới trong 7 ngày' chỉ đúng khi nối được sàn thật."),
    }
    meta = _meta(shop_id, len(theo_doi), live=co_live, unlock=unlock)

    if co_live and not du_du_lieu:
        return partial(
            data,
            "Sàn hiện chưa có đủ shop cùng danh mục để dò cảnh báo đối thủ mới — "
            "danh sách theo dõi của bạn vẫn hiển thị đầy đủ, chỉ phần cảnh báo tạm để trống.",
            meta)
    return ok(data, meta)


@router.post("/api/analytics/competitor-tracking", tags=["F36 · Đạt"])
def them(shop_id: str = CurrentShop, body: dict = Body(default={})):
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
    muc_tieu = (body or {}).get("shop_id") or shopId
    if not muc_tieu:
        invalid_param("shop_id", "mã shop cần bỏ theo dõi")

    # BR-204: chỉ tắt cờ, KHÔNG xoá bản ghi — cảnh báo cũ phải còn tra được.
    kq = _kho().update_one({"shop_id": shop_id, "tracked_shop_id": muc_tieu},
                           {"$set": {"active": False, "removed_at": _now()}})
    if not kq.matched_count:
        not_found("tracking")
    return ok({"tracked_shop_id": muc_tieu, "active": False,
               "note": "Đã dừng cảnh báo tương lai. Cảnh báo cũ vẫn giữ (BR-204).",
               "slots_used": _kho().count_documents({"shop_id": shop_id, "active": True}),
               "slots_limit": TOI_DA},
              _meta(shop_id, 0))
