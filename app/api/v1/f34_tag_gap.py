import sys
from collections import Counter
from pathlib import Path
from typing import Optional

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from fastapi import APIRouter

from app.api.v1._competitor_live import danh_muc_cua_toi, meta_doi_thu, nguon_doi_thu, ten_tag_live
from app.api.v1._mart import db
from app.api.v1._template import CurrentShop, insufficient, invalid_param, ok

router = APIRouter()

TOI_THIEU_DOI_THU = 10      # BR-194
SO_DAN_DAU = 20             # "nhóm dẫn đầu" = top 20 theo est_sales_90d
TOI_THIEU_DUNG = 2          # tag phải xuất hiện ít nhất 2 lần trong nhóm dẫn đầu
NGUONG_VUOT_TROI = 1.3      # nhóm dẫn đầu phải dùng tag này nhiều hơn mặt bằng >= 30%
TRAN_UOC_LUONG = 25         # trần % traffic dám ước lượng — trên mức này là hứa hão
NGUONG_DEM_TIN_CAY = 5      # dưới 5/20 lần thì không phân biệt được với may rủi


@router.get("/api/analytics/tag-gap", tags=["F34 · Đạt"])
def tag_gap(shop_id: str = CurrentShop, categoryId: Optional[str] = None):
    ng = nguon_doi_thu(shop_id)
    coll = ng["bang"]

    cua_toi, chinh, ten_dm = danh_muc_cua_toi(coll, shop_id)
    if not cua_toi:
        return insufficient("Shop chưa có sản phẩm nào nên chưa tìm được từ khoá thiếu")

    cat = categoryId or chinh
    if cat not in cua_toi:
        invalid_param("categoryId", " | ".join(cua_toi))

    chieu = {"_id": 0, "shop_id": 1, "tags": 1, "est_sales_90d": 1,
             "computed_at": 1, "model_version": 1}
    trong_cat = list(coll.find({"category_id": cat}, chieu))
    doi_thu = sorted((r for r in trong_cat if r["shop_id"] != shop_id),
                     key=lambda r: -r["est_sales_90d"])

    meta = meta_doi_thu(ng, trong_cat[0], scope="category", scope_id=cat, sample_size=len(trong_cat))

    if len(doi_thu) < TOI_THIEU_DOI_THU:
        meta["unlock"] = {"requirement": "sản phẩm đối thủ cùng danh mục", "unit": "sản phẩm",
                          "current": len(doi_thu), "target": TOI_THIEU_DOI_THU}
        return insufficient(
            f"Danh mục {ten_dm.get(cat) or cat} chỉ có {len(doi_thu)} sản phẩm của shop khác, "
            f"cần tối thiểu {TOI_THIEU_DOI_THU} mới kết luận được", meta)

    dan_dau = doi_thu[:SO_DAN_DAU]
    tag_toi = {t for r in trong_cat if r["shop_id"] == shop_id for t in r.get("tags") or []}

    dem_dau = Counter(t for r in dan_dau for t in set(r.get("tags") or []))
    dem_ca = Counter(t for r in doi_thu for t in set(r.get("tags") or []))
    if ng["live"]:
        ten_tag = ten_tag_live(set(dem_dau) | tag_toi)
    else:
        ten_tag = {c["category_id"]: c.get("name_vi") for c in
                   db()["categories"].find({}, {"category_id": 1, "name_vi": 1})}

    thieu = []
    for tag, n in dem_dau.items():
        if tag in tag_toi or n < TOI_THIEU_DUNG:
            continue
        share_dau = n / len(dan_dau)
        share_ca = dem_ca[tag] / len(doi_thu) if dem_ca[tag] else 0
        vuot = round(share_dau / share_ca, 2) if share_ca else None
        if vuot is None or vuot < NGUONG_VUOT_TROI:
            continue
        cao = min(TRAN_UOC_LUONG, max(6, round((vuot - 1) * 20) * 2))
        thap = max(3, cao // 2)
        thieu.append({
            "tag_id": tag,
            "name": ten_tag.get(tag, tag),
            "used_by_competitors": n,
            "competitor_share_pct": round(share_dau * 100),
            "category_share_pct": round(share_ca * 100),
            "lift": vuot,
            "estimated_traffic_gain": {
                "low_pct": thap, "high_pct": cao,
                "basis": "correlational",
            },
        })

    thieu.sort(key=lambda x: -x["lift"])

    so_tag_thu = len(dem_dau)
    ky_vong_gia = sum(1 for t in thieu if t["used_by_competitors"] < NGUONG_DEM_TIN_CAY)
    manh = [t for t in thieu if t["used_by_competitors"] >= NGUONG_DEM_TIN_CAY and t["lift"] >= 2.0]
    vuot_max = max((t["lift"] for t in thieu), default=0)
    co_tin_hieu = bool(manh)

    if co_tin_hieu:
        ghi_chu = f"{len(manh)} tag vượt trội đủ mạnh để không giải thích bằng ngẫu nhiên."
    elif ng["live"]:
        ghi_chu = (f"KHÔNG có tín hiệu đủ mạnh. Đã thử {so_tag_thu} tag trên {len(dan_dau)} đối thủ dẫn đầu; "
                   f"chưa tag nào vừa xuất hiện từ {NGUONG_DEM_TIN_CAY} lần trở lên vừa vượt mặt bằng "
                   f"từ 2 lần trở lên, nên chưa phân biệt được với may rủi."
                   # Danh mục <= 20 sản phẩm đối thủ thì nhóm dẫn đầu là cả danh mục, lift tối đa = 1.
                   + (f" Danh mục mới có {len(doi_thu)} sản phẩm của shop khác: khi chưa quá {SO_DAN_DAU} thì nhóm "
                      f"dẫn đầu chính là cả danh mục, nên không tag nào vượt trội được."
                      if len(doi_thu) <= SO_DAN_DAU else "")
                   + " Đừng dùng danh sách dưới đây để ra quyết định.")
    else:
        ghi_chu = (f"KHÔNG có tín hiệu đủ mạnh. Đã thử {so_tag_thu} tag trên "
                   f"{len(dan_dau)} đối thủ; mọi tag tìm được đều xuất hiện dưới "
                   f"{NGUONG_DEM_TIN_CAY} lần, tức nằm trong mức dao động ngẫu nhiên. "
                   f"Tag trong dữ liệu mồi được gán ngẫu nhiên nên điều này là DỰ KIẾN — "
                   f"đừng dùng danh sách dưới đây để ra quyết định. Endpoint chỉ có ý "
                   f"nghĩa trên dữ liệu sàn thật.")

    return ok({
        "category_id": cat,
        "available_categories": cua_toi,
        **({"category_names": ten_dm} if ng["live"] else {}),
        "competitors_scanned": len(dan_dau),
        "my_tags": sorted(tag_toi),
        "tag_names": {t: ten_tag.get(t) or t for t in set(dem_dau) | tag_toi},
        # Tag nhóm dẫn đầu hay dùng, kể cả tag mình đã có: FE hiện "đã có / chưa có" cho người mới.
        "leader_tags": [{"tag_id": t, "used_by": n, "mine": t in tag_toi}
                        for t, n in sorted(dem_dau.items(), key=lambda x: (-x[1], x[0]))[:12]],
        "missing_tags": thieu,
        "signal": {
            "has_signal": co_tin_hieu,
            "max_lift": vuot_max,
            "tags_tested": so_tag_thu,
            "strong_count": len(manh),
            "weak_count": ky_vong_gia,
            "note": ghi_chu,
        },
        "note": ("Ước lượng là TƯƠNG QUAN, không phải nhân quả. Thêm tag không đảm bảo "
                 "tăng truy cập — con số chỉ nói nhóm bán chạy dùng tag này vượt mặt bằng bao nhiêu."),
    }, meta)
