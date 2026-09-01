# 📖 Hướng Dẫn Kiểm Thử & Chạy Toàn Bộ Hệ Thống (USAGE GUIDE)

> **VietCraft AI Analytics & Recommendation Engine (SEP490)**  
> Tài liệu hướng dẫn chi tiết các bước vận hành, nghiệm thu và kiểm thử (verify) toàn bộ dữ liệu từ tầng Database, Data Layer, Mô hình AI đến FastAPI Web Service.

---

## 📋 MỤC LỤC
1. [Chuẩn bị Môi trường & Biến Môi trường](#1-chuẩn-bị-môi-trường--biến-môi-trường)
2. [Cấu trúc & Vị trí Đặt File Dữ liệu Nguồn (`app/data/`)](#2-cấu-trúc--vị-trí-đặt-file-dữ-liệu-nguồn-appdata)
3. [Phần 1: Kiểm tra Dữ liệu Danh mục & Tags (`verify_tags.py`)](#phần-1-kiểm-tra-dữ-liệu-danh-mục--tags)
4. [Phần 2: Kiểm tra Dữ liệu Catalog & Cấu hình Giá (`verify_catalog.py`)](#phần-2-kiểm-tra-dữ-liệu-catalog--cấu-hình-giá)
5. [Phần 3: Kiểm tra Hạ tầng Lưu trữ MongoDB (`init_seed_db.py`)](#phần-3-kiểm-tra-hạ-tầng-lưu-trữ-mongodb)
6. [Phần 4: Kiểm tra Tầng Truy xuất & Ghi dữ liệu (`loader.py` & `writer.py`)](#phần-4-kiểm-tra-tầng-truy-xuất--ghi-dữ-liệu)
7. [Phần 5: Kiểm tra Các Thuật toán AI Lõi (`calendar_vn.py`, `stl_service.py`)](#phần-5-kiểm-tra-các-thuật-toán-ai-lõi)
8. [Phần 6: Chạy Nghiên cứu Mốc Baseline & M5 Benchmark](#phần-6-chạy-nghiên-cứu-mốc-baseline--m5-benchmark)
9. [Phần 7: Kiểm tra Tính Toàn vẹn Liên kết Dữ liệu 5 Thành viên](#phần-7-kiểm-tra-tính-toàn-vẹn-liên-kết-dữ-liệu-5-thành-viên)
10. [Phần 8: Khởi chạy & Verify Web API Server (FastAPI)](#phần-8-khởi-chạy--verify-web-api-server-fastapi)
11. [🚀 Lệnh Chạy Toàn Bộ Test Suite Trong 1 Dòng (One-Liner)](#-lệnh-chạy-toàn-bộ-test-suite-trong-1-dòng-one-liner)

---

## 1. Chuẩn bị Môi trường & Biến Môi trường

Trước khi thực hiện bất kỳ lệnh kiểm thử nào, hãy đảm bảo bạn đang ở thư mục `AI-Analysic` và đã kích hoạt Virtual Environment.

```bash
cd /home/rio/Documents/CODE/nodejs/vc-ai/AI-Analysic

# 1. Kích hoạt môi trường ảo
source .venv/bin/activate

# 2. Đảm bảo file cấu hình app/.env đã có URI MongoDB Atlas
cat app/.env
```

---

## 2. Cấu trúc & Vị trí Đặt File Dữ liệu Nguồn (`app/data/`)

Tất cả các file dữ liệu chuẩn hóa sau khi cào hoặc tạo ra (seed data / master CSV) cần được copy/paste vào thư mục trung tâm: **`app/data/`**

```text
AI-Analysic/
└── app/
    └── data/
        ├── categories.csv            # 85 Danh mục chuẩn
        ├── tags.csv                  # 77 Tags chuẩn
        ├── tag_keyword_map.csv       # Liên kết tag với từ khóa Google Trends
        ├── vc_setting.csv            # Cấu hình tỷ giá & sàn margin hệ thống
        ├── vc_price_rule.csv         # 138 Quy tắc tính giá theo loại sản phẩm
        ├── vc_product_type.csv       # 138 Loại sản phẩm
        ├── vc_catalog_variant.csv    # ~25.000 Biến thể sản phẩm (size, màu, giá vốn)
        ├── seed_keywords.json        # 40 Từ khóa hạt giống
        └── baselines.json            # Chỉ số phân bố nền (phễu, thời gian, sao)
```

> **💡 Lưu ý cho Automation / CI:** Các script kiểm tra đều hỗ trợ cờ CLI (như `--tags`, `--categories`, `--data-dir`) nếu bạn muốn trỏ sang thư mục lưu trữ khác mà không cần copy vào `app/data/`.

---

## Phần 1: Kiểm tra Dữ liệu Danh mục & Tags

Kiểm tra 5 tiêu chuẩn chất lượng dữ liệu của Nhi (trùng lặp, sót từ khóa, số lượng tag, tag mồ côi, và 10 test case chuẩn hóa):

```bash
python app/seed/catalog/verify_tags.py
```
*(Hoặc chỉ định đường dẫn ngoài: `python app/seed/catalog/verify_tags.py --tags <path_to_tags.csv> --categories <path_to_categories.csv>`)*

### 🎯 Expected Output:
```text
=== VietCraft QA Verification Suite & Tags QA Logger ===
Chạy 10 test làm sạch tag:
  [OK] 'Áo Tết' -> 'ao-tet'
  [OK] 'ao tet' -> 'ao-tet'
  ...
QA SUMMARY TABLE:
  1. 1. Có tag nào trùng mã không                  [ĐẠT] (0 tag bị trùng)
  2. 2. Có từ khoá Google nào chưa có tag không    [ĐẠT] (0 từ khóa bị sót)
  3. 3. Tổng số tag                                [ĐẠT] (77 tag (phạm vi: từ 60 tới 80))
  4. 4. Có tag nào không thuộc danh mục nào không  [ĐẠT] (0 tag mồ côi)
  5. 5. Chạy 10 test làm sạch tag                  [ĐẠT] (10/10 bài test thông qua)

🎉 ALL QA CHECKS PASSED!
Report written to .../docs/qc/tags.md successfully!
```

---

## Phần 2: Kiểm tra Dữ liệu Catalog & Cấu hình Giá

Kiểm tra 8 tiêu chuẩn dữ liệu của Hưng (setting, margin rule, 138 product types, cost source, định dạng tiền VND, mã màu hex, đổi inch -> cm):

```bash
python app/seed/catalog/verify_catalog.py
```
*(Hoặc chỉ định thư mục ngoài: `python app/seed/catalog/verify_catalog.py --data-dir <path_to_data_folder>`)*

### 🎯 Expected Output:
```text
======================================================================
VERIFICATION REPORT — VIETCRAFT CATALOG & CONFIGURATION
======================================================================
[Check 1] System Settings Table (vc_setting)
  PASS: usd_vnd_rate=26000, min_margin=1.6 (4 settings present)
[Check 2] Price Margin Rules (vc_price_rule)
  PASS: 138 rules configured with min_margin=1.6, suggested=[2.0, 3.0]
[Check 3] 138 Product Types & 11 Groups (vc_product_type)
  PASS: Exactly 138 product types across 11 groups
[Check 4] Cost Source Transparency (printify vs estimated)
  PASS: 29 Real Printify types, 109 Estimated types clearly marked
[Check 5] Currency Normalization (Integer VND)
  PASS: 25,773 variants generated, 100% VND integers >= 10,000đ
[Check 6] Color Attribute Normalization (color_vi + color_hex)
  PASS: 24,944 colored variants normalized with Vietnamese name & Hex code
[Check 7] Poster & Wallart Size Conversion (inch -> cm)
  PASS: 100% of wallart/poster sizes converted to cm
[Check 8] Classification Accuracy (No Stainless Steel Mugs in T-Shirts)
  PASS: Zero stainless steel mugs/bottles misclassified into apparel

======================================================================
FINAL RESULT: 8/8 CHECKS PASSED
STATUS: ALL REQUIREMENTS FOR HƯNG (NGƯỜI 2) ARE FULLY SATISFIED!
======================================================================
```

---

## Phần 3: Kiểm tra Hạ tầng Lưu trữ MongoDB

Khởi tạo 6 khung bảng (Collections) và bộ chỉ mục tốc độ cao (Indexes) trên MongoDB Atlas database `vietcraft-seed`.

```bash
python app/core/init_seed_db.py
```

### 🎯 Expected Output:
```text
=== Khởi tạo khung chứa dữ liệu rỗng (Collections & Indexes) trên MongoDB: mongodb+srv://... (DB: vietcraft-seed) ===
✓ Kết nối MongoDB thành công.

✓ Đã khởi tạo sẵn 6 collections rỗng & bộ chỉ mục (Indexes) chờ lưu kết quả AI:
  - Khung bảng model_run         : 3 indexes (_id_, run_id_1, model_name_1_started_at_1)
  - Khung bảng forecast_point    : 3 indexes (_id_, entity_type_1_entity_id_1_forecast_date_1, run_id_1)
  - Khung bảng seasonal_profile  : 3 indexes (_id_, entity_type_1_entity_id_1_period_type_1_period_value_1, run_id_1)
  - Khung bảng anomaly_event     : 3 indexes (_id_, entity_type_1_entity_id_1_event_date_1, severity_1)
  - Khung bảng niche_score       : 2 indexes (_id_, keyword_1_date_1)
  - Khung bảng listing_health    : 2 indexes (_id_, listing_id_1_date_1)

✅ Khởi tạo khung lưu trữ DB (Task 22) thành công. Sẵn sàng lưu kết quả khi các model AI chạy.
```

---

## Phần 4: Kiểm tra Tầng Truy xuất & Ghi dữ liệu

Kiểm tra khả năng đọc dữ liệu Master Data từ MongoDB (`loader.py`) và khả năng ghi kết quả dự báo có gắn metadata chuẩn hóa (`writer.py`).

```bash
python app/core/loader.py && python app/core/writer.py
```

### 🎯 Expected Output:
```text
=== TỰ KIỂM TRA MODULE LOADER.PY ===
✓ get_active_keywords: 40 từ khoá chuẩn
✓ get_categories: 85 danh mục
✓ get_tags: 77 tags
✓ get_tag_keyword_mapping: 118 mappings
✓ get_catalog_info: 138 loại sản phẩm
✓ get_shops: 80 shops
✓ get_listings: 5000 listings
✅ TẤT CẢ SELF-CHECKS CỦA LOADER.PY ĐÃ PASS!

=== TỰ KIỂM TRA HÀM GHI DỮ LIỆU MẪU (WRITER.PY SELF-CHECK) ===
✓ start_model_run sinh run_id mẫu: run_sample_test_model_...
✓ save_forecast_points ghi thành công dữ liệu mẫu: 1 điểm
✓ finish_model_run cập nhật trạng thái hoàn thành mẫu thành công
✅ TẤT CẢ SELF-CHECKS CỦA WRITER.PY ĐÃ PASS!
```

---

## Phần 5: Kiểm tra Các Thuật toán AI Lõi

Kiểm tra 3 thuật toán nền tảng:
- `calendar_vn.py`: Xử lý lịch Tết Nguyên Đán và biến đổi trục `days_to_tet`.
- `stl_service.py`: Phân rã chuỗi thời gian STL Loess (Trend / Seasonal / Residual).
- `zscore_service.py`: Thuật toán Z-Score chống nhiễu phát hiện điểm bất thường.

```bash
python app/core/calendar_vn.py && python app/services/stl_service.py
```

### 🎯 Expected Output:
```text
=== TỰ KIỂM TRA MODULE CALENDAR_VN.PY ===
✓ Kiểm tra days_to_tet: Chính xác 100% trên các mốc thực tế.
✓ Đỉnh mùa vụ sau khi đổi trục: ngày -14 (trước Tết ~2 tuần)
✅ TẤT CẢ SELF-CHECKS CỦA CALENDAR_VN.PY ĐÃ PASS!

=== TỰ KIỂM TRA MODULE STL_SERVICE.PY (LOESS) ===
✓ Độ lệch tái cấu trúc (Trend + Seasonal + Resid vs Data): 0.000124
✅ TẤT CẢ SELF-CHECKS CỦA STL_SERVICE.PY ĐÃ PASS!
```

---

## Phần 6: Chạy Nghiên cứu Mốc Baseline & M5 Benchmark

Chạy bộ đo lường sai số mốc cho 40 từ khóa Google Trends và xuất báo cáo khoa học M5 Aggregation Benchmark:

```bash
python app/core/compute_baselines.py \
  && python app/core/benchmark_m5.py \
  && python app/core/verify_trends_freq.py
```

### 🎯 Expected Output:
```text
=== Đang tính Baselines cho 40 từ khoá chuẩn ===
✓ Đã lưu bảng baselines thành công vào: app/data/baselines.json
✅ Hoàn thành Task 23 / Task 7!

=== Đang chạy thử nghiệm M5 Aggregation Benchmark ===
✓ Đã ghi báo cáo nghiên cứu M5 ra: docs/qc/m5_aggregation.md
✅ Hoàn thành Task 19 / Task 3!

=== Kiểm tra tần suất Trends cho 40 từ khoá chuẩn ===
✓ Đã xuất báo cáo QC ra: docs/qc/trends_freq.md
✅ Hoàn thành Task 25 / Task 9!
```

---

## Phần 7: Kiểm tra Tính Toàn vẹn Liên kết Dữ liệu 5 Thành viên

Kiểm tra liên kết tham chiếu (Foreign keys / Key constraint integrity) giữa các phân hệ do 5 thành viên tạo ra:

```bash
python app/seed/verify_integration_5_members.py
```

### 🎯 Expected Output:
```text
=== Đang chạy kiểm tra toàn vẹn liên kết 5 người ===
  [ĐẠT                      ] Mọi sản phẩm thuộc shop có thật (Shops <-> Listings) -> 0 sản phẩm mồ côi / 5000 listings
  [ĐẠT                      ] Mọi biến thể thuộc sản phẩm có thật (Listings <-> Variants) -> 0 biến thể mồ côi / 39920 variants
  [PENDING (CHỜ HIẾU TASK 58)] Mọi đơn hàng gắn với người mua và sản phẩm có thật (Orders) -> Chưa có file orders.csv / order_items.csv
  [PENDING (CHỜ HIẾU TASK 59)] Mọi đánh giá gắn với đơn đã nhận thành công (Reviews) -> Chưa có file reviews.csv
  [PENDING (CHỜ HIẾU TASK 60)] Mọi dòng thống kê ngày có sản phẩm tương ứng (Listing Daily) -> Chưa có file listing_daily.csv
  [ĐẠT                      ] Mọi tag trên sản phẩm có trong danh sách chuẩn (Tags <-> Listings) -> 0 tag lạ không nằm trong tags.csv của Nhi
✓ Đã xuất báo cáo Integration QC ra: docs/qc/integration_qc.md
```

---

## Phần 8: Khởi chạy & Verify Web API Server (FastAPI)

### 8.1. Khởi chạy Web Server
```bash
python app/main.py
```
Hoặc dùng uvicorn trực tiếp:
```bash
uvicorn app.main:app --reload --port 8000
```

### 8.2. Verify các Endpoint API:

1. **Health Check Endpoint**:
   - URL: `http://localhost:8000/health`
   - Phản hồi: `{"status": "ok", "service": "ai-analytics"}`
2. **Trang Swagger UI tương tác**:
   - URL: `http://localhost:8000/docs`
3. **OpenAPI Schema Specification**:
   - URL: `http://localhost:8000/api/v1/openapi.json`

---

## 🚀 Lệnh Chạy Toàn Bộ Test Suite Trong 1 Dòng (One-Liner)

Để kiểm tra nhanh 100% tính đúng đắn của toàn hệ thống trước khi push code hoặc báo cáo:

```bash
cd_to_your_dir/ && .venv/bin/python app/seed/catalog/verify_tags.py && .venv/bin/python app/seed/catalog/verify_catalog.py && .venv/bin/python app/core/init_seed_db.py && .venv/bin/python app/core/loader.py && .venv/bin/python app/core/writer.py && .venv/bin/python app/core/calendar_vn.py && .venv/bin/python app/services/stl_service.py && .venv/bin/python app/core/compute_baselines.py && .venv/bin/python app/core/benchmark_m5.py && .venv/bin/python app/core/verify_trends_freq.py && .venv/bin/python app/seed/verify_integration_5_members.py
```
