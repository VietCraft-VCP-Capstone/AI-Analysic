import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from fastapi import APIRouter

from app.api.v1._live import _so, db_live, la_shop_live, san_pham_live
from app.api.v1._live_data import DON_HOP_LE, bat_dau, oid
from app.api.v1._money_calc import ngay_giao, tong_hop
from app.api.v1._money_range import doc_khoang_tien
from app.api.v1._money_comment import goi_y
from app.api.v1._money_voucher import kho_voucher
from app.api.v1._money_market import doan_slug, doc_tiki, dong_thi_truong
from app.api.v1._template import CurrentShop, build_meta, insufficient, ok

router = APIRouter()


def _meta(shop_id: str, n: int) -> Dict[str, Any]:
    return build_meta(model_version="live-read-1.0", scope="shop", scope_id=shop_id, database="vietcraft",
                      collection="orders", mode="live", attributed_to_live_shop=True, sample_size=n,
                      identity_linked=True, confidence="high")


def _hoan(ids: List[Any]) -> Tuple[Dict[str, int], Dict[str, int]]:
    """(hoàn theo đơn, hoàn theo món). Luồng cũ cả đơn; luồng đổi trả mới (POD) theo order_item_id."""
    hoan: Dict[str, int] = {}
    mon: Dict[str, int] = {}
    loc = {"order_id": {"$in": ids}, "status": "REFUNDED", "responsible_party": {"$nin": ["PRINTER", "PLATFORM"]}}
    for r in db_live()["refund_requests"].find(loc, {"order_id": 1, "refund_amount": 1}):
        k = str(r["order_id"])
        hoan[k] = hoan.get(k, 0) + int(round(_so(r.get("refund_amount")) or 0))
    loc_moi = {"order_id": {"$in": [str(i) for i in ids]}, "status": "REFUNDED", "fault_party": "SELLER"}
    for r in db_live()["return_refund_executions"].find(loc_moi, {"order_id": 1, "order_item_id": 1, "amount_minor": 1}):
        tien = int(r.get("amount_minor") or 0)
        hoan[r["order_id"]] = hoan.get(r["order_id"], 0) + tien
        mon[r["order_item_id"]] = mon.get(r["order_item_id"], 0) + tien
    return hoan, mon


_THI_TRUONG: Dict[str, Tuple[float, Any]] = {}


def _thi_truong(shop_id: str):
    co = _THI_TRUONG.get(shop_id)
    if co and time.time() - co[0] < 3600:  # dữ liệu Tiki cào theo ngày, không theo khoảng 7/30/90
        return co[1]
    try:
        cats = [c for p in san_pham_live(shop_id) for c in p.get("categories") or []]
        slug = doan_slug(cats)
        kq = dong_thi_truong(doc_tiki(slug), slug) if slug else None
    except Exception:
        return None
    _THI_TRUONG[shop_id] = (time.time(), kq)
    return kq


LUI_NGAY = 60
KHONG_GOI_Y = {"source": "none", "provider": None, "tips": {}}


def _don_giao(shop_id: str, tu: str, den: str) -> List[Dict[str, Any]]:
    """Đơn đã giao xong (theo ngày giao) trong [tu, den]."""
    # shortcut: đơn giao trễ hơn LUI_NGAY ngày sau khi đặt sẽ bị sót, tăng nếu POD giao lâu hơn
    lui = (date.fromisoformat(tu) - timedelta(days=LUI_NGAY)).isoformat()
    het = bat_dau((date.fromisoformat(den) + timedelta(days=1)).isoformat())
    don = db_live()["orders"].find(
        {**DON_HOP_LE, "order_status": "DELIVERED", "shop_id": oid(shop_id), "created_at": {"$gte": bat_dau(lui), "$lt": het},
         "payment_status": {"$in": ["PAID", "REFUNDED"]}, "order_code": {"$not": {"$regex": "^REPLACE-"}}},
        {"items": 1, "created_at": 1, "status_history": 1, "financial_breakdown": 1, "coupon_code": 1, "is_pod": 1})
    return [d for d in don if tu <= (ngay_giao(d) or "") <= den]


def _bao_cao(shop_id: str, timeRange: str, tu: Optional[str] = None, den: Optional[str] = None):
    """Trả (báo cáo, số đơn) hoặc (phản hồi insufficient, None)."""
    ngay, nhan = doc_khoang_tien(timeRange, tu=tu, den=den)
    if not la_shop_live(shop_id):
        return insufficient("Trang này chỉ tính cho gian hàng thật trên sàn.", _meta(shop_id, 0)), None

    don = _don_giao(shop_id, ngay[0], ngay[-1])
    if not don:
        return insufficient(f"Shop chưa có đơn đã giao xong trong {nhan}.", _meta(shop_id, 0)), None

    coupons = list(db_live()["coupons"].find({"shop_id": oid(shop_id)}))
    ten = {c["code"]: c.get("title") or "" for c in coupons}
    hoan, hoan_mon = _hoan([d["_id"] for d in don])
    bc = tong_hop(don, set(ten), hoan, ngay, hoan_mon)
    for v in bc["vouchers"]:
        v["title"] = ten.get(v["code"], "")
    bc["market"] = _thi_truong(shop_id)
    bc["voucher_stock"] = kho_voucher(coupons, {v["code"]: v["orders"] for v in bc["vouchers"]}, datetime.now())
    bc["range"], bc["from"], bc["to"] = timeRange, ngay[0], ngay[-1]
    return bc, len(don)


# Số liệu trả ngay; gợi ý AI (gọi LLM, 1–7s) để FE tải riêng ở /advice.
@router.get("/api/analytics/shop/money", tags=["F43 · Hưng"])
def money(shop_id: str = CurrentShop, timeRange: str = "30d",
          from_date: Optional[str] = None, to_date: Optional[str] = None):
    bc, n = _bao_cao(shop_id, timeRange, from_date, to_date)
    if n is None:
        return bc
    return ok({**bc, "advice": KHONG_GOI_Y}, _meta(shop_id, n))


@router.get("/api/analytics/shop/money/advice", tags=["F43 · Hưng"])
def money_advice(shop_id: str = CurrentShop, timeRange: str = "30d",
                 from_date: Optional[str] = None, to_date: Optional[str] = None):
    bc, n = _bao_cao(shop_id, timeRange, from_date, to_date)
    if n is None:
        return bc
    kq = goi_y(shop_id, bc)
    # data null khi LLM lỗi: FE không cache 5 phút, lần sau mở lại sẽ gọi lại
    return ok(kq if kq["tips"] else None, _meta(shop_id, n))
