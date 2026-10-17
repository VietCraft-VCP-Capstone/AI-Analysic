import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from fastapi import APIRouter

from app.api.v1._live import la_shop_live
from app.api.v1._live_shop import alerts_live
from app.api.v1._mart import cua_so, db, ngay_moi_nhat
from app.api.v1._template import CurrentShop, invalid_param, mart_not_ready, meta_from_record, ok

router = APIRouter()

MART = "anomaly_event"
KY_HAN = {"7d": 7, "30d": 30, "90d": 90, "all": None}
NGUONG = {"z": 7.0,
          "why": ("Đo thực nghiệm: ngưỡng 2.0 của BR-183 cho 7,38% báo động giả, "
                  "ngưỡng 7.0 còn 0,6%. Code đúng hơn SRS — xem docs/SPEC_CHANGES.md.")}


@router.get("/api/notifications/alerts", tags=["F30 · Hiếu"])
def alerts(shop_id: str = CurrentShop, period: str = "90d"):
    if period not in KY_HAN:
        invalid_param("period", " | ".join(KY_HAN))
    if la_shop_live(shop_id):
        rows, duoc_do, ghi_chu, meta = alerts_live(shop_id, KY_HAN[period])
        return _ket_qua(shop_id, period, [{**r, "date": r["event_date"]} for r in rows],
                        duoc_do, ghi_chu, meta)

    coll = db()[MART]
    if coll.estimated_document_count() == 0:
        mart_not_ready(MART)

    loc = {"entity_type": "shop", "entity_id": shop_id}
    if KY_HAN[period]:
        moi = ngay_moi_nhat({"shop_id": shop_id}) or ""
        if moi:
            tu, den = cua_so(moi, KY_HAN[period])
            loc["event_date"] = {"$gte": tu, "$lte": den}

    rows = list(coll.find(loc, {"_id": 0}).sort("event_date", -1))

    duoc_do = coll.count_documents({"entity_id": shop_id}) > 0
    mau = rows[0] if rows else coll.find_one({}, {"_id": 0})
    meta = meta_from_record(mau, scope="shop", scope_id=shop_id, collection=MART,
                            mode="seed_demo", sample_size=len(rows),
                            confidence=(rows[0].get("confidence", "ok") if rows else "medium"))

    return _ket_qua(shop_id, period, [{**r, "date": r["event_date"]} for r in rows], duoc_do,
                    None if duoc_do else
                    "Shop này KHÔNG được đưa vào phép dò: chuỗi doanh thu ngày có quá "
                    "nhiều ngày bằng 0 (dưới 40% số ngày có bán), nền của chuỗi là 0 nên "
                    "mọi ngày bán được đều bị chấm là đột biến. Không phải shop không có "
                    "bất thường — là chưa đo được.", meta)


def _ket_qua(shop_id, period, rows, duoc_do, ghi_chu, meta):
    return ok({
        "shop_id": shop_id,
        "period": period,
        "alerts": [{
            "date": r["date"],
            "direction": r["direction"],
            "z": r["z"],
            "expected_vnd": r.get("expected"),
            "actual_vnd": r.get("actual"),
            "severity": r["severity"],
            "calendar_sensitive": r.get("calendar_sensitive"),
            "confidence": r.get("confidence"),
        } for r in rows],
        "total": len(rows),
        "shop_was_analysed": duoc_do,
        "threshold": NGUONG,
        "limitation": ghi_chu,
    }, meta)
