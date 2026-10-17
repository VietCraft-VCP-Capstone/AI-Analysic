import sys
from collections import defaultdict
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from fastapi import APIRouter

from app.api.v1._live import la_shop_live
from app.api.v1._live_competitor import so_sanh_live
from app.api.v1._mart import db
from app.api.v1._template import CurrentShop, insufficient, mart_not_ready, meta_from_record, ok

router = APIRouter()

MART = "mart_competitor"
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
    if la_shop_live(shop_id):
        kq = so_sanh_live(shop_id, TOI_THIEU_LISTING)
        return _so_sanh(shop_id, *kq) if isinstance(kq, tuple) else kq

    coll = db()[MART]
    if coll.estimated_document_count() == 0:
        mart_not_ready(MART)

    cua_toi = list(coll.find({"shop_id": shop_id},
                             {"_id": 0, "category_id": 1, "price_vnd": 1, "rating_shrunk": 1,
                              "product_type_id": 1, "revenue_90d_vnd": 1,
                              "computed_at": 1, "model_version": 1}))
    if not cua_toi:
        return insufficient("Shop chưa có listing nào nên chưa so sánh được")

    meta = meta_from_record(cua_toi[0], scope="shop", scope_id=shop_id, collection=MART,
                            mode="seed_demo", sample_size=len(cua_toi))

    if len(cua_toi) < TOI_THIEU_LISTING:
        return insufficient(
            f"Shop mới có {len(cua_toi)} listing, cần tối thiểu {TOI_THIEU_LISTING} "
            f"mới dựng được biểu đồ so sánh (BR-193)", meta)

    dem_cat = defaultdict(int)
    for r in cua_toi:
        dem_cat[r["category_id"]] += 1
    phan_khuc = max(dem_cat, key=dem_cat.get)

    trong_pk = list(coll.find({"category_id": phan_khuc},
                              {"_id": 0, "shop_id": 1, "shop_name": 1, "price_vnd": 1,
                               "rating_shrunk": 1, "product_type_id": 1, "revenue_90d_vnd": 1}))
    tho = defaultdict(lambda: {"n": 0, "gia": [], "sao": [], "loai": set(), "dt": 0})
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

    phan_hoi = {s["shop_id"]: float(s.get("response_time_minutes") or 0)
                for s in db()["shops"].find({}, {"shop_id": 1, "response_time_minutes": 1})}
    return _so_sanh(shop_id, phan_khuc,
                    f"{dem_cat[phan_khuc]}/{len(cua_toi)} listing của shop nằm ở danh mục này",
                    tho, phan_hoi, meta)


def _so_sanh(shop_id, phan_khuc, ly_do, tho, phan_hoi, meta):
    def truc_tho(sid, s):
        return {
            "listing_count": s["n"],
            "avg_rating": sum(s["sao"]) / len(s["sao"]) if s["sao"] else None,
            "response_speed": -phan_hoi.get(sid, 0),
            "avg_price": sum(s["gia"]) / len(s["gia"]) if s["gia"] else None,
            "product_diversity": len(s["loai"]),
        }

    tho_all = {sid: truc_tho(sid, s) for sid, s in tho.items()}
    cot = {t: [v[t] for v in tho_all.values() if v[t] is not None] for t in TRUC}

    def chuan(sid):
        return [_chuan_hoa(tho_all[sid][t], cot[t]) for t in TRUC]

    top = sorted((sid for sid in tho if sid != shop_id),
                 key=lambda s: -tho[s]["dt"])[:SO_DOI_THU]

    return ok({
        "segment": phan_khuc,
        "segment_reason": ly_do,
        "axes": TRUC,
        "axes_vi": TEN_TRUC_VI,
        "normalization": "min-max 0-100 trong phân khúc; 100 luôn là tốt hơn",
        "me": chuan(shop_id),
        "me_raw": {t: (round(v, 2) if isinstance(v, float) else v)
                   for t, v in tho_all[shop_id].items()},
        "competitors": [{
            "shop_id": sid,
            "shop_name": tho[sid].get("ten"),
            "values": chuan(sid),
            "est_revenue_90d_vnd": int(tho[sid]["dt"]),
        } for sid in top],
        "shops_in_segment": len(tho),
    }, meta)
