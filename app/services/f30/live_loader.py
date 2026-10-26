from typing import Any, Dict, List

import numpy as np

from app.api.v1 import _live_data as live
from app.api.v1._live import LOC_SP_THAT, _so


def live_shop_ids() -> List[str]:
    return sorted({str(p["shop_id"]) for p in live.san_pham_that() if p.get("shop_id")})


def _san_pham_shop(shop_id: str) -> List[Dict[str, Any]]:
    return list(live.db_live()["products"].find(
        {**LOC_SP_THAT, "shop_id": live.oid(shop_id)}, {"title": 1}))


def load_shop(shop_id: str, days: List[str]) -> Dict[str, Any]:
    n = len(days)
    pos = {d: i for i, d in enumerate(days)}
    sp = _san_pham_shop(shop_id)
    ids = [str(p["_id"]) for p in sp]
    titles = {str(p["_id"]): p.get("title") or "" for p in sp}
    views = {pid: np.zeros(n) for pid in ids}
    revenue = {pid: np.zeros(n) for pid in ids}
    orders = {pid: np.zeros(n) for pid in ids}
    if not ids:
        return {"titles": titles, "views": views, "revenue": revenue, "orders": orders}

    tu = live.bat_dau(days[0])
    for e in live.su_kien(ids, tu):
        i = pos.get(live.ngay_vn(e.get("created_at")))
        if i is not None and e.get("event_type") == "view":
            views[str(e["product_id"])][i] += 1

    for don in live.don_hang(tu, shop_id, da_tra_tien=True):
        i = pos.get(live.ngay_vn(don.get("created_at")))
        if i is None:
            continue
        for it in don.get("items") or []:
            pid = str(it.get("product_id"))
            if pid in revenue:
                revenue[pid][i] += (_so(it.get("retail_price")) or 0) * int(it.get("quantity") or 1)
        for pid in {str(it.get("product_id")) for it in don.get("items") or []} & set(orders):
            orders[pid][i] += 1

    return {"titles": titles, "views": views, "revenue": revenue, "orders": orders}
