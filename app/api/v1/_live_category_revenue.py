import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.api.v1._live import LOC_DON_THAT, LOC_SP_THAT, _so, db_live
from app.api.v1._mart import doc_khoang, tien
from app.api.v1._template import build_meta, insufficient, ok

TRANG_THAI_TINH_TIEN = ["PAID"]
TOI_THIEU_DON = 20

THU_VI = {1: "Thứ Hai", 2: "Thứ Ba", 3: "Thứ Tư", 4: "Thứ Năm",
          5: "Thứ Sáu", 6: "Thứ Bảy", 7: "Chủ Nhật"}

CHUA_PHAN_LOAI = "(chưa phân loại)"


def _don_cua_shop(shop_id: str) -> List[Dict[str, Any]]:
    from bson import ObjectId  # noqa: PLC0415

    try:
        oid = ObjectId(shop_id)
    except Exception:
        return []
    loc = {"shop_id": oid, "payment_status": {"$in": TRANG_THAI_TINH_TIEN}, **LOC_DON_THAT}
    return list(db_live()["orders"].find(
        loc, {"items": 1, "financial_breakdown": 1, "order_hour_of_week": 1, "created_at": 1},
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


def _ngay(d: Any) -> Optional[str]:
    try:
        return d.date().isoformat()
    except Exception:
        return None


def _gio_tuan(order_hour_of_week: int):
    """order_hour_of_week = getDay()*24 + getHours() (BE, Date.getDay() kiểu JS:
    0 = Chủ Nhật .. 6 = Thứ Bảy). Đổi sang ISO dow 1 = Thứ Hai .. 7 = Chủ Nhật."""
    js_dow = order_hour_of_week // 24
    hour = order_hour_of_week % 24
    iso_dow = 7 if js_dow == 0 else js_dow
    return iso_dow, hour


def category_revenue_live(shop_id: str, time_range: str):
    so_ngay = doc_khoang(time_range)
    don = _don_cua_shop(shop_id)

    meta = build_meta(model_version="live-read-1.0", scope="shop", scope_id=shop_id,
                      database="vietcraft", collection="orders", mode="live",
                      attributed_to_live_shop=True, sample_size=len(don),
                      identity_linked=True, confidence="high" if len(don) >= TOI_THIEU_DON else "low")

    if len(don) < TOI_THIEU_DON:
        meta["unlock"] = {"requirement": "đơn thật", "unit": "đơn",
                          "current": len(don), "target": TOI_THIEU_DON}
        return insufficient(
            f"Shop mới có {len(don)} đơn thật đã thanh toán, cần tối thiểu {TOI_THIEU_DON} "
            f"mới tính được doanh thu theo danh mục và khung giờ đáng tin.", meta)

    # Khung giờ vàng
    khung: Dict[Any, Dict[str, Any]] = {}
    for d in don:
        ohw = d.get("order_hour_of_week")
        if ohw is None:
            continue
        dow, hour = _gio_tuan(int(ohw))
        k = khung.setdefault((dow, hour), {"dow": dow, "hour": hour, "orders": 0, "revenue_vnd": 0})
        k["orders"] += 1
        k["revenue_vnd"] += _tien_don(d)
    khung_list = sorted(khung.values(), key=lambda x: -x["orders"])
    dinh = khung_list[0] if khung_list else None
    tong_don_lich_su = len(don)

    # Doanh thu theo danh mục
    ngay_don = sorted(n for n in (_ngay(d.get("created_at")) for d in don) if n)
    moi_nhat = ngay_don[-1] if ngay_don else None
    if moi_nhat:
        from datetime import datetime, timedelta  # noqa: PLC0415
        den_d = datetime.fromisoformat(moi_nhat).date()
        tu_d = den_d - timedelta(days=so_ngay - 1)
        tu, den = tu_d.isoformat(), den_d.isoformat()
        trong_ky = [d for d in don if (_ngay(d.get("created_at")) or "") >= tu
                    and (_ngay(d.get("created_at")) or "") <= den]
    else:
        tu = den = None
        trong_ky = don

    pid_set = {it.get("product_id") for d in trong_ky for it in (d.get("items") or []) if it.get("product_id")}
    cat_cua_sp: Dict[str, List[str]] = {}
    if pid_set:
        for p in db_live()["products"].find(
            {"_id": {"$in": list(pid_set)}, **LOC_SP_THAT}, {"categories": 1}):
            cat_cua_sp[str(p["_id"])] = [c for c in (p.get("categories") or []) if c]

    theo_cat: Dict[str, Dict[str, Any]] = {}
    tong_dt = 0
    for d in trong_ky:
        tong_dt += _tien_don(d)
        for it in d.get("items") or []:
            pid = str(it.get("product_id") or "")
            cats = cat_cua_sp.get(pid) or [CHUA_PHAN_LOAI]
            gia = _so(it.get("retail_price")) or 0
            sl = int(it.get("quantity") or 1)
            dt_item = int(gia * sl)
            for c in cats:
                o = theo_cat.setdefault(c, {"revenue_vnd": 0, "orders": set(), "units": 0})
                o["revenue_vnd"] += dt_item
                o["orders"].add(str(d.get("_id")))
                o["units"] += sl

    tong_cat = sum(v["revenue_vnd"] for v in theo_cat.values()) or 1

    return ok({
        "range": time_range, "from": tu, "to": den, "anchored_to_latest_data": True,
        "by_product_type": [{
            "product_type_id": c,
            "name_vi": c,
            "revenue_vnd": tien(v["revenue_vnd"]),
            "orders": len(v["orders"]),
            "units": v["units"],
            "share_pct": round(v["revenue_vnd"] / tong_cat * 100, 2),
        } for c, v in sorted(theo_cat.items(), key=lambda kv: -kv[1]["revenue_vnd"])],
        "total_revenue_vnd": tien(tong_dt),
        "heatmap": [{"dow": k["dow"], "hour": k["hour"], "orders": k["orders"],
                     "revenue_vnd": tien(k["revenue_vnd"])} for k in khung_list],
        "heatmap_tz": "Asia/Ho_Chi_Minh",
        "peak_window": None if not dinh else {
            "dow": dinh["dow"], "dow_vi": THU_VI.get(dinh["dow"]), "hour": dinh["hour"],
            "orders": dinh["orders"],
            "note": f"{round(dinh['orders'] / tong_don_lich_su * 100, 1)}% đơn của shop rơi vào khung này",
        },
        "heatmap_window": "toàn bộ lịch sử đơn hàng thật",
        "limitation": ("Danh mục là chữ tự do người bán tự đặt khi tạo sản phẩm, không phải "
                       "catalog chuẩn hoá — tên có thể trùng ý nhưng khác chữ. Một sản phẩm "
                       "thuộc nhiều danh mục thì doanh thu được tính vào từng danh mục đó."),
    }, meta)
