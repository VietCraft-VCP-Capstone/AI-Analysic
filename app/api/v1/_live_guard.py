from bson import ObjectId

from app.api.v1._live import LOC_SP_THAT, db_live


def dem_shop_cung_danh_muc(shop_id: str) -> int:
    """Số shop thật khác có sản phẩm thật chung ít nhất một danh mục (F36)."""
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
