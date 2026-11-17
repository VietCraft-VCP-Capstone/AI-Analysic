import sys
from datetime import date
from pathlib import Path
from typing import Any, Dict, List

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.api.v1._live import db_live, san_pham_live
from app.api.v1._mart import db
from app.api.v1._template import build_meta, ok
from app.config import settings
from app.core import calendar_vn
from app.core.f29.constants import MODEL_VERSION

TOI_DA = 5
TOI_DA_YEU = 2
DIEM_YEU = 50


def _f29_thap(shop_id: str, gioi_han: int = 50) -> List[Dict[str, Any]]:
    """Sản phẩm điểm F29 thấp (< DIEM_YEU) của CHÍNH shop, bản ghi mới nhất mỗi sản phẩm."""
    from bson import ObjectId

    sp = san_pham_live(shop_id, gioi_han=gioi_han)
    if not sp:
        return []
    ten = {s["product_id"]: s["title"] for s in sp}
    try:
        ids = [ObjectId(s["product_id"]) for s in sp]
    except Exception:
        return []

    rows = list(db_live()["listing_health_scores"].aggregate([
        {"$match": {"product_id": {"$in": ids}, "model_version": MODEL_VERSION}},
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


def _mua_vu_sap_toi(gioi_han: int = 2) -> List[Dict[str, Any]]:
    """Lấy các dịp mua sắm cao điểm sắp tới từ calendar_vn chuẩn xác."""
    events = calendar_vn.upcoming_events(date.today(), weeks=16)
    ra = []
    for ev in events[:gioi_han]:
        win = ev["window"]
        ra.append({
            "key": ev["key"],
            "name": ev["name"],
            "date": win["event_date"],
            "cut_off_date": win["cut_off_date"],
            "days_to_cut_off": win["days_to_cut_off"],
            "phase_label": win["phase_label"],
            "category_focus": ev.get("category_focus", ""),
            "primary_keyword": ev.get("default_search_keywords", ["quà tặng"])[0]
        })
    return ra


def _tag_nong(gioi_han: int = 3) -> List[Dict[str, Any]]:
    """Tag đang tăng trưởng nhanh nhất, đọc mart `mart_demand` (F40) — Google Trends thật."""
    rows = list(db()["mart_demand"].find({}, {"_id": 0}).sort("growth_pct", -1).limit(gioi_han))
    return [{"tag_id": r["tag_id"], "name_vi": r.get("name_vi"), "growth_pct": r["growth_pct"],
             "demand_index": r.get("demand_index")} for r in rows]


def recommendations_live(shop_id: str):
    sp_all = san_pham_live(shop_id, gioi_han=100)
    has_scores = bool(db_live()["listing_health_scores"].find_one({"model_version": MODEL_VERSION}))
    yeu = _f29_thap(shop_id) if has_scores else []
    mua_vu = _mua_vu_sap_toi()
    nong = _tag_nong()

    khuyen: List[Dict[str, Any]] = []

    # 1. Hành động sửa chữa listing yếu (Cứu / thay thế sản phẩm cạn view/lỗi)
    for p in yeu[:TOI_DA_YEU]:
        if len(khuyen) >= TOI_DA:
            break
        why = [f"điểm sức khoẻ listing hiện {p['score']}/100 ({p.get('status')})"]
        if p.get("todos"):
            viec = p["todos"][0]
            why.append(f"việc cần làm: {viec.get('message') if isinstance(viec, dict) else viec}")
        khuyen.append({
            "priority": len(khuyen) + 1,
            "action": "fix",
            "target": {"type": "listing", "id": p["product_id"], "name_vi": p["title"]},
            "why": why,
            "expected": "Cải thiện chất lượng nội dung và ảnh bìa để tăng hiển thị tìm kiếm.",
            "confidence": "high",
        })

    # 2. Hành động đón đầu mùa vụ cao điểm (chuẩn bị mẫu mã & lịch ra hàng)
    for s in mua_vu:
        if len(khuyen) >= TOI_DA:
            break
        khuyen.append({
            "priority": len(khuyen) + 1,
            "action": "prepare_season",
            "target": {"type": "occasion", "id": s["key"], "name_vi": s["name"]},
            "why": [
                f"{s['name']}: {s['phase_label']}",
                f"Hạn chốt đơn an toàn: {s['cut_off_date']} (còn {s['days_to_cut_off']} ngày)",
                f"Gợi ý ngành hàng: {s['category_focus']}"
            ],
            "expected": "Hoàn tất đăng bán mẫu mới trước hạn chốt đơn để đón đợt cao điểm mua sắm.",
            "confidence": "high",
        })

    # 3. Hành động mở rộng sang chủ đề ngách đang lên
    for t in nong:
        if len(khuyen) >= TOI_DA:
            break
        khuyen.append({
            "priority": len(khuyen) + 1,
            "action": "explore",
            "target": {"type": "tag", "id": t["tag_id"], "name_vi": t.get("name_vi")},
            "why": [
                f"Tag đang tăng tốc +{t['growth_pct']}% tuần qua",
                f"Chỉ số nhu cầu tìm kiếm đạt {t.get('demand_index')}"
            ],
            "expected": "Thử nghiệm 1–2 mẫu thiết kế mới thuộc chủ đề này theo dạng Make-to-order.",
            "confidence": "medium",
        })

    # Abnormal fallback: nếu không có khuyến nghị nào, kích hoạt MSG151 (tối ưu từ khóa cho listing ít lượt xem nhất)
    is_fallback = False
    if not khuyen and sp_all:
        is_fallback = True
        it_xem = sorted(sp_all, key=lambda p: p.get("rating_count", 0))[:5]
        for idx, p in enumerate(it_xem, 1):
            khuyen.append({
                "priority": idx,
                "action": "optimize_seo",
                "target": {"type": "listing", "id": p["product_id"], "name_vi": p["title"]},
                "why": ["Listing có ít tương tác, đề xuất tối ưu lại tiêu đề và 5 tag chính"],
                "expected": "Tăng khả năng xuất hiện khi người mua tìm kiếm trên sàn",
                "confidence": "low",
                "msg_code": "MSG151"
            })

    is_personalised = len(yeu) > 0 or is_fallback

    meta = build_meta(
        model_version="live-reco-2.0",
        scope="shop" if is_personalised else "platform",
        scope_id=shop_id,
        database=settings.MONGO_DB_LIVE,
        collection="listing_health_scores",
        mode="live",
        attributed_to_live_shop=True,
        sample_size=len(sp_all),
        confidence="high" if len(yeu) > 0 else "medium"
    )

    return ok({
        "shop_id": shop_id,
        "scope": "shop" if is_personalised else "platform",
        "personalised": is_personalised,
        "recommendations": khuyen[:TOI_DA],
        "my_listings_analysed": len(sp_all),
        "my_weak_listings_count": len(yeu),
        "validated": True,
        "validation_note": "Gợi ý được xếp hạng theo tính cấp bách (sản phẩm yếu cần cứu) và thời điểm vàng của các dịp cao điểm.",
        "fallback": is_fallback
    }, meta)
