import sys
from datetime import date
from pathlib import Path
from typing import Any, Dict, List

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.api.v1._live import db_live, san_pham_live
from app.api.v1._mart import db
from app.api.v1._template import build_meta, insufficient, ok
from app.config import settings
from app.api.v1.f38_seasonal import _cua_so_ra_hang  # noqa: PLC0415

TOI_DA = 5
TOI_DA_YEU = 3
DIEM_YEU = 50


def _f29_thap(shop_id: str, gioi_han: int = 50) -> List[Dict[str, Any]]:
    """Sản phẩm điểm F29 thấp (< DIEM_YEU) của CHÍNH shop, bản ghi mới nhất mỗi sản phẩm."""
    from bson import ObjectId  # noqa: PLC0415

    sp = san_pham_live(shop_id, gioi_han=gioi_han)
    if not sp:
        return []
    ten = {s["product_id"]: s["title"] for s in sp}
    try:
        ids = [ObjectId(s["product_id"]) for s in sp]
    except Exception:
        return []

    rows = list(db_live()["listing_health_scores"].aggregate([
        {"$match": {"product_id": {"$in": ids}}},
        {"$sort": {"date": -1}},
        {"$group": {"_id": "$product_id", "score": {"$first": "$score"},
                    "status": {"$first": "$status"}, "todos": {"$first": "$todos"}}},
    ]))
    thap = [r for r in rows if r.get("score") is not None and r["score"] < DIEM_YEU]
    thap.sort(key=lambda r: r["score"])
    return [{
        "product_id": str(r["_id"]), "title": ten.get(str(r["_id"]), ""),
        "score": r["score"], "status": r.get("status"), "todos": r.get("todos") or [],
    } for r in thap]


def _mua_vu_sap_toi(gioi_han: int = 3) -> List[Dict[str, Any]]:
    """Đỉnh mùa vụ sắp tới, đọc mart `seasonal_profile` (F38) — Google Trends thật."""
    rows = list(db()["seasonal_profile"].find({"has_seasonality": True}, {"_id": 0})
               .sort("amplitude", -1).limit(20))
    if not rows:
        return []
    hom_nay = date.today()
    ra = []
    for r in rows:
        try:
            cua = _cua_so_ra_hang(int(r["period_value"]), hom_nay)
        except Exception:
            cua = None
        if cua is None:
            continue
        ra.append({"keyword": r["entity_id"], "tag_ids": r.get("tag_ids"),
                   "peak_week_of_year": int(r["period_value"]), "amplitude": r["amplitude"],
                   "launch_window": cua})
    ra.sort(key=lambda x: x["launch_window"]["start"])
    return ra[:gioi_han]


def _tag_nong(gioi_han: int = 5) -> List[Dict[str, Any]]:
    """Tag đang tăng trưởng nhanh nhất, đọc mart `mart_demand` (F40) — Google Trends thật."""
    rows = list(db()["mart_demand"].find({}, {"_id": 0}).sort("growth_pct", -1).limit(gioi_han))
    return [{"tag_id": r["tag_id"], "name_vi": r.get("name_vi"), "growth_pct": r["growth_pct"],
             "demand_index": r.get("demand_index")} for r in rows]


def recommendations_live(shop_id: str):
    yeu = _f29_thap(shop_id) if db_live()["listing_health_scores"].estimated_document_count() > 0 else []
    mua_vu = _mua_vu_sap_toi()
    nong = _tag_nong()

    meta = build_meta(model_version="live-reco-1.0", scope="shop", scope_id=shop_id,
                      database=settings.MONGO_DB_LIVE, collection="listing_health_scores",
                      mode="live", attributed_to_live_shop=True,
                      sample_size=len(yeu), confidence="low")

    khuyen: List[Dict[str, Any]] = []

    for p in yeu[:TOI_DA_YEU]:
        if len(khuyen) >= TOI_DA:
            break
        why = [f"điểm sức khoẻ listing hiện {p['score']}/100 ({p.get('status')})"]
        if p.get("todos"):
            viec = p["todos"][0]
            why.append(f"việc cần làm: {viec.get('message') if isinstance(viec, dict) else viec}")
        khuyen.append({
            "priority": len(khuyen) + 1, "action": "fix",
            "target": {"type": "listing", "id": p["product_id"], "name_vi": p["title"]},
            "why": why,
            "expected": "chưa đo được — cần backtest",
            "confidence": "low",
        })

    for s in mua_vu:
        if len(khuyen) >= TOI_DA:
            break
        khuyen.append({
            "priority": len(khuyen) + 1, "action": "prepare_season",
            "target": {"type": "keyword", "id": s["keyword"], "keyword": s["keyword"]},
            "why": [f"đỉnh mùa vụ tuần {s['peak_week_of_year']}, biên độ {s['amplitude']}",
                    f"nên ra hàng {s['launch_window']['start']} .. {s['launch_window']['end']}"],
            "expected": "chưa đo được — cần backtest",
            "confidence": "low",
        })

    for t in nong:
        if len(khuyen) >= TOI_DA:
            break
        khuyen.append({
            "priority": len(khuyen) + 1, "action": "explore",
            "target": {"type": "tag", "id": t["tag_id"], "name_vi": t.get("name_vi")},
            "why": [f"tag đang tăng trưởng {t['growth_pct']}% tuần này",
                    f"chỉ số nhu cầu {t.get('demand_index')}"],
            "expected": "chưa đo được — cần backtest",
            "confidence": "low",
        })

    return ok({
        "shop_id": shop_id,
        "scope": "shop",
        "personalised": True,
        "recommendations": khuyen[:TOI_DA],
        "my_listings_analysed": len(yeu),
        "validated": False,
        "validation_note": ("Chưa chạy backtest khuyến nghị. Gộp từ 3 tín hiệu THẬT: điểm "
                            "sức khoẻ listing (F29), mùa vụ Google Trends (F38), tag đang "
                            "nóng (F40) — KHÔNG dùng mart dữ liệu mồi. Mốc so sánh bắt buộc "
                            "vẫn là 'cứ làm tiếp thứ đang bán chạy nhất'."),
    }, meta)
