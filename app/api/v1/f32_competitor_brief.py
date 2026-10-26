from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from app.api.v1._competitor_live import dong_live, mo_ta_live, ten_tag_live, theo_doi_live
from app.api.v1._doi_thu_ai import gia_de_xuat, may_giong
from app.api.v1._doi_thu_ke_hoach import gom_su_that, lap_ke_hoach
from app.api.v1._live import la_shop_live, san_pham_live
from app.api.v1._template import CurrentShop, build_meta, insufficient, ok
from app.api.v1.f32_competitors import competitors
from app.api.v1.f33_shop_comparison import shop_comparison
from app.api.v1.f34_tag_gap import tag_gap
from app.api.v1.f36_competitor_tracking import TOI_DA

router = APIRouter()


def _data(goi) -> dict:
    """`data` của một tab; tab nào lỗi hay chưa đủ dữ liệu thì bỏ qua, kế hoạch vẫn lập từ các tab còn lại."""
    try:
        return goi().get("data") or {}
    except HTTPException:
        return {}


@router.get("/api/analytics/competitor-brief", tags=["F32 · Hạt"])
def competitor_brief(shop_id: str = CurrentShop):
    meta = build_meta(model_version="competitor-brief-1.0", scope="shop", scope_id=shop_id, database="vietcraft",
                      collection="products", mode="derived", attributed_to_live_shop=True)
    if not la_shop_live(shop_id):
        return insufficient("Kế hoạch tuần này chỉ lập cho shop thật đang bán trên sàn.", meta)
    may = may_giong(dong_live(), mo_ta_live, ten_tag_live)
    gia = [{"product_id": p["product_id"], "title": p["title"], "my_price": p["price_vnd"],
            "ai_price": gia_de_xuat(may, p["product_id"])[0]} for p in san_pham_live(shop_id)]
    su = gom_su_that(_data(lambda: competitors(shop_id=shop_id, categoryId=None)),
                     _data(lambda: shop_comparison(shop_id=shop_id)),
                     _data(lambda: tag_gap(shop_id=shop_id, categoryId=None)),
                     gia, _data(lambda: theo_doi_live(shop_id, TOI_DA)))
    meta["sample_size"] = len(su)
    return ok({**lap_ke_hoach(shop_id, su), "facts_count": len(su),
               "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")}, meta)
