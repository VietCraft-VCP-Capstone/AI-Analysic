import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.api.v1._live import _so, db_live
from app.api.v1._mart import phan_tram_thay_doi, tien
from app.api.v1._template import build_meta, insufficient, ok

TRANG_THAI_TINH_TIEN = ["PAID"]
SO_TOP_PRODUCT = 5


def _ngay(d: Any) -> Optional[str]:
    if isinstance(d, datetime):
        return d.date().isoformat()
    if isinstance(d, str) and len(d) >= 10:
        return d[:10]
    return None


def _don_cua_shop(shop_id: str) -> List[Dict[str, Any]]:
    from bson import ObjectId  # noqa: PLC0415

    try:
        oid = ObjectId(shop_id)
    except Exception:
        return []
    return list(db_live()["orders"].find(
        {"shop_id": oid, "payment_status": {"$in": TRANG_THAI_TINH_TIEN}},
        {"created_at": 1, "items": 1, "financial_breakdown": 1, "order_hour_of_week": 1},
    ))


def _tien_don(don: Dict[str, Any]) -> int:
    """Doanh thu một đơn. Ưu tiên tổng đã chốt, không có thì cộng từng dòng hàng."""
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


def overview_live(shop_id: str, so_ngay: int, time_range: str):
    """Tổng quan shop từ đơn thật. Lượt xem để null vì sàn chưa có theo dõi hành vi."""
    don = _don_cua_shop(shop_id)

    meta = build_meta(model_version="live-overview-1.0", scope="shop", scope_id=shop_id,
                      database="vietcraft", collection="orders", mode="live",
                      attributed_to_live_shop=True, sample_size=len(don),
                      identity_linked=True, confidence="high" if len(don) >= 20 else "low")

    if not don:
        return insufficient(
            "Shop bạn chưa có đơn hàng nào đã thanh toán, nên chưa có số để tổng quan. "
            "Số liệu sẽ hiện ngay khi có đơn đầu tiên.", meta)

    ngay_don = sorted(n for n in (_ngay(d.get("created_at")) for d in don) if n)
    moi_nhat = ngay_don[-1]

    den = datetime.fromisoformat(moi_nhat).replace(tzinfo=timezone.utc)
    tu = den - timedelta(days=so_ngay - 1)
    tu_truoc = tu - timedelta(days=so_ngay)
    den_truoc = tu - timedelta(days=1)

    def trong(d1: datetime, d2: datetime) -> List[Dict[str, Any]]:
        a, b = d1.date().isoformat(), d2.date().isoformat()
        return [d for d in don if (_ngay(d.get("created_at")) or "") >= a and (_ngay(d.get("created_at")) or "") <= b]

    ky_nay, ky_truoc = trong(tu, den), trong(tu_truoc, den_truoc)
    dt_nay = sum(_tien_don(d) for d in ky_nay)
    dt_truoc = sum(_tien_don(d) for d in ky_truoc)

    theo_ngay: Dict[str, Dict[str, int]] = {}
    for i in range(so_ngay):
        k = (tu + timedelta(days=i)).date().isoformat()
        theo_ngay[k] = {"orders": 0, "revenue_vnd": 0}
    for d in ky_nay:
        k = _ngay(d.get("created_at"))
        if k in theo_ngay:
            theo_ngay[k]["orders"] += 1
            theo_ngay[k]["revenue_vnd"] += _tien_don(d)

    # Top sản phẩm theo doanh thu, gộp từ các dòng hàng.
    theo_sp: Dict[str, Dict[str, Any]] = {}
    for d in ky_nay:
        for it in d.get("items") or []:
            pid = str(it.get("product_id") or "")
            if not pid:
                continue
            o = theo_sp.setdefault(pid, {"listing_id": pid, "title": it.get("title") or pid,
                                         "orders": 0, "revenue_vnd": 0})
            o["orders"] += 1
            o["revenue_vnd"] += int((_so(it.get("retail_price")) or 0) * int(it.get("quantity") or 1))

    return ok({
        "range": time_range,
        "from": tu.date().isoformat(),
        "to": den.date().isoformat(),
        "anchored_to_latest_data": True,
        "compare_from": tu_truoc.date().isoformat(),
        "compare_to": den_truoc.date().isoformat(),
        "kpi": {
            # Lượt xem CHƯA ĐO ĐƯỢC. null, không phải 0.
            "views": {"value": None, "pop_pct": None},
            "orders": {"value": len(ky_nay), "pop_pct": phan_tram_thay_doi(len(ky_nay), len(ky_truoc))},
            "revenue_vnd": {"value": tien(dt_nay), "pop_pct": phan_tram_thay_doi(dt_nay, dt_truoc)},
            "conversion_pct": {"value": None, "pop_pct": None},
        },
        "series": [{"date": k, "views": None, "orders": v["orders"], "revenue_vnd": v["revenue_vnd"]}
                   for k, v in sorted(theo_ngay.items())],
        "top_products": sorted(theo_sp.values(), key=lambda x: -x["revenue_vnd"])[:SO_TOP_PRODUCT],
        "recent_feedback": [],
        "orders_all_time": len(don),
        "limitation": (
            "Đơn hàng và doanh thu là số THẬT của shop bạn, chỉ tính đơn đã thanh toán. "
            "Lượt xem và tỉ lệ chuyển đổi để trống vì sàn chưa bật theo dõi hành vi người "
            "mua, không phải vì bằng 0. Hai chỉ số đó sẽ tự hiện khi tính năng theo dõi lên sóng."
        ),
    }, meta)
