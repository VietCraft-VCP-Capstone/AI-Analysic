import sys
from pathlib import Path
from typing import Optional

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from fastapi import APIRouter

from app.api.v1._competitor_live import danh_muc_cua_toi, meta_doi_thu, mo_ta_live, nguon_doi_thu, ten_tag_live
from app.api.v1._doi_thu_ai import may_giong, shop_canh_tranh_nhat
from app.api.v1._mart import tien
from app.api.v1._template import CurrentShop, insufficient, invalid_param, ok

router = APIRouter()

TOP_N = 20

GHI_CHU = {
    "seed_demo": "Cột \"Đã bán (90 ngày)\" là ước lượng từ units_sold 90 ngày của dữ liệu mồi, không phải doanh số công bố.",
    "live": ("Cột \"Đã bán (90 ngày)\" là số sản phẩm đã giao thành công trong 90 ngày trên sàn. "
             "Đơn huỷ, đơn chưa giao và đơn mô phỏng không được tính."),
}


TOI_THIEU_PHAN_VI = 5


def _phan_vi(gia_tri, moc_list):
    """Phân vị mid-rank so với sản phẩm của shop KHÁC; dưới 5 mốc thì None (một mình không 'cao hơn 100%')."""
    if gia_tri is None or len(moc_list) < TOI_THIEU_PHAN_VI:
        return None
    duoi = sum(1 for m in moc_list if m < gia_tri) + 0.5 * sum(1 for m in moc_list if m == gia_tri)
    return round(duoi / len(moc_list) * 100)


@router.get("/api/analytics/competitors", tags=["F32 · Nhi"])
def competitors(shop_id: str = CurrentShop, categoryId: Optional[str] = None):
    ng = nguon_doi_thu(shop_id)
    coll = ng["bang"]

    cua_toi, chinh, ten_dm = danh_muc_cua_toi(coll, shop_id)
    if not cua_toi:
        return insufficient("Shop chưa có sản phẩm nào nên chưa so sánh được với ai")

    cat = categoryId or chinh
    if cat not in cua_toi:
        invalid_param("categoryId", " | ".join(cua_toi))

    chieu = {"_id": 0, "listing_id": 1, "shop_id": 1, "shop_name": 1, "title": 1,
             "price_vnd": 1, "est_sales_90d": 1, "rating_shrunk": 1, "n_reviews": 1,
             "favorite_count": 1, "rank_in_cat": 1, "n_in_cat": 1,
             "computed_at": 1, "model_version": 1}

    trong_cat = list(coll.find({"category_id": cat}, chieu))
    cua_minh = [r for r in trong_cat if r["shop_id"] == shop_id]
    doi_thu = [r for r in trong_cat if r["shop_id"] != shop_id]

    meta = meta_doi_thu(ng, trong_cat[0], scope="category", scope_id=cat, sample_size=len(trong_cat))

    doi_thu.sort(key=lambda r: (-r["est_sales_90d"], -(r.get("n_reviews") or 0), r.get("rank_in_cat") or 0))   # BR-188
    # Chưa có đơn (đang xếp theo số đánh giá) hoặc ít đối thủ thì thứ hạng chưa chắc: không để mặc định "medium".
    co_don = any(r["est_sales_90d"] for r in doi_thu)
    meta["quality"]["confidence"] = "medium" if co_don and len(doi_thu) >= TOI_THIEU_PHAN_VI else "low"
    gia_cat = [r["price_vnd"] for r in doi_thu]
    sao_cat = [r["rating_shrunk"] for r in doi_thu if r["rating_shrunk"] is not None]

    gia_toi = [r["price_vnd"] for r in cua_minh]
    sao_toi = [r["rating_shrunk"] for r in cua_minh if r["rating_shrunk"] is not None]
    gia_tb = sum(gia_toi) / len(gia_toi) if gia_toi else None
    sao_tb = sum(sao_toi) / len(sao_toi) if sao_toi else None
    # Đối thủ trực tiếp theo nội dung sản phẩm (AI), chỉ có ở shop thật.
    may = may_giong(coll, mo_ta_live, ten_tag_live) if ng["live"] else None

    return ok({
        "category_id": cat,
        "available_categories": cua_toi,
        # SRS 3.9.1: ít đối thủ vẫn hiện đúng số đang có; dưới 5 thì FE ghi thứ hạng chỉ để tham khảo.
        "low_sample": len(doi_thu) < TOI_THIEU_PHAN_VI,
        # Danh mục của sàn không có nhãn cứng ở FE như dữ liệu mồi nên trả kèm tên.
        **({"category_names": ten_dm} if ng["live"] else {}),
        "my_listings": [{
            "listing_id": r["listing_id"],
            "title": r.get("title"),
            "price_vnd": tien(r["price_vnd"]),
            "est_sales_90d": r["est_sales_90d"],
            "rating_shrunk": r["rating_shrunk"],
            "n_reviews": r.get("n_reviews") or 0,
            "favorite_count": r.get("favorite_count") or 0,
            "rank_in_cat": r.get("rank_in_cat"),
            "n_in_cat": r.get("n_in_cat"),
            **({"direct_rivals": may.doi_thu_truc_tiep(r["listing_id"])} if may else {}),
        } for r in sorted(cua_minh, key=lambda r: r.get("rank_in_cat") or 10**9)],
        **({"direct_rival_shops": shop_canh_tranh_nhat(may, [r["listing_id"] for r in cua_minh])} if may else {}),
        "competitors": [{
            "rank": i,
            "listing_id": r["listing_id"],
            "shop_name": r.get("shop_name"),
            "title": r.get("title"),
            "price_vnd": tien(r["price_vnd"]),
            "est_sales_90d": r["est_sales_90d"],
            "rating_shrunk": r["rating_shrunk"],
            "n_reviews": r["n_reviews"],
            "favorite_count": r["favorite_count"],
            # Shop thật: kèm mã shop để bấm "Theo dõi" ngay trên bảng.
            **({"shop_id": r["shop_id"]} if ng["live"] else {}),
        } for i, r in enumerate(doi_thu[:TOP_N], 1)],
        "my_position": {
            "price_percentile": _phan_vi(gia_tb, gia_cat),
            "rating_percentile": _phan_vi(sao_tb, sao_cat),
            "my_avg_price_vnd": tien(gia_tb) if gia_tb is not None else None,
            "my_avg_rating": round(sao_tb, 2) if sao_tb is not None else None,
        },
        "note": GHI_CHU[ng["mode"]],
    }, meta)
