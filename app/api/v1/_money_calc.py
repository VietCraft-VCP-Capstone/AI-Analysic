import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.api.v1._live import _so
from app.api.v1._live_data import ngay_vn

TOI_THIEU_SO_SANH = 10


def _v(x: Any) -> int:
    return int(round(_so(x) or 0))


def _fb(don: Dict[str, Any]) -> Dict[str, Any]:
    return don.get("financial_breakdown") or {}


def _sl(it: Dict[str, Any]) -> int:
    return int(it.get("quantity") or 1)


def ngay_giao(don: Dict[str, Any]) -> Optional[str]:
    """Ngày giao xong đầu tiên (giống BE); đơn cũ thiếu lịch sử thì dùng ngày tạo."""
    lan = [r["changed_at"] for r in don.get("status_history") or []
           if r.get("status") == "DELIVERED" and isinstance(r.get("changed_at"), datetime)]
    return ngay_vn(min(lan) if lan else don.get("created_at"))


def _net(don: Dict[str, Any], hoan: Dict[str, int]) -> int:
    return _v(_fb(don).get("seller_payout_amount")) - hoan.get(str(don["_id"]), 0)


def _dong_tien(don: List[Dict], ma_shop: Set[str], hoan: Dict[str, int]) -> Dict[str, int]:
    mua = sum(_v(_fb(d).get("subtotal")) for d in don)
    phi = sum(_v(_fb(d).get("platform_fee")) for d in don)
    voucher_shop = sum(_v(_fb(d).get("coupon_discount")) for d in don if d.get("coupon_code") in ma_shop)
    voucher_san = sum(_v(_fb(d).get("coupon_discount")) for d in don
                      if d.get("coupon_code") and d.get("coupon_code") not in ma_shop)
    refund = sum(hoan.get(str(d["_id"]), 0) for d in don)
    net = sum(_net(d, hoan) for d in don)
    return {"buyer_paid_vnd": mua, "platform_fee_vnd": phi, "shop_voucher_vnd": voucher_shop,
            "refund_vnd": refund, "other_vnd": mua - phi - voucher_shop - refund - net,
            "net_vnd": net, "platform_voucher_vnd": voucher_san}


def _theo_ngay(don: List[Dict], hoan: Dict[str, int], ngay: List[str]) -> List[Dict[str, Any]]:
    tong = {n: {"date": n, "net_vnd": 0, "orders": 0} for n in ngay}
    for d in don:
        n = ngay_giao(d)
        if n in tong:
            tong[n]["net_vnd"] += _net(d, hoan)
            tong[n]["orders"] += 1
    return list(tong.values())


def _theo_san_pham(don: List[Dict], hoan: Dict[str, int], hoan_mon: Dict[str, int]) -> List[Dict[str, Any]]:
    gop: Dict[str, Dict[str, Any]] = {}
    for d in don:
        dong = d.get("items") or []
        trong_so = [_v(it.get("retail_price")) * _sl(it) for it in dong]
        tong = sum(trong_so)
        if not tong:
            continue
        rieng = [hoan_mon.get(str(it.get("order_item_id")), 0) for it in dong]
        # hoàn theo món gán thẳng vào món đó; phần hoàn cả đơn còn lại chia theo giá
        cu = hoan.get(str(d["_id"]), 0) - sum(rieng)
        truoc_hoan = _net(d, hoan) + hoan.get(str(d["_id"]), 0)
        for it, w, r in zip(dong, trong_so, rieng):
            pid = str(it.get("product_id") or "")
            g = gop.setdefault(pid, {"product_id": pid, "title": it.get("title") or "",
                                     "image": it.get("image") or "", "units": 0, "net_vnd": 0.0,
                                     "refund_vnd": 0.0})
            g["units"] += _sl(it)
            g["refund_vnd"] += cu * w / tong + r
            g["net_vnd"] += truoc_hoan * w / tong - (cu * w / tong + r)
    for g in gop.values():
        g["net_vnd"] = int(round(g["net_vnd"]))
        g["refund_vnd"] = int(round(g["refund_vnd"]))
    return sorted(gop.values(), key=lambda g: -g["net_vnd"])


def _pod(don: List[Dict], hoan: Dict[str, int]) -> Optional[Dict[str, int]]:
    pod = [d for d in don if d.get("is_pod") is True]
    if not pod:
        return None
    net = sum(_net(d, hoan) for d in pod)
    phoi = sum(_v(it.get("base_cost")) * _sl(it) for d in pod for it in d.get("items") or [])
    return {"orders": len(pod), "net_vnd": net, "blank_cost_vnd": phoi, "profit_vnd": net - phoi}


def _vouchers(don: List[Dict], ma_shop: Set[str], hoan: Dict[str, int]) -> List[Dict[str, Any]]:
    gop: Dict[str, Dict[str, Any]] = {}
    for d in don:
        code = d.get("coupon_code")
        if code not in ma_shop:
            continue
        g = gop.setdefault(code, {"code": code, "title": "", "orders": 0, "cost_vnd": 0, "net_vnd": 0})
        g["orders"] += 1
        g["cost_vnd"] += _v(_fb(d).get("coupon_discount"))
        g["net_vnd"] += _net(d, hoan)
    for g in gop.values():
        g["avg_net_vnd"] = g["net_vnd"] // g["orders"]
    return sorted(gop.values(), key=lambda g: -g["cost_vnd"])


def _trung_binh(don: List[Dict], hoan: Dict[str, int]) -> int:
    return sum(_net(d, hoan) for d in don) // len(don)


def _so_sanh(don: List[Dict], ma_shop: Set[str], hoan: Dict[str, int]) -> Optional[Dict[str, int]]:
    co = [d for d in don if d.get("coupon_code") in ma_shop]
    khong = [d for d in don if not d.get("coupon_code")]  # đơn dùng voucher sàn không thuộc nhóm nào
    if len(co) < TOI_THIEU_SO_SANH or len(khong) < TOI_THIEU_SO_SANH:
        return None
    return {"with_orders": len(co), "with_avg_vnd": _trung_binh(co, hoan),
            "without_orders": len(khong), "without_avg_vnd": _trung_binh(khong, hoan)}


def tong_hop(don: List[Dict], ma_shop: Set[str], hoan: Dict[str, int], ngay: List[str],
             hoan_mon: Optional[Dict[str, int]] = None) -> Dict[str, Any]:
    return {"orders": len(don), "flow": _dong_tien(don, ma_shop, hoan),
            "by_day": _theo_ngay(don, hoan, ngay), "by_product": _theo_san_pham(don, hoan, hoan_mon or {}),
            "pod": _pod(don, hoan), "vouchers": _vouchers(don, ma_shop, hoan),
            "voucher_compare": _so_sanh(don, ma_shop, hoan)}
