import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from app.api.v1._live import _so

LOAI = {"PERCENTAGE": "giảm theo %", "FIXED_AMOUNT": "giảm số tiền cố định", "FREE_SHIPPING": "miễn phí vận chuyển",
        "FLASH_SALE": "flash sale", "BUNDLE": "mua kèm"}
SAP_HET_NGAY = 14
IT_DUNG = 0.2


def _trang_thai(c: Dict[str, Any], bay_gio: datetime) -> str:
    het = c.get("end_date")
    if not c.get("is_active", True) or (isinstance(het, datetime) and het.replace(tzinfo=None) < bay_gio):
        return "ended"
    dung, han = int(_so(c.get("used_count")) or 0), int(_so(c.get("usage_limit")) or 0)
    if dung == 0:
        return "unused"
    if han and dung / han < IT_DUNG:
        return "low"
    if isinstance(het, datetime) and het.replace(tzinfo=None) - bay_gio < timedelta(days=SAP_HET_NGAY):
        return "expiring"
    return "ok"


def kho_voucher(coupons: List[Dict[str, Any]], trong_ky: Dict[str, int], bay_gio: datetime) -> Dict[str, Any]:
    """Kho mã của shop: tổng, đã dùng / giới hạn (trọn đời), số đơn trong kỳ, mã hiệu quả thấp."""
    ds = []
    for c in coupons:
        het = c.get("end_date")
        ds.append({"code": c["code"], "title": c.get("title") or "", "type": c.get("discount_type") or "",
                   "value": _so(c.get("discount_value")) or 0, "used": int(_so(c.get("used_count")) or 0),
                   "limit": int(_so(c.get("usage_limit")) or 0), "min_order": _so(c.get("min_order_value")) or 0,
                   "max_discount": _so(c.get("max_discount_amount")) or 0, "orders_in_range": trong_ky.get(c["code"], 0),
                   "end_date": het.date().isoformat() if isinstance(het, datetime) else None,
                   "expired": isinstance(het, datetime) and het.replace(tzinfo=None) < bay_gio,
                   "status": _trang_thai(c, bay_gio)})
    ds.sort(key=lambda v: (v["status"] == "ended", -v["used"]))
    return {"total": len(ds), "active": sum(v["status"] != "ended" for v in ds),
            "used": sum(v["used"] for v in ds), "limit": sum(v["limit"] for v in ds),
            "idle": sum(v["status"] in ("unused", "low") for v in ds), "items": ds,
            "suggest": goi_y_luat(ds)}


def _ty_le(v: Dict[str, Any]) -> float:
    return v["used"] / v["limit"] if v["limit"] else 0.0


def ban_nhap(mau: Optional[Dict[str, Any]], ma_da_co: List[str]) -> Dict[str, Any]:
    """Mã đề xuất cụ thể: chép cấu hình mã mẫu, tên mới chưa trùng (A-Z0-9_, 3-20 ký tự như BE)."""
    if not mau:
        return {"code": "FREESHIP_1", "title": "Miễn phí vận chuyển cho khách mới", "value": 30000,
                "min_order": 150000, "max_discount": 30000, "limit": 50, "days": 30}
    goc = re.sub(r"[^A-Z0-9_]", "", mau["code"].upper())[:17] or "SHOP"
    i = 2
    while f"{goc}_{i}" in ma_da_co:
        i += 1
    ten = (mau["title"] or LOAI.get(mau["type"], "Voucher").capitalize())[:88]
    return {"code": f"{goc}_{i}", "title": f"{ten} (đợt mới)", "value": mau["value"], "min_order": mau["min_order"],
            "max_discount": mau["max_discount"], "limit": mau["limit"] or 50, "days": 30}


def _viec(tot: Dict[str, Any]) -> Tuple[str, str]:
    """Mã tốt nhất còn dùng được thì giữ/bật lại; hết hạn hoặc hết lượt thì tạo mã mới (BE chưa cho sửa mã)."""
    con = not tot["limit"] or tot["used"] < tot["limit"]
    if tot["status"] != "ended" and con:
        return "keep", f"Mã {tot['code']} còn {tot['limit'] - tot['used']} lượt, chưa cần tạo mới." if tot["limit"]             else f"Mã {tot['code']} vẫn đang chạy, chưa cần tạo mới."
    if tot["status"] == "ended" and not tot["expired"] and con:
        return "reactivate", f"Mã {tot['code']} đang tắt, bật lại là dùng tiếp."
    ly_do = "đã hết hạn" if tot["expired"] else "đã hết lượt"
    return "create", f"Mã {tot['code']} {ly_do}, tạo mã mới cùng điều kiện."


def goi_y_luat(ds: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Việc nên làm với voucher: dựa trên mã có tỉ lệ dùng cao nhất; chưa có mã nào thì tạo mã miễn phí vận chuyển."""
    if not ds:
        y = ["Shop chưa có mã nào.", "Miễn phí vận chuyển là loại dễ hiểu nhất với khách mới."]
        return {"type": "FREE_SHIPPING", "action": "create", "code": None, "reason": " ".join(y), "points": y,
                "draft": ban_nhap(None, [])}
    tot = max(ds, key=_ty_le)
    if tot["used"] == 0:
        return None
    viec, cau = _viec(tot)
    y = [f"Mã {tot['code']} ({LOAI.get(tot['type'], tot['type'])}) được dùng {tot['used']}/{tot['limit']} lượt, cao nhất trong kho.", cau]
    im = sum(v["status"] in ("unused", "low") for v in ds)
    if im:
        y.append(f"{im} mã hiệu quả thấp, nên tạm dừng để kho gọn hơn.")
    chua = [LOAI[k] for k in LOAI if k not in {v["type"] for v in ds}]
    if chua:
        y.append(f"Shop chưa thử: {', '.join(chua)}.")
    nhap = ban_nhap(tot, [v["code"] for v in ds]) if viec == "create" else None
    return {"type": tot["type"], "action": viec, "code": tot["code"], "reason": " ".join(y), "points": y, "draft": nhap}
