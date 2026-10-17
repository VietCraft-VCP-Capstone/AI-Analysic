from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional

from bson import ObjectId

from app.api.v1._live import LOC_DON_THAT, LOC_SP_THAT, _so, db_live

GIO_VN = timezone(timedelta(hours=7))
DON_HOP_LE = {**LOC_DON_THAT, "order_status": {"$ne": "CANCELLED"}}


def _tien_don(don: Dict[str, Any]) -> int:
    fb = don.get("financial_breakdown") or {}
    for khoa in ("subtotal", "total", "grand_total"):
        v = _so(fb.get(khoa))
        if v and v > 0:
            return int(v)
    tong = 0.0
    for it in don.get("items") or []:
        gia = _so(it.get("retail_price")) or 0
        tong += gia * int(it.get("quantity") or 1)
    return int(tong)


def oid(x: Any) -> Optional[ObjectId]:
    try:
        return ObjectId(x)
    except Exception:
        return None


def ngay_vn(d: Any) -> Optional[str]:
    if not isinstance(d, datetime):
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(GIO_VN).date().isoformat()


def cac_ngay(so_ngay: int, den: Optional[str] = None) -> List[str]:
    cuoi = datetime.fromisoformat(den).date() if den else datetime.now(GIO_VN).date()
    return [(cuoi - timedelta(days=i)).isoformat() for i in range(so_ngay - 1, -1, -1)]


def bat_dau(ngay: str) -> datetime:
    return datetime.fromisoformat(ngay).replace(tzinfo=GIO_VN).astimezone(timezone.utc)


def san_pham_that() -> List[Dict[str, Any]]:
    return list(db_live()["products"].find(
        LOC_SP_THAT, {"shop_id": 1, "title": 1, "categories": 1, "tags": 1,
                      "average_rating": 1, "rating_count": 1}))


def danh_muc(p: Dict[str, Any]) -> Optional[str]:
    return (p.get("categories") or [None])[0]


def su_kien(ids: Iterable[Any], tu: datetime) -> List[Dict[str, Any]]:
    return list(db_live()["product_events"].find(
        {"product_id": {"$in": [oid(i) for i in ids]}, "created_at": {"$gte": tu}},
        {"product_id": 1, "event_type": 1, "created_at": 1}))


def don_hang(tu: datetime, shop_id: Any = None, da_tra_tien: bool = False) -> List[Dict[str, Any]]:
    loc: Dict[str, Any] = {**DON_HOP_LE, "created_at": {"$gte": tu}}
    if shop_id is not None:
        loc["shop_id"] = oid(shop_id)
    if da_tra_tien:
        loc["payment_status"] = "PAID"
    return list(db_live()["orders"].find(
        loc, {"shop_id": 1, "items": 1, "created_at": 1, "financial_breakdown": 1}))


def _dong_hang(don: Dict[str, Any], ids: set) -> List[Dict[str, Any]]:
    return [it for it in don.get("items") or [] if str(it.get("product_id")) in ids]


def tong_theo_san_pham(ids: Iterable[Any], tu: datetime) -> Dict[str, Dict[str, float]]:
    ids = {str(i) for i in ids}
    ra: Dict[str, Dict[str, float]] = defaultdict(
        lambda: {"views": 0, "carts": 0, "orders": 0, "units": 0, "revenue_vnd": 0})
    for e in su_kien(ids, tu):
        ra[str(e["product_id"])]["views" if e["event_type"] == "view" else "carts"] += 1
    for d in don_hang(tu):
        dong = _dong_hang(d, ids)
        for pid in {str(it["product_id"]) for it in dong}:
            ra[pid]["orders"] += 1
        for it in dong:
            sl = int(it.get("quantity") or 1)
            ra[str(it["product_id"])]["units"] += sl
            ra[str(it["product_id"])]["revenue_vnd"] += (_so(it.get("retail_price")) or 0) * sl
    return ra


def chuoi_ngay(ids: Iterable[Any], ngay: List[str]) -> Dict[str, Dict[str, int]]:
    ids = {str(i) for i in ids}
    ra = {d: {"views": 0, "carts": 0, "orders": 0, "revenue_vnd": 0} for d in ngay}
    tu = bat_dau(ngay[0])
    for e in su_kien(ids, tu):
        d = ngay_vn(e.get("created_at"))
        if d in ra:
            ra[d]["views" if e["event_type"] == "view" else "carts"] += 1
    for don in don_hang(tu):
        dong, d = _dong_hang(don, ids), ngay_vn(don.get("created_at"))
        if dong and d in ra:
            ra[d]["orders"] += 1
            ra[d]["revenue_vnd"] += int(sum((_so(it.get("retail_price")) or 0) * int(it.get("quantity") or 1)
                                            for it in dong))
    return ra


def doanh_thu_ngay(shop_id: str, so_ngay_toi_da: int = 540):
    hom_qua = (datetime.now(GIO_VN).date() - timedelta(days=1)).isoformat()
    tien: Dict[str, int] = defaultdict(int)
    for d in don_hang(bat_dau(cac_ngay(so_ngay_toi_da, hom_qua)[0]), shop_id, da_tra_tien=True):
        ngay = ngay_vn(d.get("created_at"))
        if ngay and ngay <= hom_qua:
            tien[ngay] += _tien_don(d)
    if not tien:
        return [], []
    so_ngay = (datetime.fromisoformat(hom_qua) - datetime.fromisoformat(min(tien))).days + 1
    ngay = cac_ngay(so_ngay, hom_qua)
    return ngay, [float(tien.get(n, 0)) for n in ngay]
