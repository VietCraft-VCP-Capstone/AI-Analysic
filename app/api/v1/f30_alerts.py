import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from fastapi import APIRouter

from app.api.v1._f30_store import latest_run, read_events
from app.api.v1._live import la_shop_live
from app.api.v1._mart import cua_so, db
from app.api.v1._template import CurrentShop, build_meta, invalid_param, mart_not_ready, ok
from app.services.f30.rules import (MIN_CHANGE_PCT, MIN_CHANGE_VND, MIN_EXPECTED,
                                    MIN_HISTORY_DAYS, MODEL_VERSION, Z_THRESHOLD)

router = APIRouter()

MART = "anomaly_event"
KY_HAN = {"7d": 7, "30d": 30, "90d": 90, "all": None}
WEEKLY_CAP = 3  # trần thông báo/shop/7 ngày, BE giữ (anomaly-alert.delivery.ts)
THRESHOLD = {"z": Z_THRESHOLD, "min_change_pct": MIN_CHANGE_PCT, "min_change_vnd": MIN_CHANGE_VND,
             "min_expected": MIN_EXPECTED, "weekly_cap": WEEKLY_CAP}
CAC_TRUONG = ("metric", "direction", "rule", "z", "expected", "actual", "change_pct",
              "severity", "calendar_sensitive", "confidence", "top_listings")
LY_DO = {
    "chua_chay": "Shop này chưa được chạy phép dò bất thường lần nào.",
    "qua_ngan": "Shop mới có {n} ngày lịch sử, cần ít nhất {can} ngày để biết mức bình thường.",
    "khong_co_san_pham": "Shop chưa có sản phẩm nào để dò bất thường.",
    "loi": "Không phân tích được dữ liệu của shop.",
}


@router.get("/api/notifications/alerts", tags=["F30 · Hiếu"])
def alerts(shop_id: str = CurrentShop, period: str = "90d"):
    if period not in KY_HAN:
        invalid_param("period", " | ".join(KY_HAN))
    live = la_shop_live(shop_id)
    if not live and db()[MART].count_documents({}) == 0:
        mart_not_ready(MART)
    run = latest_run(shop_id)
    if run is None:
        return _ket_qua(shop_id, period, live, [], {}, "chua_chay")
    den = run["run_date"]
    tu = cua_so(den, KY_HAN[period])[0] if KY_HAN[period] else None
    rows = [r for r in read_events(shop_id, tu) if r["event_date"] <= den]
    return _ket_qua(shop_id, period, live, rows, run, run.get("skip_reason"))


def _muc(r):
    return {"id": r["id"], "date": r["event_date"], **{k: r.get(k) for k in CAC_TRUONG}}


def _ket_qua(shop_id, period, live, rows, run, skip):
    meta = build_meta(computed_at=run.get("computed_at"),
                      model_version=run.get("model_version", MODEL_VERSION),
                      scope="shop", scope_id=shop_id, collection=MART,
                      mode="live" if live else "seed_demo", attributed_to_live_shop=live,
                      sample_size=len(rows),
                      confidence=rows[0].get("confidence", "ok") if rows else "medium")
    return ok({
        "shop_id": shop_id,
        "period": period,
        "alerts": [_muc(r) for r in rows],
        "total": len(rows),
        "shop_was_analysed": skip is None,
        "skip_reason": skip,
        "limitation": LY_DO[skip].format(n=run.get("history_days", 0), can=MIN_HISTORY_DAYS)
        if skip else None,
        "threshold": THRESHOLD,
    }, meta)
