import sys
from collections import defaultdict
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from fastapi import APIRouter

from app.api.v1._competitor_live import meta_doi_thu, nguon_doi_thu
from app.api.v1._doi_thu_ai import nhom_chien_luoc
from app.api.v1._mart import db
from app.api.v1._template import CurrentShop, insufficient, ok

router = APIRouter()

TOI_THIEU_LISTING = 5       # BR-193
SO_DOI_THU = 5              # BR-191

TRUC = ["listing_count", "avg_rating", "response_speed", "avg_price", "product_diversity"]
TEN_TRUC_VI = ["Số sản phẩm", "Điểm đánh giá", "Tốc độ phản hồi", "Giá trung bình", "Độ đa dạng"]


def _chuan_hoa(gia_tri, tat_ca):
    """Min–max về 0–100 (BR-192). Mọi shop bằng nhau thì trả 50, không phải 0 hay 100."""
    if gia_tri is None:
        return None
    lo, hi = min(tat_ca), max(tat_ca)
    if hi == lo:
        return 50.0
    return round((gia_tri - lo) / (hi - lo) * 100, 1)


@router.get("/api/analytics/shop-comparison", tags=["F33 · Nhi"])
def shop_comparison(shop_id: str = CurrentShop):
    ng = nguon_doi_thu(shop_id)
    coll = ng["bang"]

    cua_toi = list(coll.find({"shop_id": shop_id},
                             {"_id": 0, "category_id": 1, "category_name": 1, "price_vnd": 1,
                              "rating_shrunk": 1, "product_type_id": 1, "revenue_90d_vnd": 1,
                              "computed_at": 1, "model_version": 1}))
    if not cua_toi:
        return insufficient("Shop chưa có sản phẩm nào nên chưa so sánh được")

    meta = meta_doi_thu(ng, cua_toi[0], scope="shop", scope_id=shop_id, sample_size=len(cua_toi))

    if len(cua_toi) < TOI_THIEU_LISTING:
        meta["unlock"] = {"requirement": "sản phẩm của shop", "unit": "sản phẩm",
                          "current": len(cua_toi), "target": TOI_THIEU_LISTING}
        return insufficient(
            f"Shop mới có {len(cua_toi)} sản phẩm, cần tối thiểu {TOI_THIEU_LISTING} "
            f"mới so sánh được với shop khác", meta)

    dem_cat = defaultdict(int)
    for r in cua_toi:
        dem_cat[r["category_id"]] += 1
    phan_khuc = max(dem_cat, key=dem_cat.get)

    trong_pk = list(coll.find({"category_id": phan_khuc},
                              {"_id": 0, "shop_id": 1, "shop_name": 1, "price_vnd": 1,
                               "rating_shrunk": 1, "product_type_id": 1, "revenue_90d_vnd": 1,
                               "shop_response_seconds": 1, "n_reviews": 1}))
    tho = defaultdict(lambda: {"n": 0, "gia": [], "sao": [], "loai": set(), "dt": 0, "dg": 0})
    for r in trong_pk:
        s = tho[r["shop_id"]]
        s["n"] += 1
        s["ten"] = r.get("shop_name")
        if r["price_vnd"]:
            s["gia"].append(r["price_vnd"])
        if r["rating_shrunk"] is not None:
            s["sao"].append(r["rating_shrunk"])
        s["loai"].add(r.get("product_type_id"))
        s["dt"] += r.get("revenue_90d_vnd") or 0
        s["dg"] += r.get("n_reviews") or 0

    if ng["live"]:
        # Giây -> phút cho cùng đơn vị với dữ liệu mồi; thiếu là CHƯA ĐO nên None, không phải 0.
        phan_hoi = {r["shop_id"]: (r["shop_response_seconds"] / 60 if r.get("shop_response_seconds") else None)
                    for r in trong_pk}
    else:
        phan_hoi = {s["shop_id"]: (float(s["response_time_minutes"]) if s.get("response_time_minutes") else None)
                    for s in db()["shops"].find({}, {"shop_id": 1, "response_time_minutes": 1})}

    def truc_tho(sid, s):
        ph = phan_hoi.get(sid)
        return {
            "listing_count": s["n"],
            "avg_rating": sum(s["sao"]) / len(s["sao"]) if s["sao"] else None,
            # Phản hồi nhanh là tốt -> đảo dấu để 100 luôn là "tốt" trên mọi trục.
            "response_speed": -ph if ph is not None else None,
            "avg_price": sum(s["gia"]) / len(s["gia"]) if s["gia"] else None,
            "product_diversity": len(s["loai"]),
        }

    # BR-191: top 5 theo doanh thu; sàn chưa có đơn thì doanh thu đều 0 nên hoà theo số đánh giá như BR-188.
    top = sorted((sid for sid in tho if sid != shop_id),
                 key=lambda s: (-tho[s]["dt"], -tho[s]["dg"], s))[:SO_DOI_THU]
    tho_all = {sid: truc_tho(sid, s) for sid, s in tho.items()}
    # BR-192: min–max trên đúng shop mình và 5 đối thủ, không trên cả phân khúc.
    cot = {t: [tho_all[sid][t] for sid in [shop_id, *top] if tho_all[sid][t] is not None] for t in TRUC}

    def chuan(sid):
        return [_chuan_hoa(tho_all[sid][t], cot[t]) for t in TRUC]

    def tho_tron(sid):
        return {t: (round(v, 2) if isinstance(v, float) else v) for t, v in tho_all[sid].items()}

    nhom, nhom_ly_do = nhom_chien_luoc(tho, phan_hoi, shop_id) if ng["live"] else (None, None)

    return ok({
        "segment": phan_khuc,
        **({"segment_name": next((r.get("category_name") for r in cua_toi if r["category_id"] == phan_khuc), None)}
           if ng["live"] else {}),
        "segment_reason": f"{dem_cat[phan_khuc]}/{len(cua_toi)} sản phẩm của shop nằm ở danh mục này",
        "axes": TRUC,
        "axes_vi": TEN_TRUC_VI,
        "normalization": "min-max 0-100 trên shop bạn và 5 đối thủ; 100 là tốt hơn, riêng giá: 100 là đắt nhất",
        "neutral_axes": ["avg_price"],
        "ranked_by": "revenue" if any(tho[s]["dt"] > 0 for s in top) else "reviews",
        "me": chuan(shop_id),
        "me_raw": tho_tron(shop_id),
        # Trục của shop mình chưa có số: FE không vẽ thành 0 và không tính là trục yếu nhất.
        "axes_missing": [t for t in TRUC if tho_all[shop_id][t] is None],
        "competitors": [{
            "shop_id": sid,
            "shop_name": tho[sid].get("ten"),
            "values": chuan(sid),
            "raw": tho_tron(sid),       # số thật, để FE so "bạn vs nhóm" bằng đơn vị người bán hiểu
        } for sid in top],
        "shops_in_segment": len(tho),
        **({"strategic_groups": nhom, "strategic_groups_reason": nhom_ly_do} if ng["live"] else {}),
    }, meta)
