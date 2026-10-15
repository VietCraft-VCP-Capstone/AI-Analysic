"""
F32 · GET /api/analytics/competitors?categoryId= — mình đứng đâu so với đối thủ.

Đọc mart `mart_competitor` (5.000 dòng, do app/core/build_marts.py ghi).

  BR-186  chỉ liệt kê danh mục mà người bán có ít nhất 1 listing
  BR-188  top 20 xếp theo est_sales_90d giảm dần
  BR-189  loại shop của chính người bán khỏi bảng xếp hạng, vẫn hiện ở my_listings

Chạy cho hai loại shop:

  shop dữ liệu mồi  cả hai phía đều từ mart                     -> mode seed_demo
  shop thật         SẢN PHẨM VÀ GIÁ CỦA BẠN là thật trên sàn,
                    nhóm đối thủ lấy từ catalog tham chiếu vì
                    sàn chưa đủ shop để xếp hạng         -> mode derived
"""

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from fastapi import APIRouter

from app.api.v1._live import la_shop_live, san_pham_live
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


def _danh_muc_cua_loai(coll, loai: List[str]) -> Dict[str, str]:
    """Mã loại phôi sang mã danh mục, tra bằng chính mart.

    Đây là cách nối hai miền mà không bịa: mart đã có sẵn cặp product_type_id và
    category_id, nên chỉ cần tra, không cần tự đặt bảng ánh xạ danh mục.
    """
    ra: Dict[str, str] = {}
    for pt in loai:
        d = coll.find_one({"product_type_id": pt}, {"_id": 0, "category_id": 1})
        if d and d.get("category_id"):
            ra[pt] = d["category_id"]
    return ra


def _competitors_live(shop_id: str, categoryId: Optional[str]):
    coll = db()[MART]
    if coll.estimated_document_count() == 0:
        mart_not_ready(MART)

    sp = san_pham_live(shop_id)
    if not sp:
        return insufficient("Shop bạn chưa có sản phẩm nào trên sàn nên chưa so sánh được với ai")

    loai = sorted({p["product_type_id"] for p in sp if p["product_type_id"]})
    map_cat = _danh_muc_cua_loai(coll, loai)
    cua_toi_cat = sorted(set(map_cat.values()))

    if not cua_toi_cat:
        return insufficient(
            f"Chưa ánh xạ được sản phẩm nào của shop sang danh mục của catalog tham chiếu. "
            f"{len([p for p in sp if p['type_source'] == 'handmade'])} trên {len(sp)} sản phẩm là "
            f"đồ thủ công, không có loại phôi in theo yêu cầu tương ứng để so.",
            meta_from_record({}, scope="shop", scope_id=shop_id, collection=MART,
                             mode="derived", attributed_to_live_shop=True, sample_size=len(sp)),
        )

    cat = categoryId or cua_toi_cat[0]
    if cat not in cua_toi_cat:
        invalid_param("categoryId", " | ".join(cua_toi_cat))

    chieu = {"_id": 0, "listing_id": 1, "shop_id": 1, "shop_name": 1, "title": 1,
             "price_vnd": 1, "est_sales_90d": 1, "rating_shrunk": 1, "n_reviews": 1,
             "favorite_count": 1, "computed_at": 1, "model_version": 1}
    trong_cat = list(coll.find({"category_id": cat}, chieu))
    if len(trong_cat) < 5:
        return insufficient(f"Danh mục `{cat}` trong catalog tham chiếu chỉ có {len(trong_cat)} sản phẩm, chưa đủ để xếp hạng")

    meta = meta_from_record(trong_cat[0], scope="category", scope_id=cat, collection=MART,
                            mode="derived", attributed_to_live_shop=True, sample_size=len(trong_cat))

    doi_thu = sorted(trong_cat, key=lambda r: -r["est_sales_90d"])      # BR-188
    gia_cat = sorted(r["price_vnd"] for r in trong_cat)
    sao_cat = sorted(r["rating_shrunk"] for r in trong_cat if r["rating_shrunk"] is not None)

    # Sản phẩm THẬT của shop thuộc danh mục đang xem.
    loai_trong_cat = {pt for pt, c in map_cat.items() if c == cat}
    cua_minh = [p for p in sp if p["product_type_id"] in loai_trong_cat]

    gia_toi = [p["price_vnd"] for p in cua_minh if p["price_vnd"]]
    sao_toi = [p["rating"] for p in cua_minh if p["rating"]]
    gia_tb = sum(gia_toi) / len(gia_toi) if gia_toi else None
    sao_tb = sum(sao_toi) / len(sao_toi) if sao_toi else None

    return ok({
        "category_id": cat,
        "available_categories": cua_toi_cat,
        "my_listings": [{
            "listing_id": p["product_id"],
            "title": p["title"],
            "price_vnd": tien(p["price_vnd"]) if p["price_vnd"] else 0,
            "est_sales_90d": 0,
            "rating_shrunk": p["rating"],
            "rank_in_cat": _phan_vi(p["price_vnd"], gia_cat) or 0,
            "n_in_cat": len(trong_cat),
            "product_type_id": p["product_type_id"],
            "type_source": p["type_source"],
        } for p in sorted(cua_minh, key=lambda p: -(p["price_vnd"] or 0))],
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
            "price_percentile": _phan_vi(gia_tb, gia_cat),
            "rating_percentile": _phan_vi(sao_tb, sao_cat),
            "my_avg_price_vnd": tien(gia_tb) if gia_tb is not None else None,
            "my_avg_rating": round(sao_tb, 2) if sao_tb is not None else None,
        },
        "note": (
            "SẢN PHẨM VÀ GIÁ CỦA BẠN là dữ liệu thật trên sàn. NHÓM ĐỐI THỦ lấy từ catalog "
            "tham chiếu của ngành in theo yêu cầu, không phải shop thật trên VietCraft, vì sàn "
            "chưa có đủ shop cùng ngành có đơn để xếp hạng cạnh tranh. "
            "Cột doanh số ước lượng của bạn để 0 vì chưa nối được đơn hàng thật sang bảng này. "
            "Hạng trong danh mục ở bảng của bạn là PHÂN VỊ GIÁ, không phải hạng doanh số."
        ),
    }, meta)


@router.get("/api/analytics/competitors", tags=["F32 · Nhi"])
def competitors(shop_id: str = CurrentShop, categoryId: Optional[str] = None):
    if la_shop_live(shop_id):
        return _competitors_live(shop_id, categoryId)

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
