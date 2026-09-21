"""
F40 · GET /api/analytics/forecast/radar — 10 tag nóng lên nhanh nhất tuần này.

  BR-212  radar chỉ vẽ danh mục lớn; tag chi tiết nằm ở danh sách bên dưới
  BR-213  Momentum cần >= 100 lượt tìm/tuần — CHƯA ÁP DỤNG ĐƯỢC, xem `limitation`
"""

import sys
from collections import defaultdict
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from fastapi import APIRouter

from app.api.v1._mart import db
from app.api.v1._template import CurrentShop, mart_not_ready, meta_from_record, ok

router = APIRouter()

MART = "mart_demand"
TOP_N = 10
TOI_THIEU_TAG_MOI_TRUC = 3


@router.get("/api/analytics/forecast/radar", tags=["F40 · Hưng"])
def radar(shop_id: str = CurrentShop):
    rows = list(db()[MART].find({}, {"_id": 0}).sort("growth_pct", -1))
    if not rows:
        mart_not_ready(MART)

    tag_cat = {t["tag_id"]: t.get("category_id") for t in
               db()["tags"].find({}, {"tag_id": 1, "category_id": 1})}

    # BR-212: gom về danh mục cấp 1 ("apparel.tet" -> "apparel") cho radar đỡ rối.
    theo_truc = defaultdict(list)
    for r in rows:
        cat = (tag_cat.get(r["tag_id"]) or "khac").split(".")[0]
        theo_truc[cat].append(r["demand_index"])

    truc = sorted((c for c, v in theo_truc.items() if len(v) >= TOI_THIEU_TAG_MOI_TRUC),
                  key=lambda c: -sum(theo_truc[c]) / len(theo_truc[c]))
    gia_tri = [round(sum(theo_truc[c]) / len(theo_truc[c]), 1) for c in truc]
    cao = max(gia_tri) if gia_tri else 0
    # Chuẩn hoá về 0–100 theo trục cao nhất, để radar đọc được; giữ cả số thô.
    gia_tri_chuan = [round(v / cao * 100, 1) if cao else 0.0 for v in gia_tri]

    meta = meta_from_record(rows[0], scope="platform", scope_id="all", collection=MART,
                            mode="live",          # Google Trends Việt Nam thật
                            sample_size=len(rows), confidence="medium")

    return ok({
        "week": rows[0].get("week"),
        "top_tags": [{
            "rank": i,
            "tag_id": r["tag_id"],
            "name_vi": r.get("name_vi"),
            "growth_pct": r["growth_pct"],
            "momentum": r["momentum"],
            "demand_index": r["demand_index"],
            "supply_n_listings": r.get("supply_n_listings"),
            "trend": r["trend"],
            "searches_per_week": r.get("searches_per_week"),
        } for i, r in enumerate(rows[:TOP_N], 1)],
        "radar": {"axes": truc, "values": gia_tri_chuan, "values_raw": gia_tri,
                  "scale": "0-100, chuẩn hoá theo trục cao nhất"},
        "limitation": ("BR-213 đòi ngưỡng >= 100 lượt tìm/tuần, nhưng Google Trends trả "
                       "CHỈ SỐ 0-100 chứ không phải số lượt tìm tuyệt đối — quy đổi ra "
                       "lượt/tuần là bịa số. Ngưỡng này CHƯA áp dụng được; "
                       "`searches_per_week` để null thay vì điền số giả."),
    }, meta)
