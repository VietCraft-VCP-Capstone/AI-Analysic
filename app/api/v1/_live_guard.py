from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from bson import ObjectId

from app.api.v1._live import LOC_DON_THAT, LOC_SP_THAT, db_live, la_shop_live
from app.api.v1._template import build_meta, insufficient
from app.config import settings

THIEU_LUOT_XEM = "Cần đủ lượt xem sản phẩm để tính. Sàn mới bắt đầu ghi lượt xem nên số liệu còn ít."
THIEU_LICH_SU = "Cần thêm thời gian bán hàng để mô hình học được nhịp bán bình thường của shop."
THIEU_DOI_THU = "Cần thêm shop cùng ngành có đơn trên sàn để so sánh có ý nghĩa."


def chua_ho_tro_live(ly_do: str) -> str:
    """Ghép lý do kỹ thuật với câu trấn an."""
    return f"{ly_do} Đây không phải lỗi, số liệu sẽ tự hiện khi đủ dữ liệu."


def chan_shop_live(shop_id: str, ly_do: str, collection: str = "orders",
                   unlock: Optional[Dict[str, Any]] = None):
    """insufficient_data cho shop live khi chưa đủ dữ liệu."""
    if not la_shop_live(shop_id):
        return None

    return insufficient(
        chua_ho_tro_live(ly_do),
        build_meta(model_version="live-guard-1.0", scope="shop", scope_id=shop_id,
                   database=settings.MONGO_DB_LIVE, collection=collection,
                   mode="live", attributed_to_live_shop=True, sample_size=0,
                   confidence="low", unlock=unlock),
    )


def _ngay_don_da_thanh_toan(shop_id: str):
    try:
        oid = ObjectId(shop_id)
    except Exception:
        return []
    return [
        d.get("created_at")
        for d in db_live()["orders"].find(
            {"shop_id": oid, "payment_status": {"$in": ["PAID"]}, **LOC_DON_THAT},
            {"created_at": 1},
        )
    ]


def dem_ngay_co_don(shop_id: str) -> int:
    """Số ngày khác nhau có đơn thật đã thanh toán (F30)."""
    ngay = set()
    for ca in _ngay_don_da_thanh_toan(shop_id):
        try:
            ngay.add(ca.date().isoformat())
        except Exception:
            continue
    return len(ngay)


def dem_tuan_co_don(shop_id: str) -> int:
    """Số tuần ISO khác nhau có đơn thật đã thanh toán (F37)."""
    tuan = set()
    for ca in _ngay_don_da_thanh_toan(shop_id):
        try:
            iso = ca.isocalendar()
            tuan.add((iso[0], iso[1]))
        except Exception:
            continue
    return len(tuan)


def dem_luot_xem_listing_30ngay(listing_id: str) -> int:
    """Lượt xem 30 ngày của một listing (F27/F28). Lỗi hoặc thiếu `product_events` thì 0 (§9.2)."""
    live = db_live()
    try:
        if "product_events" not in live.list_collection_names():
            return 0
    except Exception:
        return 0

    try:
        oid = ObjectId(listing_id)
    except Exception:
        oid = listing_id

    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        return live["product_events"].count_documents(
            {"product_id": oid, "event_type": "view", "created_at": {"$gte": cutoff}})
    except Exception:
        return 0


def dem_shop_cung_danh_muc(shop_id: str) -> int:
    """Số shop thật khác có sản phẩm thật chung ít nhất một danh mục (F33/F34/F36)."""
    try:
        oid = ObjectId(shop_id)
    except Exception:
        return 0

    live = db_live()
    danh_muc = [c for c in live["products"].distinct("categories", {"shop_id": oid, **LOC_SP_THAT}) if c]
    if not danh_muc:
        return 0
    return len(live["products"].distinct(
        "shop_id", {"categories": {"$in": danh_muc}, "shop_id": {"$ne": oid}, **LOC_SP_THAT}))
