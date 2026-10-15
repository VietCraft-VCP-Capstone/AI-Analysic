import sys
from pathlib import Path
from typing import List, Optional

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from fastapi import APIRouter

from app.api.v1._mart import db, tien
from app.api.v1._template import CurrentShop, insufficient, invalid_param, mart_not_ready, meta_from_record, ok

router = APIRouter()

MART = "mart_competitor"
TOP_BAN_CHAY = 20        # BR-198
TOI_THIEU = 8            # dưới ngưỡng này phân vị không có nghĩa

DAI = [(10, "far_below"), (30, "below"), (70, "competitive"), (90, "premium"), (101, "far_above")]


def _phan_vi_gia_tri(sap_xep: List[int], q: float) -> int:
    """Phân vị kiểu nội suy tuyến tính, không cần numpy."""
    if not sap_xep:
        return 0
    k = (len(sap_xep) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(sap_xep) - 1)
    return int(round(sap_xep[lo] + (sap_xep[hi] - sap_xep[lo]) * (k - lo)))


@router.get("/api/analytics/pricing", tags=["F35 · Nhi"])
def pricing(shop_id: str = CurrentShop,
            productType: Optional[str] = None,
            price: Optional[float] = None):
    coll = db()[MART]
    if coll.estimated_document_count() == 0:
        mart_not_ready(MART)

    cua_toi = sorted(coll.distinct("product_type_id", {"shop_id": shop_id}))
    if not cua_toi:
        return insufficient("Shop chưa có listing nào nên chưa so giá được")

    pt = productType or cua_toi[0]
    if pt not in cua_toi:
        invalid_param("productType", " | ".join(cua_toi[:12]) + (" ..." if len(cua_toi) > 12 else ""))

    rows = list(coll.find({"product_type_id": pt},
                          {"_id": 0, "price_vnd": 1, "est_sales_90d": 1, "shop_id": 1,
                           "computed_at": 1, "model_version": 1}))
    meta = meta_from_record(rows[0], scope="product_type", scope_id=pt, collection=MART,
                            mode="seed_demo", sample_size=len(rows))

    ban_chay = sorted(rows, key=lambda r: -r["est_sales_90d"])[:TOP_BAN_CHAY]
    gia = sorted(r["price_vnd"] for r in ban_chay if r["price_vnd"] > 0)

    if len(gia) < TOI_THIEU:
        return insufficient(
            f"Loại `{pt}` chỉ có {len(gia)} listing có giá trong nhóm bán chạy, "
            f"cần tối thiểu {TOI_THIEU} mới dựng được phân bố", meta)

    pb = {"min": gia[0], "max": gia[-1],
          **{f"p{int(q*100)}": _phan_vi_gia_tri(gia, q) for q in (0.10, 0.25, 0.50, 0.75, 0.90)}}

    gia_toi = price
    if gia_toi is None:
        cua_minh = [r["price_vnd"] for r in rows if r["shop_id"] == shop_id and r["price_vnd"] > 0]
        gia_toi = sum(cua_minh) / len(cua_minh) if cua_minh else None

    if gia_toi is None:
        pv = dai = None
    else:
        pv = round(sum(1 for g in gia if g <= gia_toi) / len(gia) * 100)
        dai = next(ten for nguong, ten in DAI if pv < nguong)

    return ok({
        "product_type_id": pt,
        "available_product_types": cua_toi,
        "n_listings": len(gia),
        "basis": f"top {len(gia)} listing bán chạy nhất trong {len(rows)} listing cùng loại (BR-198)",
        "distribution": pb,
        "my_price": tien(gia_toi) if gia_toi is not None else None,
        "percentile": pv,
        "band": dai,
        "suggested_range": {
            "low": pb["p25"], "high": pb["p75"],
            "basis": "khoảng giá liên phân vị của nhóm bán chạy nhất",
            "caveat": "tương quan — giá nằm trong khoảng này không đảm bảo bán được",
        },
    }, meta)
