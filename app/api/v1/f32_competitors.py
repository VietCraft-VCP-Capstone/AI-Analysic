import sys
from pathlib import Path
from typing import Optional

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from fastapi import APIRouter

from app.api.v1._mart import db, tien
from app.api.v1._template import CurrentShop, insufficient, invalid_param, mart_not_ready, meta_from_record, ok

router = APIRouter()

TOP_N = 20
MART = "mart_competitor"


def _phan_vi(gia_tri, moc_list):
    """Phần trăm số phần tử nhỏ hơn hoặc bằng. Danh sách rỗng -> None, không phải 0."""
    if gia_tri is None or not moc_list:
        return None
    return round(sum(1 for m in moc_list if m <= gia_tri) / len(moc_list) * 100)


@router.get("/api/analytics/competitors", tags=["F32 · Nhi"])
def competitors(shop_id: str = CurrentShop, categoryId: Optional[str] = None):
    coll = db()[MART]
    if coll.estimated_document_count() == 0:
        mart_not_ready(MART)

    # BR-186: chỉ những danh mục người bán thật sự có hàng.
    cua_toi = sorted(coll.distinct("category_id", {"shop_id": shop_id}))
    if not cua_toi:
        return insufficient("Shop chưa có listing nào nên chưa so sánh được với ai")

    cat = categoryId or cua_toi[0]
    if cat not in cua_toi:
        invalid_param("categoryId", " | ".join(cua_toi))

    chieu = {"_id": 0, "listing_id": 1, "shop_id": 1, "shop_name": 1, "title": 1,
             "price_vnd": 1, "est_sales_90d": 1, "rating_shrunk": 1, "n_reviews": 1,
             "favorite_count": 1, "rank_in_cat": 1, "n_in_cat": 1,
             "computed_at": 1, "model_version": 1}

    trong_cat = list(coll.find({"category_id": cat}, chieu))
    cua_minh = [r for r in trong_cat if r["shop_id"] == shop_id]
    doi_thu = [r for r in trong_cat if r["shop_id"] != shop_id]        # BR-189

    meta = meta_from_record(trong_cat[0], scope="category", scope_id=cat, collection=MART,
                            mode="seed_demo", sample_size=len(trong_cat))

    if len(doi_thu) < 5:
        return insufficient(
            f"Danh mục `{cat}` chỉ có {len(doi_thu)} listing của shop khác, "
            f"chưa đủ để xếp hạng (cần từ 5)", meta)

    doi_thu.sort(key=lambda r: -r["est_sales_90d"])                     # BR-188
    gia_cat = sorted(r["price_vnd"] for r in trong_cat)
    sao_cat = sorted(r["rating_shrunk"] for r in trong_cat if r["rating_shrunk"] is not None)

    gia_toi = [r["price_vnd"] for r in cua_minh]
    sao_toi = [r["rating_shrunk"] for r in cua_minh if r["rating_shrunk"] is not None]
    gia_tb = sum(gia_toi) / len(gia_toi) if gia_toi else None
    sao_tb = sum(sao_toi) / len(sao_toi) if sao_toi else None

    return ok({
        "category_id": cat,
        "available_categories": cua_toi,
        "my_listings": [{
            "listing_id": r["listing_id"],
            "title": r.get("title"),
            "price_vnd": tien(r["price_vnd"]),
            "est_sales_90d": r["est_sales_90d"],
            "rating_shrunk": r["rating_shrunk"],
            "rank_in_cat": r.get("rank_in_cat"),
            "n_in_cat": r.get("n_in_cat"),
        } for r in sorted(cua_minh, key=lambda r: r.get("rank_in_cat") or 10**9)],
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
        } for i, r in enumerate(doi_thu[:TOP_N], 1)],
        "my_position": {
            # null khi chưa có căn cứ — shop chưa có đánh giá nào thì không có
            # phân vị sao, và đó KHÁC với "xếp chót".
            "price_percentile": _phan_vi(gia_tb, gia_cat),
            "rating_percentile": _phan_vi(sao_tb, sao_cat),
            "my_avg_price_vnd": tien(gia_tb) if gia_tb is not None else None,
            "my_avg_rating": round(sao_tb, 2) if sao_tb is not None else None,
        },
        "note": "est_sales_90d là ước lượng từ units_sold 90 ngày của dữ liệu mồi, không phải doanh số công bố.",
    }, meta)
