import sys
from pathlib import Path
from typing import Optional

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from fastapi import APIRouter
from pymongo import MongoClient

from app.api.v1._live import LOC_SP_THAT, db_live, la_shop_live
from app.api.v1._mart import db
from app.api.v1._template import CurrentShop, build_meta, mart_not_ready, meta_from_record, ok, partial
from app.config import settings

router = APIRouter()

MART = "niche_score"
TOP_N = 20
NGUONG_CUNG_LIVE = 20    # §9.2: ≥20 listing live cùng tag mới tin được phần CUNG


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

    niches_out = [{
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
    } for i, r in enumerate(sach[:TOP_N], 1)]

    # Shop THẬT: cầu (Google Trends) vẫn là số thật, giữ nguyên. Cung so với CATALOG
    # SEED thì không có nghĩa với sàn thật — che phần cung, không bịa số, và nói rõ
    # cần bao nhiêu listing thật cùng tag thì mới tính lại được (§9.2).
    if la_shop_live(shop_id):
        so_sp_that = db_live()["products"].count_documents(
            {**LOC_SP_THAT, "tags": {"$exists": True, "$ne": []}})
        for n in niches_out:
            n["supply_pct"] = None
            n["gap_score"] = None
            n["n_listings"] = None
            n["supply_insufficient"] = True

        meta = build_meta(model_version="live-read-1.0", scope="platform", scope_id="all",
                          database=settings.MONGO_DB_LIVE, collection="products",
                          mode="live", attributed_to_live_shop=True,
                          sample_size=len(niches_out), confidence="medium",
                          unlock={"requirement": "listing thật có tag", "unit": "listing",
                                  "current": so_sp_that, "target": NGUONG_CUNG_LIVE})
        return partial({
            "niches": niches_out,
            "total_niches": len(sach),
            "banned_filtered": da_loc,
            "banned_list_size": len(cam),
            "limitation": ("Cầu lấy từ Google Trends Việt Nam THẬT. Phần CUNG tạm ẩn vì sàn "
                           "thật chưa có đủ listing gắn tag để so — supply_pct/gap_score/"
                           "n_listings sẽ tự hiện khi đủ dữ liệu."),
        }, "Chưa đủ listing thật gắn tag để tính phần CUNG của ngách — chỉ hiện phần CẦU.", meta)

    meta = meta_from_record(rows[0], scope="platform", scope_id="all", collection=MART,
                            mode="derived",       # cầu từ Trends thật, cung từ listing mồi
                            sample_size=len(rows), confidence="medium")

    return ok({
        "niches": niches_out,
        "total_niches": len(sach),
        "banned_filtered": da_loc,
        "banned_list_size": len(cam),
        "limitation": ("Cầu lấy từ Google Trends Việt Nam THẬT. Cung đếm trên listing của "
                       "dữ liệu mồi, nên gap_score phản ánh mức cạnh tranh của dữ liệu mồi, "
                       "chưa phải của sàn thật."),
    }, meta)
