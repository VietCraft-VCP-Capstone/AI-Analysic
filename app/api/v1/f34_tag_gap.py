import sys
from collections import Counter
from pathlib import Path
from typing import Optional

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from fastapi import APIRouter

from app.api.v1._mart import db
from app.api.v1._template import CurrentShop, insufficient, invalid_param, mart_not_ready, meta_from_record, ok

router = APIRouter()

MART = "mart_competitor"
TOI_THIEU_DOI_THU = 10      # BR-194
SO_DAN_DAU = 20             # "nhóm dẫn đầu" = top 20 theo est_sales_90d
TOI_THIEU_DUNG = 2          # tag phải xuất hiện ít nhất 2 lần trong nhóm dẫn đầu
NGUONG_VUOT_TROI = 1.3      # nhóm dẫn đầu phải dùng tag này nhiều hơn mặt bằng >= 30%
NGUONG_DEM_TIN_CAY = 5      # dưới 5/20 lần thì không phân biệt được với may rủi


@router.get("/api/analytics/tag-gap", tags=["F34 · Đạt"])
def tag_gap(shop_id: str = CurrentShop, categoryId: Optional[str] = None):
    coll = db()[MART]
    if coll.estimated_document_count() == 0:
        mart_not_ready(MART)

    cua_toi = sorted(coll.distinct("category_id", {"shop_id": shop_id}))
    if not cua_toi:
        return insufficient("Shop chưa có listing nào nên chưa tìm được tag thiếu")

    cat = categoryId or cua_toi[0]
    if cat not in cua_toi:
        invalid_param("categoryId", " | ".join(cua_toi))

    chieu = {"_id": 0, "shop_id": 1, "tags": 1, "est_sales_90d": 1,
             "computed_at": 1, "model_version": 1}
    trong_cat = list(coll.find({"category_id": cat}, chieu))
    doi_thu = sorted((r for r in trong_cat if r["shop_id"] != shop_id),
                     key=lambda r: -r["est_sales_90d"])

    meta = meta_from_record(trong_cat[0], scope="category", scope_id=cat, collection=MART,
                            mode="seed_demo", sample_size=len(trong_cat))

    if len(doi_thu) < TOI_THIEU_DOI_THU:
        return insufficient(
            f"Danh mục `{cat}` chỉ có {len(doi_thu)} listing cạnh tranh, "
            f"cần tối thiểu {TOI_THIEU_DOI_THU} mới kết luận được (BR-194)", meta)

    dan_dau = doi_thu[:SO_DAN_DAU]
    tag_toi = {t for r in trong_cat if r["shop_id"] == shop_id for t in r.get("tags") or []}

    dem_dau = Counter(t for r in dan_dau for t in set(r.get("tags") or []))
    dem_ca = Counter(t for r in doi_thu for t in set(r.get("tags") or []))
    ten_tag = {c["category_id"]: c.get("name_vi") for c in
               db()["categories"].find({}, {"category_id": 1, "name_vi": 1})}

    thieu = []
    for tag, n in dem_dau.items():
        if tag in tag_toi or n < TOI_THIEU_DUNG:
            continue
        share_dau = n / len(dan_dau)
        share_ca = dem_ca[tag] / len(doi_thu) if dem_ca[tag] else 0
        # ĐỘ VƯỢT TRỘI, không phải tỉ lệ tuyệt đối. Câu hỏi đúng không phải "bao
        # nhiêu đối thủ dùng tag này" mà "nhóm BÁN CHẠY có dùng nó nhiều hơn mặt
        # bằng chung không". Tỉ lệ tuyệt đối cao vẫn vô nghĩa nếu ai cũng dùng.
        vuot = round(share_dau / share_ca, 2) if share_ca else None
        if vuot is None or vuot < NGUONG_VUOT_TROI:
            continue
        thap = max(3, round((vuot - 1) * 20))
        thieu.append({
            "tag_id": tag,
            "name": ten_tag.get(tag, tag),
            "used_by_competitors": n,
            "competitor_share_pct": round(share_dau * 100),
            "category_share_pct": round(share_ca * 100),
            "lift": vuot,
            "estimated_traffic_gain": {
                "low_pct": thap, "high_pct": min(25, thap * 2),
                "basis": "correlational",
            },
        })

    thieu.sort(key=lambda x: -x["lift"])   # BR-197

    so_tag_thu = len(dem_dau)
    ky_vong_gia = sum(1 for t in thieu if t["used_by_competitors"] < NGUONG_DEM_TIN_CAY)
    manh = [t for t in thieu if t["used_by_competitors"] >= NGUONG_DEM_TIN_CAY and t["lift"] >= 2.0]
    vuot_max = max((t["lift"] for t in thieu), default=0)
    co_tin_hieu = bool(manh)

    return ok({
        "category_id": cat,
        "available_categories": cua_toi,
        "competitors_scanned": len(dan_dau),
        "my_tags": sorted(tag_toi),
        "missing_tags": thieu,
        "signal": {
            "has_signal": co_tin_hieu,
            "max_lift": vuot_max,
            "tags_tested": so_tag_thu,
            "strong_count": len(manh),
            "weak_count": ky_vong_gia,
            "note": (f"{len(manh)} tag vượt trội đủ mạnh để không giải thích bằng ngẫu nhiên."
                     if co_tin_hieu else
                     f"KHÔNG có tín hiệu đủ mạnh. Đã thử {so_tag_thu} tag trên "
                     f"{len(dan_dau)} đối thủ; mọi tag tìm được đều xuất hiện dưới "
                     f"{NGUONG_DEM_TIN_CAY} lần, tức nằm trong mức dao động ngẫu nhiên. "
                     f"Tag trong dữ liệu mồi được gán ngẫu nhiên nên điều này là DỰ KIẾN — "
                     f"đừng dùng danh sách dưới đây để ra quyết định. Endpoint chỉ có ý "
                     f"nghĩa trên dữ liệu sàn thật."),
        },
        "note": ("Ước lượng là TƯƠNG QUAN, không phải nhân quả. Thêm tag không đảm bảo "
                 "tăng truy cập — con số chỉ nói nhóm bán chạy dùng tag này vượt mặt bằng bao nhiêu."),
    }, meta)
