"""
F39 · GET /api/analytics/forecast/niches?categoryId= — ngách nhiều cầu ít cung.

Đọc mart `niche_score` (do app/core/build_marts.py ghi từ Google Trends THẬT).

  BR-210  tính lại mỗi 24h lúc nửa đêm GMT+7
  BR-211  BẮT BUỘC lọc bỏ ngách chứa từ khoá cấm (bản quyền / NSFW),
          đọc collection `banned_keywords` trên sàn live
"""

import sys
from pathlib import Path
from typing import Optional

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from fastapi import APIRouter
from pymongo import MongoClient

from app.api.v1._mart import db
from app.api.v1._template import CurrentShop, mart_not_ready, meta_from_record, ok
from app.config import settings

router = APIRouter()

MART = "niche_score"
TOP_N = 20


_client_live = None


def _tu_khoa_cam() -> set:
    """BR-211. Bảng đang rỗng trên sàn -> không lọc gì, nhưng vẫn phải ĐỌC:
    ngày nào có người đổ vào là lọc có hiệu lực ngay, không phải sửa code.

    Giữ lại MongoClient: mở mới mỗi request là mỗi lần bắt tay TLS với Atlas,
    đo được 1.3 giây trên tổng 1.7 giây của endpoint này.
    """
    global _client_live
    try:
        if _client_live is None:
            _client_live = MongoClient(settings.MONGO_URI, serverSelectionTimeoutMS=5000,
                                       maxPoolSize=5)
        return {str(x.get("keyword", "")).lower().strip()
                for x in _client_live[settings.MONGO_DB_LIVE]["banned_keywords"]
                .find({}, {"keyword": 1})}
    except Exception:
        # Không đọc được danh sách cấm thì KHÔNG im lặng bỏ lọc.
        # BR-211 là ràng buộc pháp lý (bản quyền/NSFW), không phải tuỳ chọn.
        raise


@router.get("/api/analytics/forecast/niches", tags=["F39 · Hưng"])
def niches(shop_id: str = CurrentShop, categoryId: Optional[str] = None):
    rows = list(db()[MART].find({}, {"_id": 0}).sort("gap_score", -1))
    if not rows:
        mart_not_ready(MART)

    cam = _tu_khoa_cam()
    sach = [r for r in rows if r["keyword"].lower().strip() not in cam]
    da_loc = len(rows) - len(sach)

    if categoryId:
        tag_cat = {t["tag_id"] for t in db()["tags"].find(
            {"category_id": {"$regex": f"^{categoryId}"}}, {"tag_id": 1})}
        if tag_cat:
            sach = [r for r in sach if set(r.get("tag_ids") or []) & tag_cat]

    meta = meta_from_record(rows[0], scope="platform", scope_id="all", collection=MART,
                            mode="derived",       # cầu từ Trends thật, cung từ listing mồi
                            sample_size=len(rows), confidence="medium")

    return ok({
        "niches": [{
            "rank": i,
            "keyword": r["keyword"],
            "tag_id": r.get("tag_id"),
            "demand_pct": r["demand_pct"],
            "supply_pct": r["supply_pct"],
            "gap_score": r["gap_score"],
            "n_listings": r["n_listings"],
            "demand_index": r["demand_index"],
            "trend": r["trend"],
            "growth_pct": r.get("growth_pct"),
            "quadrant": r.get("quadrant"),
            "sparkline_7d": r.get("sparkline_7d"),
        } for i, r in enumerate(sach[:TOP_N], 1)],
        "total_niches": len(sach),
        "banned_filtered": da_loc,
        "banned_list_size": len(cam),
        "limitation": ("Cầu lấy từ Google Trends Việt Nam THẬT. Cung đếm trên listing của "
                       "dữ liệu mồi, nên gap_score phản ánh mức cạnh tranh của dữ liệu mồi, "
                       "chưa phải của sàn thật."),
    }, meta)
