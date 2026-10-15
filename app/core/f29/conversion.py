"""Trục chuyển đổi (plan §4.1, §8 S1): tỉ lệ mua 30 ngày so với mặt bằng."""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.api.v1._live import LOC_DON_THAT, LOC_SP_THAT
from app.core.f29.constants import (
    CONVERSION_WINDOW_DAYS,
    CR_INDEX_CAP,
    MIN_CONVERSION_PEERS,
    MIN_VIEWS_CONVERSION,
)
from app.core.f29.scoring import category_key


def conversion_stats(live_db) -> Dict[str, Any]:
    """Lượt xem đọc thẳng `product_events` (BE đã gộp trùng theo phiên 30 phút).
    Mỗi đơn thật, không huỷ, tính một lần mua cho mỗi sản phẩm trong đơn."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=CONVERSION_WINDOW_DAYS)

    products = {
        str(p["_id"]): category_key(p)
        for p in live_db["products"].find(LOC_SP_THAT, {"_id": 1, "category_ids": 1})
    }

    views: Dict[str, int] = {}
    for ev in live_db["product_events"].find(
        {"event_type": "view", "created_at": {"$gte": cutoff}}, {"product_id": 1}
    ):
        pid = str(ev.get("product_id"))
        if pid in products:
            views[pid] = views.get(pid, 0) + 1

    orders: Dict[str, int] = {}
    for o in live_db["orders"].find(
        {**LOC_DON_THAT, "created_at": {"$gte": cutoff}, "order_status": {"$ne": "CANCELLED"}},
        {"items.product_id": 1},
    ):
        for pid in {str(i.get("product_id")) for i in (o.get("items") or [])}:
            if pid in products:
                orders[pid] = orders.get(pid, 0) + 1

    qualified = [pid for pid, v in views.items() if v >= MIN_VIEWS_CONVERSION]

    def pooled(pids: List[str]) -> Optional[float]:
        v = sum(views[p] for p in pids)
        return (sum(orders.get(p, 0) for p in pids) / v) if v else None

    by_cat: Dict[Any, List[str]] = {}
    for pid in qualified:
        by_cat.setdefault(products[pid], []).append(pid)

    return {
        "views": views,
        "orders": orders,
        "category_of": products,
        "category_baseline": {
            c: pooled(pids) for c, pids in by_cat.items()
            if c is not None and len(pids) >= MIN_CONVERSION_PEERS
        },
        "platform_baseline": pooled(qualified) if len(qualified) >= MIN_CONVERSION_PEERS else None,
        "n_qualified": len(qualified),
    }


def conversion_score(stats: Dict[str, Any], product_id: str) -> Tuple[Optional[float], Dict[str, Any]]:
    """Chỉ số = tỉ lệ mua ÷ mặt bằng, chặn trần 2,0, quy về 0-100 (bằng mặt bằng = 50).
    `detail` cho giao diện giải thích vì sao chưa tính hoặc so trên mặt bằng nào."""
    pid = str(product_id)
    n_views = stats["views"].get(pid, 0)
    n_orders = stats["orders"].get(pid, 0)
    detail: Dict[str, Any] = {
        "views_30d": n_views,
        "orders_30d": n_orders,
        "min_views": MIN_VIEWS_CONVERSION,
        "conversion_rate": None,
        "baseline_rate": None,
        "baseline_scope": None,
        "reason": None,
    }

    if n_views < MIN_VIEWS_CONVERSION:
        detail["reason"] = "not_enough_views"
        return None, detail

    cr = n_orders / n_views
    detail["conversion_rate"] = round(cr, 4)

    cat = stats["category_of"].get(pid)
    baseline = stats["category_baseline"].get(cat)
    scope = "category"
    if baseline is None:
        baseline, scope = stats["platform_baseline"], "platform"
    if baseline is None:
        detail["reason"] = "not_enough_peers"
        return None, detail
    if baseline <= 0:
        # Cả mặt bằng chưa ai mua: chấm 0 hay 100 đều không công bằng.
        detail["reason"] = "no_orders_in_baseline"
        return None, detail

    detail["baseline_rate"] = round(baseline, 4)
    detail["baseline_scope"] = scope
    index = min(CR_INDEX_CAP, cr / baseline)
    return round(index * 50.0, 1), detail
