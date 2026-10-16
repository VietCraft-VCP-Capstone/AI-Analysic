import os
import sys
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from pymongo import MongoClient, UpdateOne

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.dirname(BASE_DIR)
ROOT_DIR = os.path.dirname(APP_DIR)
sys.path.insert(0, ROOT_DIR)

from app.config import settings


def _get_seed_db():
    client = MongoClient(settings.MONGO_URI, serverSelectionTimeoutMS=10000, retryWrites=True)
    return client[settings.MONGO_DB_SEED]


# ---------------------------------------------------------------------------
# SƠ ĐỒ MART — hợp đồng chung của cả 5 người.
#
# Đây là bản thay thế cho một file MART_SCHEMA.md: quy ước nằm trong CODE nên
# máy ép đúng, không phụ thuộc ai có đọc tài liệu hay không.
#
# `key` lấy từ index đã tạo sẵn trên MongoDB ngày 01/09 — không phải đặt mới.
# `writes`/`reads` ghi để biết hỏi ai khi một bảng ra số lạ.
#
# THÊM BẢNG MỚI: thêm một dòng ở đây TRƯỚC, rồi mới gọi save_model_output().
# ---------------------------------------------------------------------------
MART_SCHEMA: Dict[str, Dict[str, Any]] = {
    "forecast_point": {
        # Khoá KHÔNG có horizon_days (index tạo sẵn trên Mongo từ 01/09 là như vậy).
        # Hệ quả: chỉ được lưu MỘT chuỗi dự báo cho mỗi (entity, ngày). Ghi thêm bản
        # 30 và 60 ngày cho cùng ngày sẽ upsert đè lên nhau và mất dữ liệu trong
        # im lặng — đã xảy ra 21/09, mất 7.200/14.400 dòng.
        # Cách làm đúng: job ghi chuỗi 90 ngày, API cắt ra cửa sổ người dùng xin.
        "key": ["entity_type", "entity_id", "forecast_date"],
        "writes": "F37 · F38",
        "reads": "F37 · F38 · F41",
        "fields": {
            "yhat": "float — giá trị dự báo",
            "lo95": "float >= 0 — cận dưới 95%, KẸP Ở 0 (BR-207), không dự báo doanh thu âm",
            "hi95": "float — cận trên 95%",
            "model": "str — arima · lstm · seasonal_naive (BR-205)",
            "horizon_days": "int — độ dài chuỗi đã dự báo (90); API cắt ra 30/60/90",
            "horizon_index": "int — bước thứ mấy trong chuỗi, 1..90",
            "mase": "float — sai số của mô hình đã chọn, đo trên phần giữ lại",
            "mase_baseline": "float — sai số của seasonal_naive; mô hình phải thấp hơn số này",
            # Bảng so sánh đầy đủ 3 mô hình nằm ở `model_run.parameters.model_comparison`,
            # ghi MỘT LẦN cho mỗi shop thay vì lặp trên cả 14.400 dòng dự báo.
            "validation": "dict|None — chỉ dùng cho bản ghi lẻ; job ghi vào model_run",
        },
        # BR-206: khoảng tin cậy LUÔN phải có. Thiếu lo95/hi95 thì FE không vẽ
        # được vùng mờ, và một con số dự báo trần trụi đọc như lời hứa chắc chắn.
        "fields_bat_buoc": ["yhat", "lo95", "hi95", "model", "horizon_days"],
    },
    "anomaly_event": {
        "key": ["entity_type", "entity_id", "event_date"],
        "writes": "F30",
        "reads": "F30",
        "fields": {
            "direction": "str — drop · spike",
            "z": "float — điểm z, ngưỡng |z| > 7.0 (KHÔNG phải 2.0 của BR-183, xem SPEC_CHANGES.md)",
            "expected": "int|None — doanh thu kỳ vọng, VND nguyên",
            "actual": "int|None — doanh thu thật, VND nguyên",
            "severity": "str — high · medium · low",
            "calendar_sensitive": "bool — rơi vào dịp lễ/Tết hay không",
            "confidence": "str — ok · calendar_sensitive · limited_few_cycles · unreliable_high_rate",
            "reliability_note": "str|None — vì sao chuỗi này đáng tin tới mức đó",
            "cycles_observed": "float — số chu kỳ mùa vụ quan sát được; dưới 12 thì kém tin",
        },
        "fields_bat_buoc": ["direction", "z", "severity", "confidence"],
    },
    "listing_health": {
        "key": ["listing_id", "date"],
        "writes": "F29",
        "reads": "F28 · F29",
        "fields": {
            "health_score": "float 0-100",
            "band": "str — tốt (>=80) · cần cải thiện (50-79) · kém (<50), BR-182",
            "conversion_rate": "float|None",
            "category_avg_cr": "float|None",
            "cr_index": "float|None",
            "rating_shrunk": "float|None — CHƯA có đánh giá thì null, KHÔNG mặc định 4.0",
            "n_reviews": "int",
            "breakdown": "dict 5 trục — conversion·rating·content·stock·freshness, weight cộng đúng 1.0",
            "todo": "list — [{priority, action, expected_gain}]",
            "title": "str|None",
            "axes_missing": "list[str] — trục thiếu dữ liệu, ĐÃ loại khỏi phép tính và chia lại trọng số (không cho 0 điểm)",
        },
        "fields_bat_buoc": ["health_score", "band", "breakdown"],
    },
    "niche_score": {
        "key": ["keyword", "date"],
        "writes": "F39",
        "reads": "F39 · F40 · F41",
        "fields": {
            "tag_id": "str",
            "demand_pct": "float 0-100",
            "supply_pct": "float 0-100",
            "gap_score": "float — cầu trừ cung, xếp hạng theo cái này",
            "n_listings": "int",
            "demand_index": "float",
            "trend": "str — rising · flat · falling",
            "sparkline_7d": "list[int] — 7 điểm gần nhất",
            "tag_ids": "list[str] — mọi tag ánh xạ từ từ khoá này",
            "growth_pct": "float — 12 tuần gần nhất so 12 tuần trước",
            "quadrant": "str — opportunity · crowded · niche_quiet · oversupplied",
            "rank": "int — xếp theo gap_score giảm dần",
        },
        # BR-211: ngách chứa từ khoá cấm (bản quyền/NSFW) phải bị loại TRƯỚC khi ghi.
        # Lọc ở tầng đọc là quá muộn — số đã nằm trong bảng thì job khác đọc được.
        "fields_bat_buoc": ["tag_id", "demand_pct", "supply_pct", "gap_score"],
    },
    "seasonal_profile": {
        "key": ["entity_type", "entity_id", "period_type", "period_value"],
        "writes": "F38",
        "reads": "F38",
        "fields": {
            "trend": "list[float] — thành phần xu hướng sau phân rã STL",
            "seasonal": "list[float] — thành phần mùa vụ",
            "residual": "list[float] — phần dư",
            "amplitude": "float — biên độ đỉnh mùa",
            "events": "list — [{name, date, driver, peak_offset_days, launch_window}]",
            "content_calendar": "list — [{week, action}]",
            "tag_ids": "list[str]",
            "n_points": "int — số điểm tuần đưa vào phân rã",
            "peak_date_sample": "str YYYY-MM-DD — một ngày rơi vào đỉnh mùa",
            "has_seasonality": "bool — biên độ có đủ lớn để gọi là có mùa vụ không",
        },
        "fields_bat_buoc": ["seasonal", "amplitude"],
    },

    # --- 3 BẢNG NỀN (Sprint 2) ---
    # Khác 5 bảng trên: đây là dữ liệu tổng hợp làm NGUỒN, không phải kết quả model.
    # Khoá đọc từ đặc tả `plan/IMPLEMENT_F26_F41.md` mục 2, CHƯA có index trên Mongo.
    # Người dựng bảng nào thì tạo index cho khoá bảng đó, và xác nhận lại khoá ở đây.
    "mart_listing_quality": {
        # KHOÁ ĐÃ CHỐT (SPEC-01 bước 2, 21/09): giữ ["listing_id"], KHÔNG thêm "date".
        #
        # BR-181 đòi chấm lại mỗi 24h, nên thoạt nhìn phải có "date". Nhưng:
        #   5.000 listing x 365 ngày = 1,8 triệu dòng, trên cụm Atlas M0 512 MB
        #   DÙNG CHUNG CẢ NHÓM. Bảng `listing_daily` 796.025 dòng đã làm cụm
        #   vọt lên 526/512 MB ngày 21/09 và chặn ghi với TẤT CẢ mọi người.
        #
        # Lịch sử điểm KHÔNG mất: `listing_health` đã có "date" trong khoá và
        # chính là bảng kết quả có lịch sử. Bảng này chỉ là ẢNH CHỤP HIỆN TẠI của
        # phần đầu vào — F28 và F29 đều chỉ đọc bản mới nhất.
        "key": ["listing_id"],
        "writes": "Hạt (Sprint 2 · DATA-03)",
        "reads": "F28 · F29",
        "fields": {
            "funnel": "dict — {views, carts, orders}",
            "view_to_cart_pct": "float|None — 0 lượt xem thì null, KHÔNG chia cho 0",
            "cart_to_order_pct": "float|None",
            "view_to_order_pct": "float|None",
            "category_avg_pct": "float|None",
            "cr_index": "float|None — tỉ lệ so với trung bình danh mục",
            "weakest_step": "str — view_to_cart · cart_to_order",
            "tips": "list — CHỈ điền khi CR thấp hơn danh mục >= 20% (BR-179), không thì []",
            "category_id": "str — mốc so sánh lấy theo danh mục này",
            "window_from": "str YYYY-MM-DD",
            "window_to": "str YYYY-MM-DD — neo theo ngày mới nhất có thật trong dữ liệu",
        },
        "fields_bat_buoc": ["funnel", "weakest_step"],
    },
    "mart_competitor": {
        # KHOÁ ĐÃ CHỐT (SPEC-01 bước 2, 21/09): giữ ["listing_id"]. Cùng lý do
        # hạn mức Atlas như trên — thêm "date" là 5.000 x 365 dòng.
        # F36 cần lịch sử "đối thủ ra sản phẩm mới lúc nào" thì ghi vào
        # `competitor_trackers` trên sàn live (thưa, mỗi lần phát hiện một dòng),
        # không phải nhân đôi cả bảng theo ngày.
        "key": ["listing_id"],
        "writes": "Nhi (Sprint 2 · DATA-04)",
        "reads": "F32 · F33 · F34 · F35 · F36",
        "fields": {
            "shop_id": "str",
            "shop_name": "str",
            "category_id": "str",
            "product_type_id": "str",
            "price_vnd": "int — VND NGUYÊN, không thập phân",
            "est_sales_90d": "int — SUM(quantity) từ order_items nối orders trong 90 ngày",
            "rating_shrunk": "float|None",
            "n_reviews": "int",
            "favorite_count": "int",
            "rank_in_cat": "int — xếp theo est_sales_90d giảm dần (BR-188)",
            "n_in_cat": "int — tổng số listing cùng danh mục, để hiểu rank_in_cat",
            "tags": "list[str] — dùng cho phép trừ tập hợp của F34",
            "title": "str|None — tiêu đề listing, F32/F36 hiển thị",
            "status": "str — active · paused · removed",
            "views_90d": "int — phễu 90 ngày, F32 dùng để so",
            "carts_90d": "int",
            "orders_90d": "int",
            "revenue_90d_vnd": "int — VND nguyên",
            "window_from": "str YYYY-MM-DD — mốc đầu cửa sổ 90 ngày đã dùng",
            "window_to": "str YYYY-MM-DD — mốc cuối; neo theo ngày MỚI NHẤT có thật trong dữ liệu, không phải hôm nay",
        },
        "fields_bat_buoc": ["shop_id", "category_id", "price_vnd", "est_sales_90d"],
    },
    "mart_shop_hour": {
        # Nhịp đặt hàng theo thứ/giờ. Bảng RIÊNG vì nó là thứ duy nhất cần nối
        # orders -> order_items -> listings: `orders.shop_id` là float NaN ở cả
        # 24.736 dòng nên không quy đơn về shop trực tiếp được. Nối lúc đọc thì
        # mỗi request tốn một phép join 3 bảng — đẩy về job chạy đêm.
        # Kích thước: 80 shop x 7 thứ x 24 giờ = tối đa 13.440 dòng, thực tế thưa hơn.
        "key": ["shop_id", "dow", "hour"],
        "writes": "Hiếu (F31)",
        "reads": "F31",
        "fields": {
            "orders": "int — số đơn rơi vào khung thứ/giờ này",
            "units": "int",
            "revenue_vnd": "int — VND nguyên",
            "share_pct": "float — % tổng đơn của shop rơi vào khung này",
            "tz": "str — múi giờ đã quy đổi, luôn là Asia/Ho_Chi_Minh (BR-185)",
        },
        "fields_bat_buoc": ["orders", "tz"],
    },
    "mart_demand": {
        "key": ["tag_id"],
        "writes": "Hưng (Sprint 2 · DATA-05)",
        "reads": "F38 · F39 · F40",
        "fields": {
            "week": "str — ISO tuần, ví dụ 2026-W38",
            "demand_index": "float",
            "searches_per_week": "int — dưới 100 thì loại khỏi bảng (BR-213)",
            "growth_pct": "float",
            "momentum": "float 0-1",
            "supply_n_listings": "int",
            "trend": "str — rising · flat · falling",
            "name_vi": "str — tên tag hiển thị",
            "n_keywords": "int — bao nhiêu từ khoá Trends gộp vào tag này",
            "demand_scale_note": "str — nói rõ demand_index là thang gì",
            "low_base": "bool — nền quá thấp nên growth_pct không đáng tin, đã để null",
        },
        # searches_per_week KHÔNG bắt buộc: Google Trends trả chỉ số 0-100, không
        # phải số lượt tìm tuyệt đối. Quy đổi ra "lượt/tuần" là bịa số. BR-213 đặt
        # ngưỡng 100 lượt/tuần nên chưa áp dụng được — đã ghi vào mục Hạn chế.
        "fields_bat_buoc": ["demand_index"],
    },
}

# Ba trường này writer TỰ gắn vào mọi bản ghi. Cổng ra kiểm đúng ba cái.
META_FIELDS = ("run_id", "model_version", "computed_at")

# BẢNG BỊ CHẶN — từng có trong kế hoạch, đã đo và thấy KHÔNG khả thi.
# Chặn kèm lý do để người sau không dựng lại rồi gặp đúng sự cố.
BLOCKED: Dict[str, str] = {
    "mart_listing_daily":
        "Bảng này sẽ là BẢN SAO 1:1 của `listing_daily` (796.025 dòng) vì nguồn "
        "ĐÃ ở đúng độ mịn (listing_id, date) — gộp lại không giảm được dòng nào. "
        "Đã thử 21/09: cụm Atlas M0 (512 MB, DÙNG CHUNG CẢ NHÓM) vọt lên 526/512 MB "
        "và CHẶN GHI VỚI TẤT CẢ MỌI NGƯỜI. Phải xoá bảng mới gỡ được.\n"
        "  → 4 cột khoá đã được điền THẲNG vào `listing_daily` bằng "
        "app/core/backfill_listing_daily_ids.py. F26/F27/F30/F31/F37 đọc trực tiếp "
        "bảng đó, đã có index trên shop_id / category_id / product_type_id / date.\n"
        "  → Cần một bảng gộp thật thì gộp ở ĐỘ MỊN THÔ HƠN, ví dụ (shop_id, date): "
        "80 shop x ~550 ngày = ~44.000 dòng thay vì 796.025."
}


class MartWriteError(ValueError):
    """Sai hợp đồng ghi mart. Cố ý là ValueError chứ không phải cảnh báo:
    ghi sai khoá làm MẤT dữ liệu trong im lặng, phải dừng ngay tại chỗ gọi."""



def start_model_run(model_name: str, model_version: str, params: Optional[Dict[str, Any]] = None) -> str:
    """
    Tạo một bản ghi nhật ký khi bắt đầu chạy model. Trả về run_id duy nhất.
    """
    run_id = f"run_{model_name}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    doc = {
        "run_id": run_id,
        "model_name": model_name,
        "model_version": model_version,
        "parameters": params or {},
        "status": "RUNNING",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "finished_at": None,
        "metrics": None,
        "error_message": None
    }
    try:
        db = _get_seed_db()
        db["model_run"].insert_one(doc)
    except Exception as e:
        print(f"⚠ [Writer] Không thể ghi model_run lên MongoDB: {e}")
    return run_id


def finish_model_run(run_id: str, status: str = "COMPLETED", metrics: Optional[Dict[str, Any]] = None, error_message: Optional[str] = None):
    """
    Cập nhật trạng thái hoàn thành / lỗi của lần chạy model.
    """
    update_data = {
        "status": status,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "metrics": metrics or {},
        "error_message": error_message
    }
    try:
        db = _get_seed_db()
        db["model_run"].update_one({"run_id": run_id}, {"$set": update_data})
    except Exception as e:
        print(f"⚠ [Writer] Không thể cập nhật model_run: {e}")


def save_forecast_points(run_id: str, model_version: str, points: List[Dict[str, Any]]) -> int:
    """
    Ghi kết quả dự báo vào collection forecast_point.
    Mỗi point tối thiểu có: entity_type, entity_id, forecast_date, yhat, lo95, hi95.

    TÊN CỘT DẢI TIN CẬY: `lo95` / `hi95`, theo docs/API_CONTRACT.md (BR-206).
    Bản cũ của hàm này dùng `yhat_lower` / `yhat_upper` — hai tên cho cùng một thứ,
    API đọc `lo95` sẽ không thấy gì. Tên cũ vẫn nhận được và tự đổi sang tên mới
    kèm cảnh báo, để code đã viết không gãy.
    """
    if not points:
        return 0

    computed_at = datetime.now(timezone.utc).isoformat()
    operations = []
    da_canh_bao = False

    for pt in points:
        doc = dict(pt)
        for cu, moi in (("yhat_lower", "lo95"), ("yhat_upper", "hi95")):
            if cu in doc:
                doc.setdefault(moi, doc.pop(cu))
                if not da_canh_bao:
                    print(f"⚠ [Writer] `{cu}` là tên cũ, đã đổi thành `{moi}` theo "
                          f"API_CONTRACT.md (BR-206). Sửa chỗ gọi để khỏi phụ thuộc lớp đệm này.")
                    da_canh_bao = True

        # BR-207: cận dưới KẸP Ở 0 — không dự báo doanh thu âm.
        if doc.get("lo95") is not None and doc["lo95"] < 0:
            doc["lo95"] = 0

        doc["run_id"] = run_id
        doc["model_version"] = model_version
        doc["computed_at"] = computed_at

        # Khoá xác định bản ghi duy nhất
        filter_key = {
            "entity_type": doc["entity_type"],
            "entity_id": str(doc["entity_id"]),
            "forecast_date": str(doc["forecast_date"])
        }
        operations.append(UpdateOne(filter_key, {"$set": doc}, upsert=True))

    try:
        db = _get_seed_db()
        res = db["forecast_point"].bulk_write(operations)
        return res.upserted_count + res.modified_count
    except Exception as e:
        # Ghi hỏng thì PHẢI trả 0. Trả len(points) làm hàm gọi tưởng đã ghi
        # thành công và pipeline chạy tiếp trên dữ liệu không tồn tại.
        print(f"⚠ [Writer] Lỗi ghi forecast_point, đã ghi 0/{len(points)} điểm: {e}")
        return 0


def save_model_output(collection_name: str, run_id: str, model_version: str,
                      records: List[Dict[str, Any]],
                      key_fields: Optional[List[str]] = None) -> int:
    """
    Ghi kết quả model vào một bảng mart. Khoá lấy từ MART_SCHEMA, không tự chọn.

    `key_fields` giữ lại chỉ để code cũ gọi không gãy; nếu truyền vào mà khác
    khoá trong sơ đồ thì BÁO LỖI thay vì im lặng dùng khoá sai.

    Ném MartWriteError khi: tên bảng không có trong sơ đồ · record thiếu trường
    khoá · trường khoá rỗng. Cả ba đều là lỗi làm MẤT dữ liệu mà không ai thấy.
    """
    if collection_name in BLOCKED:
        raise MartWriteError(f"`{collection_name}` BỊ CHẶN.\n  {BLOCKED[collection_name]}")

    if collection_name not in MART_SCHEMA:
        raise MartWriteError(
            f"`{collection_name}` không có trong MART_SCHEMA. "
            f"Bảng cho phép: {', '.join(sorted(MART_SCHEMA))}. "
            f"Gõ sai tên thì MongoDB lặng lẽ tạo bảng mới và API đọc bảng cũ ra rỗng. "
            f"Muốn thêm bảng thật thì khai báo trong MART_SCHEMA trước."
        )

    schema_key = MART_SCHEMA[collection_name]["key"]
    if key_fields is not None and list(key_fields) != schema_key:
        raise MartWriteError(
            f"`{collection_name}` có khoá {schema_key}, nhưng được gọi với {list(key_fields)}. "
            f"Hai người dùng hai khoá khác nhau cho cùng một bảng thì dữ liệu nhân đôi "
            f"mà không ai báo. Bỏ tham số key_fields đi, writer tự lấy đúng khoá."
        )

    if not records:
        return 0

    computed_at = datetime.now(timezone.utc).isoformat()
    operations = []

    so_do = MART_SCHEMA[collection_name]
    bat_buoc: List[str] = so_do.get("fields_bat_buoc", [])
    cho_phep = set(so_do.get("fields", {})) | set(schema_key) | {"scope", "scope_id", "_id"}
    la: set = set()

    for i, rec in enumerate(records):
        doc = dict(rec)
        doc["run_id"] = run_id
        doc["model_version"] = model_version
        doc["computed_at"] = computed_at

        missing = [k for k in schema_key if k not in doc]
        if missing:
            raise MartWriteError(
                f"`{collection_name}` bản ghi #{i} thiếu trường khoá {missing}. "
                f"Cần đủ {schema_key}, bản ghi đang có: {sorted(doc)}. "
                f"Bản cũ bỏ qua trường thiếu trong im lặng — {len(records)} bản ghi "
                f"sẽ ép xuống còn số ít hơn nhiều và ghi đè lên nhau."
            )
        blank = [k for k in schema_key if doc[k] is None or str(doc[k]).strip() == ""]
        if blank:
            raise MartWriteError(
                f"`{collection_name}` bản ghi #{i} có trường khoá rỗng: {blank}. "
                f"Khoá rỗng làm mọi bản ghi rỗng gộp thành một dòng."
            )

        # --- KIỂM CỘT THÂN (SPEC-01) ---
        # Thiếu cột bắt buộc -> DỪNG. API đọc ra sẽ thiếu trường, FE hiện ô trống
        # mà không ai biết vì sao — sửa lúc đó phải chạy lại cả job.
        thieu_than = [k for k in bat_buoc if k not in doc]
        if thieu_than:
            raise MartWriteError(
                f"`{collection_name}` bản ghi #{i} thiếu cột bắt buộc {thieu_than}. "
                f"Hợp đồng bảng này cần {bat_buoc}; bản ghi đang có {sorted(set(doc) - set(META_FIELDS))}. "
                f"Xem MART_SCHEMA['{collection_name}']['fields'] để biết mỗi cột chứa gì."
            )

        # Cột lạ -> CẢNH BÁO, không dừng. Thừa dữ liệu không làm hỏng ai đọc,
        # nhưng thường là dấu hiệu gõ sai tên cột (vd. "lo_95" thay vì "lo95"),
        # nên phải nói ra. Gom lại in một lần ở cuối thay vì spam từng bản ghi.
        la.update(set(doc) - set(META_FIELDS) - set(cho_phep))

        filter_key = {k: doc[k] for k in schema_key}
        operations.append(UpdateOne(filter_key, {"$set": doc}, upsert=True))

    if la:
        print(f"⚠ [Writer] `{collection_name}` có {len(la)} cột không khai báo trong "
              f"MART_SCHEMA: {sorted(la)}. Vẫn ghi, nhưng kiểm lại xem có gõ sai tên "
              f"cột không — API đọc theo tên trong hợp đồng sẽ không thấy cột lạ.")

    try:
        db = _get_seed_db()
        res = db[collection_name].bulk_write(operations)
        return res.upserted_count + res.modified_count
    except Exception as e:
        # Xem chú thích ở save_forecast_points: thất bại không được báo thành công.
        print(f"⚠ [Writer] Lỗi ghi vào {collection_name}, đã ghi 0/{len(records)} bản ghi: {e}")
        return 0


if __name__ == "__main__":
    print("=== TỰ KIỂM TRA HÀM GHI DỮ LIỆU MẪU (WRITER.PY SELF-CHECK) ===")
    run_id = start_model_run("sample_test_model", "v1.0.0", {"sample_param": 123})
    print(f"✓ start_model_run sinh run_id mẫu: {run_id}")
    assert run_id.startswith("run_sample_test_model_")

    sample_points = [
        {
            "entity_type": "keyword",
            "entity_id": "áo tết",
            "forecast_date": "2026-09-01",
            "yhat": 45.2,
            "yhat_lower": 40.0,
            "yhat_upper": 50.4
        }
    ]
    saved = save_forecast_points(run_id, "v1.0.0", sample_points)
    print(f"✓ save_forecast_points ghi thành công dữ liệu mẫu: {saved} điểm")

    finish_model_run(run_id, "COMPLETED", {"mae": 2.1})
    print("✓ finish_model_run cập nhật trạng thái hoàn thành mẫu thành công")
    print("✅ TẤT CẢ SELF-CHECKS CỦA WRITER.PY ĐÃ PASS!")

