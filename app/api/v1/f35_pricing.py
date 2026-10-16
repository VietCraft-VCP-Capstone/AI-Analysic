import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from fastapi import APIRouter

from app.api.v1._live import (
    gia_cung_danh_muc_live,
    la_shop_live,
    san_pham_live,
)
from app.api.v1._mart import db, tien
from app.api.v1._template import (
    CurrentShop,
    build_meta,
    insufficient,
    invalid_param,
    mart_not_ready,
    meta_from_record,
    ok,
)

router = APIRouter()

MART = "mart_competitor"
TOP_BAN_CHAY = 20        # BR-198
TOI_THIEU = 8            # dưới ngưỡng này phân vị không có nghĩa

DAI = [(10, "far_below"), (30, "below"), (70, "competitive"), (90, "premium"), (101, "far_above")]

# Giải thích nguồn mã loại phôi. Người bán cần biết mã này do họ chọn hay do máy đoán.
NGUON_LOAI = {
    "seller": "bạn tự chọn",
    "vi": "máy đoán từ tên sản phẩm",
    "en": "máy đoán từ tên sản phẩm",
    "handmade": "sản phẩm thủ công, không có loại phôi in theo yêu cầu tương ứng",
    "unknown": "chưa đoán được từ tên sản phẩm",
}


def _phan_vi_gia_tri(sap_xep: List[int], q: float) -> int:
    """Phân vị kiểu nội suy tuyến tính, không cần numpy."""
    if not sap_xep:
        return 0
    k = (len(sap_xep) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(sap_xep) - 1)
    return int(round(sap_xep[lo] + (sap_xep[hi] - sap_xep[lo]) * (k - lo)))


def _phan_bo(gia: List[int]) -> Dict[str, int]:
    return {"min": gia[0], "max": gia[-1],
            **{f"p{int(q * 100)}": _phan_vi_gia_tri(gia, q) for q in (0.10, 0.25, 0.50, 0.75, 0.90)}}


def _vi_tri(gia: List[int], gia_toi: Optional[float]):
    """Phân vị và dải của giá mình trong phân bố. Không có giá mình thì trả (None, None)."""
    if gia_toi is None:
        return None, None
    pv = round(sum(1 for g in gia if g <= gia_toi) / len(gia) * 100)
    return pv, next(ten for nguong, ten in DAI if pv < nguong)


def _khoang_de_xuat(pb: Dict[str, int], co_so: str) -> Dict[str, Any]:
    return {
        "low": pb["p25"], "high": pb["p75"],
        "basis": f"khoảng giá liên phân vị của {co_so}",
        "caveat": "tương quan — giá nằm trong khoảng này không đảm bảo bán được",
    }


# ---------------------------------------------------------------------------
# ĐƯỜNG SHOP THẬT
# ---------------------------------------------------------------------------

def _pricing_live(shop_id: str, productType: Optional[str],
                  price: Optional[float], productId: Optional[str]):
    sp = san_pham_live(shop_id)
    if not sp:
        return insufficient(
            "Shop bạn chưa có sản phẩm nào trên sàn, nên chưa có giá để so. "
            "Đăng sản phẩm đầu tiên rồi quay lại trang này.",
            build_meta(model_version="live-pricing-1.0", scope="shop", scope_id=shop_id,
                       database="vietcraft", collection="products", mode="derived",
                       attributed_to_live_shop=True, sample_size=0),
        )

    # Danh sách sản phẩm để FE dựng bộ chọn. Đây là sản phẩm THẬT của người bán.
    cua_toi = [{
        "product_id": p["product_id"],
        "title": p["title"],
        "price_vnd": p["price_vnd"],
        "product_type_id": p["product_type_id"],
        "type_source": p["type_source"],
        "handmade_hint": p["handmade_hint"],
    } for p in sp]

    chon = next((p for p in sp if p["product_id"] == productId), None) if productId else None
    if productId and chon is None:
        invalid_param("productId", "mã một sản phẩm của shop bạn")

    # Loại phôi: người bán chọn thì tin người bán, không thì lấy của sản phẩm đang xem,
    # không nữa thì lấy loại phổ biến nhất trong shop.
    if productType:
        pt, nguon_loai = productType, "seller"
    elif chon:
        pt, nguon_loai = chon["product_type_id"], chon["type_source"]
    else:
        dem: Dict[str, int] = {}
        for p in sp:
            if p["product_type_id"]:
                dem[p["product_type_id"]] = dem.get(p["product_type_id"], 0) + 1
        pt = max(dem, key=lambda k: dem[k]) if dem else None
        nguon_loai = next((p["type_source"] for p in sp if p["product_type_id"] == pt), "unknown")

    # Giá của mình: tham số price thắng, rồi tới giá sản phẩm đang xem.
    #
    # CHƯA CHỌN SẢN PHẨM THÌ KHÔNG PHÁN XÉT. Bản đầu lấy trung vị giá các sản phẩm cùng
    # loại phôi của shop rồi chấm "cao hơn hầu hết" — nhưng trung vị của một bộ ấm chén
    # gốm và một cái cốc in là con số không đại diện cho sản phẩm nào cả, và người bán sẽ
    # nhận một kết luận về thứ họ chưa hỏi. Để trống, và mời họ chọn một sản phẩm.
    if price is not None:
        gia_toi: Optional[float] = price
    elif chon:
        gia_toi = chon["price_vnd"]
    else:
        gia_toi = None

    loai_cua_toi = sorted({p["product_type_id"] for p in sp if p["product_type_id"]})

    # ---- Mặt bằng 1: catalog tham chiếu POD, cùng loại phôi -----------------
    if pt:
        coll = db()[MART]
        if coll.estimated_document_count() == 0:
            mart_not_ready(MART)
        rows = list(coll.find({"product_type_id": pt},
                              {"_id": 0, "price_vnd": 1, "est_sales_90d": 1,
                               "computed_at": 1, "model_version": 1}))
        ban_chay = sorted(rows, key=lambda r: -r["est_sales_90d"])[:TOP_BAN_CHAY]
        gia = sorted(r["price_vnd"] for r in ban_chay if r["price_vnd"] > 0)

        if len(gia) >= TOI_THIEU:
            pb = _phan_bo(gia)
            pv, dai = _vi_tri(gia, gia_toi)
            meta = meta_from_record(
                rows[0], scope="product_type", scope_id=pt, collection=MART,
                mode="derived", attributed_to_live_shop=True, sample_size=len(rows),
            )
            return ok({
                "product_type_id": pt,
                "type_source": nguon_loai,
                "type_source_note": NGUON_LOAI.get(nguon_loai, nguon_loai),
                "available_product_types": loai_cua_toi,
                "my_products": cua_toi,
                "selected_product_id": chon["product_id"] if chon else None,
                "basis_kind": "reference_catalog",
                "n_listings": len(gia),
                "basis": f"top {len(gia)} sản phẩm bán chạy nhất cùng loại phôi trong catalog tham chiếu (BR-198)",
                "distribution": pb,
                "my_price": tien(gia_toi) if gia_toi is not None else None,
                "percentile": pv,
                "band": dai,
                "suggested_range": _khoang_de_xuat(pb, "nhóm bán chạy nhất trong catalog tham chiếu"),
                "handmade_hint": bool(chon and chon["handmade_hint"]),
                "needs_product_pick": gia_toi is None,
                "limitation": (
                    ("GIÁ CỦA BẠN là giá thật trên sàn. " if gia_toi is not None else
                     "Chọn một sản phẩm ở danh sách bên trên để xem giá của bạn đứng đâu. ")
                    + "MẶT BẰNG SO SÁNH lấy từ catalog tham chiếu của ngành in theo yêu cầu, "
                    "không phải giá thật của shop khác trên VietCraft, vì sàn chưa đủ sản phẩm "
                    "cùng loại để dựng phân bố. "
                    f"Mã loại phôi ({pt}) do {NGUON_LOAI.get(nguon_loai, nguon_loai)}; "
                    "chọn lại ở ô bên trên nếu chưa đúng."
                    + (" ⚠ Sản phẩm bạn chọn có dấu hiệu là HÀNG THỦ CÔNG. Giá hàng thủ công "
                       "phụ thuộc công làm và chất liệu, không so được với phôi in công nghiệp; "
                       "hãy đọc khoảng giá dưới đây như một mốc tham khảo xa, đừng coi là kết luận."
                       if chon and chon["handmade_hint"] else "")
                ),
            }, meta)

    # ---- Mặt bằng 2: giá THẬT của shop khác trên sàn, cùng danh mục ---------
    danh_muc = sorted({c for p in sp for c in p["categories"]}) if not chon else sorted(chon["categories"])
    gia_that = gia_cung_danh_muc_live(danh_muc, tru_shop=shop_id)
    meta_live = build_meta(model_version="live-pricing-1.0", scope="shop", scope_id=shop_id,
                          database="vietcraft", collection="product_variants",
                          mode="live", attributed_to_live_shop=True,
                          sample_size=len(gia_that))

    if len(gia_that) >= TOI_THIEU:
        pb = _phan_bo(gia_that)
        pv, dai = _vi_tri(gia_that, gia_toi)
        return ok({
            "product_type_id": pt,
            "type_source": nguon_loai,
            "type_source_note": NGUON_LOAI.get(nguon_loai, nguon_loai),
            "available_product_types": loai_cua_toi,
            "my_products": cua_toi,
            "selected_product_id": chon["product_id"] if chon else None,
            "basis_kind": "live_category",
            "n_listings": len(gia_that),
            "basis": f"giá thật của {len(gia_that)} biến thể sản phẩm thuộc {', '.join(danh_muc) or 'cùng danh mục'} trên sàn",
            "distribution": pb,
            "my_price": tien(gia_toi) if gia_toi is not None else None,
            "percentile": pv,
            "band": dai,
            "suggested_range": _khoang_de_xuat(pb, "các sản phẩm cùng danh mục trên sàn"),
            "limitation": (
                "Sản phẩm này không ánh xạ được sang loại phôi in theo yêu cầu nào, nên mặt "
                "bằng lấy theo DANH MỤC trên sàn. Cùng danh mục không có nghĩa là cùng loại "
                "hàng, nên hãy đọc đây là khoảng giá của ngành, không phải của đúng sản phẩm "
                "như bạn."
            ),
        }, meta_live)

    # ---- Không đủ cả hai ---------------------------------------------------
    return insufficient(
        (f"Chưa dựng được mặt bằng giá cho sản phẩm này. Tên sản phẩm "
         f"{'không ánh xạ được sang loại phôi nào' if not pt else f'ánh xạ sang loại phôi {pt} nhưng catalog chưa đủ sản phẩm cùng loại'}"
         f", và trên sàn chỉ có {len(gia_that)} mức giá cùng danh mục, cần tối thiểu {TOI_THIEU}. "
         f"Chọn tay một loại phôi ở ô bên trên để so với catalog tham chiếu."),
        meta_live,
    )


# ---------------------------------------------------------------------------
# ĐƯỜNG SHOP DỮ LIỆU MỒI
# ---------------------------------------------------------------------------

def _pricing_seed(shop_id: str, productType: Optional[str], price: Optional[float]):
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

    pb = _phan_bo(gia)

    gia_toi = price
    if gia_toi is None:
        cua_minh = [r["price_vnd"] for r in rows if r["shop_id"] == shop_id and r["price_vnd"] > 0]
        gia_toi = sum(cua_minh) / len(cua_minh) if cua_minh else None
    pv, dai = _vi_tri(gia, gia_toi)

    return ok({
        "product_type_id": pt,
        "type_source": "seed",
        "available_product_types": cua_toi,
        "basis_kind": "seed_market",
        "n_listings": len(gia),
        "basis": f"top {len(gia)} listing bán chạy nhất trong {len(rows)} listing cùng loại (BR-198)",
        "distribution": pb,
        "my_price": tien(gia_toi) if gia_toi is not None else None,
        "percentile": pv,
        "band": dai,
        "suggested_range": _khoang_de_xuat(pb, "nhóm bán chạy nhất"),
    }, meta)


@router.get("/api/analytics/pricing", tags=["F35 · Nhi"])
def pricing(shop_id: str = CurrentShop,
            productType: Optional[str] = None,
            price: Optional[float] = None,
            productId: Optional[str] = None):
    if la_shop_live(shop_id):
        return _pricing_live(shop_id, productType, price, productId)
    return _pricing_seed(shop_id, productType, price)
