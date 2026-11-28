"""Định nghĩa "đơn hợp lệ" (đơn thể hiện cầu thật) dùng chung cho các phân tích.

Phải khớp với `isValidDemandOrder` ở backend (`seasonal-math.ts`):
không hủy, không hoàn tiền, không giả lập, đơn PayOS phải đã thanh toán.
Enum `order_status` thật: ORDERED, PENDING_DESIGN, PROCESSING, SHIPPING, DELIVERED, CANCELLED.
"""
from typing import Any, Dict

VALID_ORDER_FILTER: Dict[str, Any] = {
    "order_status": {"$ne": "CANCELLED"},
    "refund_status": {"$ne": "REFUNDED"},
    "payment_status": {"$ne": "REFUNDED"},
    "is_simulated": {"$ne": True},
    "$or": [{"payment_method": {"$ne": "PAYOS"}}, {"payment_status": "PAID"}],
}


def is_valid_demand_order(o: Dict[str, Any]) -> bool:
    if not o or o.get("is_simulated") is True:
        return False
    if str(o.get("order_status") or "").upper() == "CANCELLED":
        return False
    if o.get("refund_status") == "REFUNDED" or o.get("payment_status") == "REFUNDED":
        return False
    if o.get("payment_method") == "PAYOS" and o.get("payment_status") != "PAID":
        return False
    return True
