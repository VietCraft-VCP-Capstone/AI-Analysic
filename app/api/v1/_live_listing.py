import statistics
from collections import Counter
from typing import Any, Dict

from app.api.v1._live import LOC_SP_THAT, db_live
from app.api.v1._live_data import (
    bat_dau, cac_ngay, chuoi_ngay, danh_muc, ngay_vn, oid, san_pham_that, su_kien, tong_theo_san_pham,
)
from app.api.v1._template import build_meta, forbidden, insufficient, not_found
from app.core.build_marts import _phan_tram, chi_so_pheu

CUA_SO_PHEU = 90


def san_pham_cua_shop(pid: str, shop_id: str) -> Dict[str, Any]:
    p = db_live()["products"].find_one({"_id": oid(pid), **LOC_SP_THAT},
                                       {"shop_id": 1, "title": 1, "categories": 1})
    if p is None:
        not_found("listing")
    if str(p.get("shop_id")) != shop_id:
        forbidden()
    return p


def _meta(pid: str, n: int, unlock=None):
    return build_meta(model_version="live-read-1.0", scope="listing", scope_id=pid,
                      database="vietcraft", collection="product_events", mode="live",
                      attributed_to_live_shop=True, sample_size=n,
                      confidence="high" if n >= 100 else "medium" if n >= 30 else "low", unlock=unlock)


def timeseries_live(pid: str, shop_id: str, so_ngay: int):
    p = san_pham_cua_shop(pid, shop_id)
    ngay = cac_ngay(so_ngay)
    theo_ngay = chuoi_ngay([pid], ngay)
    chuoi = [{"date": d, **theo_ngay[d]} for d in ngay]
    meta = _meta(pid, sum(c["views"] for c in chuoi))
    if not any(c["views"] or c["orders"] for c in chuoi):
        return insufficient(f"Sản phẩm chưa có lượt xem hay đơn nào trong {so_ngay} ngày qua.", meta)

    ban = [str(q["_id"]) for q in san_pham_that() if danh_muc(q) == danh_muc(p) and str(q["_id"]) != pid]
    dem = Counter((str(e["product_id"]), ngay_vn(e.get("created_at")))
                  for e in su_kien(ban, bat_dau(ngay[0])) if e["event_type"] == "view")
    ban = [b for b in ban if any(dem[(b, d)] for d in ngay)]
    trung_vi = [{"date": d, "views": round(statistics.median(dem[(b, d)] for b in ban), 1)}
                for d in ngay] if ban else []
    return {"title": p.get("title"), "category_id": danh_muc(p), "from": ngay[0], "to": ngay[-1],
            "series": chuoi, "category_median": trung_vi}, meta


def conversion_live(pid: str, shop_id: str, toi_thieu_view: int):
    p = san_pham_cua_shop(pid, shop_id)
    ngay = cac_ngay(CUA_SO_PHEU)
    cung = [str(q["_id"]) for q in san_pham_that() if danh_muc(q) == danh_muc(p)]
    tong = tong_theo_san_pham(set(cung) | {pid}, bat_dau(ngay[0]))
    r = tong[pid]
    co_ban = any(q != pid and tong[q]["views"] for q in cung)
    moc = _phan_tram(sum(t["orders"] for t in tong.values()), sum(t["views"] for t in tong.values())) if co_ban else None
    meta = _meta(pid, int(r["views"]), {"requirement": f"lượt xem/listing, {CUA_SO_PHEU} ngày",
                                         "unit": "lượt xem", "current": int(r["views"]),
                                         "target": toi_thieu_view})
    if r["views"] < toi_thieu_view:
        return insufficient(
            f"Sản phẩm mới có {int(r['views'])} lượt xem trong {CUA_SO_PHEU} ngày, "
            f"cần tối thiểu {toi_thieu_view} thì tỉ lệ % mới có nghĩa", meta)
    return {
        "listing_id": pid,
        "title": p.get("title"),
        "funnel": {"views": int(r["views"]), "carts": int(r["carts"]), "orders": int(r["orders"])},
        **chi_so_pheu(r["views"], r["carts"], r["orders"], moc),
        "category_id": danh_muc(p),
        "window": {"from": ngay[0], "to": ngay[-1]},
    }, meta
