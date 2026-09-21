"""
F37 · GET /api/analytics/forecast/revenue?targetId=&window= — dự báo doanh thu.

Quyết định E20: dự báo ở CẤP SHOP, không cấp listing. Benchmark M5 của chính nhóm
đo được ARIMA cấp listing MASE 1,12 — THUA cách ngây thơ; cấp nhóm 0,89 — thắng.
Chuỗi cấp listing trung vị 41 ngày, chỉ 3 ngày có bán (7,3%), quá thưa để mô hình hoá.

  BR-206  khoảng tin cậy 95% LUÔN phải trả về; lo95/hi95 không được null khi status ok
  BR-207  lo95 kẹp ở 0 — không dự báo doanh thu âm
  BR-205  ARIMA khi lịch sử < 90 ngày, LSTM khi >= 90
          -> LSTM CHƯA có, SPEC-03 chưa chốt. Bảng so sánh trả `lstm_mase: null`
             thay vì bịa số. Xem `model_selection` trong phản hồi.
"""

import sys
from pathlib import Path
from typing import Optional

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from fastapi import APIRouter

from app.api.v1._mart import db, tien
from app.api.v1._template import CurrentShop, forbidden, insufficient, invalid_param, mart_not_ready, meta_from_record, ok

router = APIRouter()

MART = "forecast_point"
CUA_SO = {"30": 30, "60": 60, "90": 90}


def _bang_so_sanh(shop_id: str):
    """Bảng so sánh mô hình lấy từ `model_run`, nơi job ghi MỘT LẦN cho mỗi shop."""
    r = db()["model_run"].find_one({"model_name": MART, "status": "COMPLETED"},
                                   {"_id": 0, "parameters": 1, "run_id": 1},
                                   sort=[("started_at", -1)])
    ss = ((r or {}).get("parameters") or {}).get("model_comparison") or {}
    return ss.get(shop_id)


@router.get("/api/analytics/forecast/revenue", tags=["F37 · Đạt"])
def forecast_revenue(shop_id: str = CurrentShop,
                     targetId: Optional[str] = None,
                     window: str = "30"):
    if str(window) not in CUA_SO:
        invalid_param("window", " | ".join(CUA_SO))
    h = CUA_SO[str(window)]

    # targetId mặc định là shop của người gọi. Xin shop khác -> 403 (BR-174/177).
    muc_tieu = targetId or shop_id
    if muc_tieu != shop_id:
        forbidden()

    coll = db()[MART]
    if coll.estimated_document_count() == 0:
        mart_not_ready(MART)

    # Job lưu chuỗi 90 ngày; cắt ra đúng cửa sổ người dùng xin. ARIMA dự báo 90
    # bước cho ra đúng 30 giá trị đầu giống hệt khi dự báo 30 bước, nên cắt là
    # tương đương mà không phải lưu ba bản (xem ghi chú trong writer.MART_SCHEMA).
    diem = list(coll.find({"entity_type": "shop", "entity_id": muc_tieu},
                          {"_id": 0}).sort("forecast_date", 1).limit(h))
    if not diem:
        return insufficient(
            f"Shop `{muc_tieu}` chưa có dự báo. Job chỉ chạy cho shop có từ 90 ngày "
            f"lịch sử doanh thu — dưới ngưỡng đó mô hình không có căn cứ.")

    meta = meta_from_record(diem[0], scope="shop", scope_id=muc_tieu, collection=MART,
                            mode="seed_demo", sample_size=len(diem),
                            confidence="medium")

    ss = _bang_so_sanh(muc_tieu) or {}
    mo_hinh = diem[0].get("model")

    return ok({
        "scope": "shop",
        "target_id": muc_tieu,
        "horizon_days": h,
        "model": mo_hinh,
        "points": [{
            "date": p["forecast_date"],
            "yhat": tien(p["yhat"]),
            "lo95": tien(p["lo95"]),      # BR-207: đã kẹp ở 0 lúc ghi
            "hi95": tien(p["hi95"]),
        } for p in diem],
        "total_forecast_vnd": tien(sum(p["yhat"] for p in diem)),
        "validation": {
            "metric": "MASE",
            "value": diem[0].get("mase"),
            "baseline": diem[0].get("mase_baseline"),
            "beats_baseline": (diem[0].get("mase") is not None
                               and diem[0].get("mase_baseline") is not None
                               and diem[0]["mase"] < diem[0]["mase_baseline"]),
            "holdout_days": ss.get("holdout_days"),
            "note": "MASE < 1 nghĩa là thắng mốc ngây thơ. Đo trên phần dữ liệu GIỮ LẠI.",
        },
        "model_selection": {
            "chosen": mo_hinh,
            "seasonal_naive_mase": ss.get("seasonal_naive_mase"),
            "arima_mase": ss.get("arima_mase"),
            "lstm_mase": ss.get("lstm_mase"),
            "why": ("Chọn theo SỐ ĐO trên phần giữ lại, không theo ý thích. "
                    "LSTM để null vì SPEC-03 chưa chốt làm hay không — bảng so sánh "
                    "thiếu một dòng là kết quả nghiên cứu hợp lệ; điền số giả thì không."),
        },
        "limitation": ("Dự báo ở CẤP SHOP theo quyết định E20. Cấp listing KHÔNG dự báo "
                       "được: chuỗi trung vị 41 ngày, chỉ 7,3% số ngày có bán, và "
                       "benchmark M5 của nhóm đo được ARIMA cấp listing MASE 1,12 — "
                       "thua cả cách ngây thơ."),
    }, meta)
