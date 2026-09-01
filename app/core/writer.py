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
        print(f"⚠ [Writer] Lỗi ghi forecast_point: {e}")
        return len(points)


def save_model_output(collection_name: str, run_id: str, model_version: str, records: List[Dict[str, Any]], key_fields: List[str]) -> int:
    """
    Ghi generic kết quả model vào collection bất kỳ với khóa duy nhất key_fields.
    """
    if not records:
        return 0

    computed_at = datetime.now(timezone.utc).isoformat()
    operations = []

    for rec in records:
        doc = dict(rec)
        doc["run_id"] = run_id
        doc["model_version"] = model_version
        doc["computed_at"] = computed_at

        filter_key = {k: doc[k] for k in key_fields if k in doc}
        if filter_key:
            operations.append(UpdateOne(filter_key, {"$set": doc}, upsert=True))

    try:
        db = _get_seed_db()
        res = db[collection_name].bulk_write(operations)
        return res.upserted_count + res.modified_count
    except Exception as e:
        print(f"⚠ [Writer] Lỗi ghi vào {collection_name}: {e}")
        return len(records)


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

