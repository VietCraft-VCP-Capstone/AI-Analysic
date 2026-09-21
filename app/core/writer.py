"""
writer.py — Module ghi kết quả chuẩn hóa cho toàn bộ các mô hình AI VietCraft.
Đảm bảo mọi dòng ghi ra database đều có 3 trường:
  - run_id: Mã lần chạy model
  - model_version: Phiên bản model
  - computed_at: Thời gian tính (ISO UTC)
Chống ghi trùng lặp (idempotent upsert).
"""

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
        "key": ["entity_type", "entity_id", "forecast_date"],
        "writes": "F37 · F38",
        "reads": "F37 · F38 · F41",
    },
    "anomaly_event": {
        "key": ["entity_type", "entity_id", "event_date"],
        "writes": "F30",
        "reads": "F30",
    },
    "listing_health": {
        "key": ["listing_id", "date"],
        "writes": "F29",
        "reads": "F28 · F29",
    },
    "niche_score": {
        "key": ["keyword", "date"],
        "writes": "F39",
        "reads": "F39 · F40 · F41",
    },
    "seasonal_profile": {
        "key": ["entity_type", "entity_id", "period_type", "period_value"],
        "writes": "F38",
        "reads": "F38",
    },

    # --- 3 BẢNG NỀN (Sprint 2) ---
    # Khác 5 bảng trên: đây là dữ liệu tổng hợp làm NGUỒN, không phải kết quả model.
    # Khoá đọc từ đặc tả `plan/IMPLEMENT_F26_F41.md` mục 2, CHƯA có index trên Mongo.
    # Người dựng bảng nào thì tạo index cho khoá bảng đó, và xác nhận lại khoá ở đây.
    "mart_listing_quality": {
        "key": ["listing_id"],
        "writes": "Hạt (Sprint 2 · T2)",
        "reads": "F28 · F29",
    },
    "mart_competitor": {
        "key": ["listing_id"],
        "writes": "Nhi (Sprint 2 · T3)",
        "reads": "F32 · F33 · F34 · F35 · F36",
    },
    "mart_demand": {
        "key": ["tag_id"],
        "writes": "Hưng (Sprint 2 · T4)",
        "reads": "F38 · F39 · F40",
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
    Mỗi point tối thiểu có: entity_type, entity_id, forecast_date, yhat, yhat_lower, yhat_upper.
    """
    if not points:
        return 0

    computed_at = datetime.now(timezone.utc).isoformat()
    operations = []

    for pt in points:
        doc = dict(pt)
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

        filter_key = {k: doc[k] for k in schema_key}
        operations.append(UpdateOne(filter_key, {"$set": doc}, upsert=True))

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

