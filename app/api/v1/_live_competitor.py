from collections import Counter
from typing import Any, Dict, List

from app.api.v1._live import db_live, san_pham_live
from app.api.v1._live_data import bat_dau, cac_ngay, danh_muc, oid, san_pham_that, tong_theo_san_pham
from app.api.v1._template import build_meta, insufficient

CUA_SO_DOANH_SO = 90


def _meta(shop_id: str, model: str, n: int, unlock: Dict[str, Any]):
    return build_meta(model_version=model, scope="shop", scope_id=shop_id, database="vietcraft",
                      collection="products", mode="live", attributed_to_live_shop=True,
                      sample_size=n, confidence="medium" if n >= unlock["target"] else "low",
                      unlock=unlock)


def _ban_90_ngay(ids: List[str]) -> Dict[str, Dict[str, float]]:
    return tong_theo_san_pham(ids, bat_dau(cac_ngay(CUA_SO_DOANH_SO)[0]))


def so_sanh_live(shop_id: str, toi_thieu_sp: int):
    cua_toi = san_pham_live(shop_id)
    meta = _meta(shop_id, "live-compare-1.0", len(cua_toi),
                 {"requirement": "sản phẩm của shop", "unit": "sản phẩm",
                  "current": len(cua_toi), "target": toi_thieu_sp})
    if len(cua_toi) < toi_thieu_sp:
        return insufficient(f"Shop mới có {len(cua_toi)} sản phẩm, cần tối thiểu {toi_thieu_sp} "
                            f"mới dựng được biểu đồ so sánh (BR-193)", meta)

    dem = Counter((p["categories"] or [None])[0] for p in cua_toi)
    phan_khuc = dem.most_common(1)[0][0]
    cung = [q for q in san_pham_that() if danh_muc(q) == phan_khuc]
    shops = {str(q["shop_id"]) for q in cung} | {shop_id}
    if len(shops) < 2:
        meta["unlock"] = {"requirement": "shop khác cùng danh mục", "unit": "shop", "current": 0, "target": 1}
        return insufficient(f"Danh mục {phan_khuc} chưa có shop nào khác trên sàn để so sánh.", meta)

    ban = _ban_90_ngay([str(q["_id"]) for q in cung])
    thong_tin = {str(s["_id"]): s for s in db_live()["shops"].find(
        {"_id": {"$in": [oid(s) for s in shops]}},
        {"shop_name": 1, "average_response_time_seconds": 1})}
    tho = {}
    for sid in shops:
        sp = [p for p in san_pham_live(sid) if (p["categories"] or [None])[0] == phan_khuc]
        tho[sid] = {
            "n": len(sp),
            "ten": (thong_tin.get(sid) or {}).get("shop_name"),
            "gia": [p["price_vnd"] for p in sp if p["price_vnd"]],
            "sao": [p["rating"] for p in sp if p["n_reviews"] and p["rating"] is not None],
            "loai": {p["product_type_id"] for p in sp},
            "dt": sum(ban[p["product_id"]]["revenue_vnd"] for p in sp),
        }
    phan_hoi = {sid: float((thong_tin.get(sid) or {}).get("average_response_time_seconds") or 0) / 60
                for sid in shops}
    ly_do = f"{dem[phan_khuc]}/{len(cua_toi)} sản phẩm của shop nằm ở danh mục này"
    return phan_khuc, ly_do, tho, phan_hoi, meta


def tag_live(shop_id: str, toi_thieu_doi_thu: int):
    tat_ca = san_pham_that()
    cua_toi = sorted({str(danh_muc(p)) for p in tat_ca if str(p["shop_id"]) == shop_id and danh_muc(p)})
    meta = _meta(shop_id, "live-tag-gap-1.0", len(tat_ca),
                 {"requirement": "sản phẩm đối thủ cùng danh mục", "unit": "sản phẩm",
                  "current": 0, "target": toi_thieu_doi_thu})
    ban = _ban_90_ngay([str(p["_id"]) for p in tat_ca])
    hang = [{"shop_id": str(p["shop_id"]), "category_id": danh_muc(p), "tags": p.get("tags") or [],
             "est_sales_90d": ban[str(p["_id"])]["units"]} for p in tat_ca]
    return cua_toi, hang, meta
