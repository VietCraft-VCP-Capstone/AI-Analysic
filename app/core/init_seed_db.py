"""
init_seed_db.py — Khởi tạo 6 bảng kết quả model và compound indexes trên MongoDB vietcraft-seed.
"""

import os
import sys
from pymongo import MongoClient, ASCENDING

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.dirname(BASE_DIR)
sys.path.insert(0, os.path.dirname(APP_DIR))

from app.config import settings


def get_seed_db(uri: str = None, db_name: str = None):
    uri = uri or settings.MONGO_URI
    db_name = db_name or settings.MONGO_DB_SEED
    client = MongoClient(uri, serverSelectionTimeoutMS=10000, retryWrites=True)
    return client[db_name]



def ensure_model_indexes(db) -> dict:
    """Tạo 6 collection và index tương ứng cho các model AI."""
    created = {}

    # 1. model_run — Nhật ký mỗi lần chạy model
    c_run = db["model_run"]
    c_run.create_index([("run_id", ASCENDING)], unique=True)
    c_run.create_index([("model_name", ASCENDING), ("started_at", ASCENDING)])
    created["model_run"] = [idx["name"] for idx in c_run.list_indexes()]

    # 2. forecast_point — Kết quả dự báo
    c_fc = db["forecast_point"]
    c_fc.create_index(
        [("entity_type", ASCENDING), ("entity_id", ASCENDING), ("forecast_date", ASCENDING)],
        unique=True
    )
    c_fc.create_index([("run_id", ASCENDING)])
    created["forecast_point"] = [idx["name"] for idx in c_fc.list_indexes()]

    # 3. seasonal_profile — Thành phần mùa vụ
    c_sp = db["seasonal_profile"]
    c_sp.create_index(
        [("entity_type", ASCENDING), ("entity_id", ASCENDING), ("period_type", ASCENDING), ("period_value", ASCENDING)]
    )
    c_sp.create_index([("run_id", ASCENDING)])
    created["seasonal_profile"] = [idx["name"] for idx in c_sp.list_indexes()]

    # 4. anomaly_event — Cảnh báo bất thường
    c_ano = db["anomaly_event"]
    c_ano.create_index([("entity_type", ASCENDING), ("entity_id", ASCENDING), ("metric", ASCENDING), ("event_date", ASCENDING)])
    c_ano.create_index([("severity", ASCENDING)])
    created["anomaly_event"] = [idx["name"] for idx in c_ano.list_indexes()]

    c_run = db["anomaly_run"]
    c_run.create_index([("entity_type", ASCENDING), ("entity_id", ASCENDING), ("run_date", ASCENDING)])
    created["anomaly_run"] = [idx["name"] for idx in c_run.list_indexes()]

    # 5. niche_score — Điểm cơ hội ngách theo ngày
    c_niche = db["niche_score"]
    c_niche.create_index([("keyword", ASCENDING), ("date", ASCENDING)], unique=True)
    created["niche_score"] = [idx["name"] for idx in c_niche.list_indexes()]

    # 6. listing_health — Điểm sức khoẻ từng sản phẩm
    c_lh = db["listing_health"]
    c_lh.create_index([("listing_id", ASCENDING), ("date", ASCENDING)], unique=True)
    created["listing_health"] = [idx["name"] for idx in c_lh.list_indexes()]

    return created


def main():
    print(f"=== Khởi tạo khung chứa dữ liệu rỗng (Collections & Indexes) trên MongoDB: {settings.MONGO_URI} (DB: {settings.MONGO_DB_SEED}) ===")
    try:
        db = get_seed_db()
        # Ping
        db.command("ping")
        print("✓ Kết nối MongoDB thành công.")
        
        indexes = ensure_model_indexes(db)
        print("\n✓ Đã khởi tạo sẵn 6 collections rỗng & bộ chỉ mục (Indexes) chờ lưu kết quả AI:")
        for col, idx_list in indexes.items():
            print(f"  - Khung bảng {col:<18}: {len(idx_list)} indexes ({', '.join(idx_list)})")
            
        print("\n✅ Khởi tạo khung lưu trữ DB (Task 22) thành công. Sẵn sàng lưu kết quả khi các model AI chạy.")
    except Exception as e:
        print(f"⚠ Lỗi kết nối hoặc khởi tạo index: {e}")
        print("  (Vui lòng kiểm tra biến môi trường MONGO_URI nếu đang chạy remote)")



if __name__ == "__main__":
    main()
