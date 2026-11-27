"""Gợi ý số lượng chuẩn bị cho một sản phẩm có sẵn hàng (mô hình newsvendor).

Nhu cầu trong kỳ ~ Poisson(λ = nhịp bán ngày thường của chính sản phẩm × số ngày). Đây là mức
"nếu bán như ngày thường"; chưa có số đo độ tăng đơn của dịp nên không nhân hệ số mùa vụ.
Q* = phân vị Poisson tại tỷ lệ tới hạn cu / (cu + co):
- cu (thiếu 1 cái) = lãi mất đi = giá − vốn − phí sàn
- co (dư 1 cái)   = vốn − giá thu hồi khi thanh lý (salvage_pct × vốn, là GIẢ ĐỊNH, chỉnh được)
"""
from typing import Any, Dict, Optional

from scipy.stats import poisson

DEFAULT_SALVAGE_PCT = 0.30
POD_TYPES = {"POD_TEMPLATE", "CUSTOM_DESIGN_REQUEST"}


def stock_plan(
    units_per_day: Optional[float],
    window_days: int,
    price: Optional[float],
    cost: Optional[float],
    fee_rate: float,
    salvage_pct: float = DEFAULT_SALVAGE_PCT,
    current_stock: int = 0,
    product_type: Optional[str] = None,
) -> Dict[str, Any]:
    base = {"recommended_qty": None, "to_add": None, "salvage_pct": salvage_pct, "window_days": window_days}
    if product_type in POD_TYPES:
        return {**base, "mode": "print_on_demand", "recommended_qty": 0, "to_add": 0}
    if units_per_day is None or units_per_day <= 0:
        return {**base, "mode": "no_sales_history"}
    if not price or not cost:
        return {**base, "mode": "missing_cost"}

    under = price - cost - price * fee_rate
    over = cost - cost * salvage_pct
    if under <= 0:
        return {**base, "mode": "unprofitable", "recommended_qty": 0, "to_add": 0}

    lam = units_per_day * window_days
    cr = under / (under + over)
    q = int(poisson.ppf(cr, lam))
    p10, p90 = int(poisson.ppf(0.1, lam)), int(poisson.ppf(0.9, lam))
    return {
        **base,
        "mode": "stock",
        "demand": {"p10": p10, "p50": round(lam, 1), "p90": p90},
        "critical_ratio": round(cr, 2),
        "unit_margin_vnd": round(under),
        "unit_overstock_loss_vnd": round(over),
        "recommended_qty": q,
        "current_stock": int(current_stock or 0),
        "to_add": max(0, q - int(current_stock or 0)),
        "worst_case_loss_vnd": round(max(0, q - p10) * over),
    }
