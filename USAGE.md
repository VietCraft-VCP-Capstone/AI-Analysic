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
11. [Phần 9: Kiểm Khung API, Hợp đồng Mart & Dựng lại Mart](#phần-9-kiểm-khung-api--hợp-đồng-mart)
12. [Phần 10: Sửa và mở rộng một tính năng (F26–F41)](#phần-10-sửa-và-mở-rộng-một-tính-năng-f26f41)
13. [🚀 Lệnh Chạy Toàn Bộ Test Suite Trong 1 Dòng (One-Liner)](#-lệnh-chạy-toàn-bộ-test-suite-trong-1-dòng-one-liner)

---

## 1. Chuẩn bị Môi trường & Biến Môi trường

Trước khi thực hiện bất kỳ lệnh kiểm thử nào, hãy đảm bảo bạn đang ở thư mục `AI-Analysic` và đã kích hoạt Virtual Environment.

```bash
cd <thư-mục-bạn-clone>/vc-ai/AI-Analysic

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

**Đứng ở thư mục `AI-Analysic/`, KHÔNG phải `AI-Analysic/app/`.**
`app.main:app` đọc là *"vào thư mục `app`, lấy file `main.py`"* — đã đứng sẵn trong
`app/` thì Python không tìm thấy `app` bên trong `app` nữa, và báo
`ModuleNotFoundError: No module named 'app'`.

```bash
cd AI-Analysic
source .venv/bin/activate
uvicorn app.main:app --reload
```

Không cần MongoDB, không cần `app/.env` để khởi động.

Khởi động xong sẽ in ra tình trạng 16 tính năng:

```text
[F26-F41] 0 tinh nang chay that: (chua co)
[F26-F41] 16 con la khung, tra 503 mart_not_ready: F26, F27, ... F41
```

Dòng này là **bảng điều khiển tiến độ**: mỗi lần có người cắm tính năng thật vào,
số bên trái tăng. Cách cắm ghi ở đầu `app/api/v1/analytics_routes.py`.

### 8.2. Verify các Endpoint hạ tầng

1. **Health Check**: `http://localhost:8000/health` → `{"status":"ok","service":"ai-analytics"}`
2. **Swagger UI**: `http://localhost:8000/docs` — 19 đường dẫn, nhóm theo `F26 · Hiếu`, `F34 · Đạt`…
3. **OpenAPI Schema**: `http://localhost:8000/api/v1/openapi.json`

### 8.3. Verify 16 endpoint phân tích F26–F41

**Cả 16 endpoint đều trả dữ liệu thật.** Không còn cái nào là khung.

> **Mọi endpoint sẽ trả `401 unauthorized` nếu chưa bật cờ dev.** Đó là ĐÚNG.
>
> API chỉ cho người bán xem dữ liệu shop của chính mình (`BR-174`, `BR-177`), nên
> `shop_id` **luôn lấy từ JWT**, không nhận từ query. Mà phần giải mã JWT là
> **SPEC-04 (Nhi), chưa xong** — chưa có thuật toán ký, khoá, và tên trường shop
> từ repo sàn. Chưa có mấy thứ đó thì **không tồn tại token hợp lệ nào**.

#### Cách 1 — tắt hẳn xác thực (dùng khi đang viết tính năng)

```bash
DEV_SHOP_ID=shp_00017 uvicorn app.main:app --reload
```

Xong. Mở Swagger bấm **Execute** thẳng, không cần token, không cần điền header gì cả.
Mọi request được coi là của shop `shp_00017`.

Server in cảnh báo to lúc khởi động để không ai quên là đang bật:

```text
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
!!  XAC THUC DANG TAT HOAN TOAN — moi request thanh shop `shp_00017` (DEV_SHOP_ID)
!!  Chi dung khi dang viet tinh nang. TAT truoc khi deploy hay demo:
!!  bo DEV_SHOP_ID / DEV_TRUST_SHOP_HEADER khoi .env va moi truong.
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
```

Tiện thì đặt luôn vào `app/.env` (đã có dòng mẫu trong `.env.example`).

#### Cách 2 — đổi shop giữa các request

Dùng khi cần thử `BR-174`/`BR-177`: *shop A có xem được dữ liệu shop B không.*
**Header thắng `DEV_SHOP_ID`**, nên đặt sẵn `DEV_SHOP_ID` trong `.env` vẫn đổi được:

```bash
curl -s -H "X-Debug-Shop-Id: shp_00025" \
  http://localhost:8000/api/analytics/tag-gap
```

#### 🎯 Expected Output — bảng nghiệm thu 16 endpoint

Đo thật ngày 21/09/2026, shop `shp_00017`:

| F | Đường dẫn | ms | Trả về |
|---|---|---|---|
| F26 | `GET /api/analytics/shop/overview` | 237 | 4.714 lượt xem · 158 đơn · 34.475.000đ · CR 3,35% |
| F27 | `GET /api/analytics/listings/{id}/timeseries` | 400 | chuỗi 30 ngày + trung vị danh mục + độ dốc hồi quy |
| F28 | `GET /api/analytics/listings/{id}/conversion` | 256 | phễu xem→giỏ→mua, khâu yếu nhất |
| F29 | `GET /api/analytics/listings/{id}/health` | 254 | điểm 75.0 · dải `cần cải thiện` · breakdown 5 trục |
| F30 | `GET /api/notifications/alerts` | 422 | cảnh báo z-score, ngưỡng \|z\| > 7.0 |
| F31 | `GET /api/analytics/shop/categories/revenue` | 533 | 95 loại hàng + heatmap 156 ô giờ Việt Nam |
| F32 | `GET /api/analytics/competitors` | 368 | top 20 đối thủ + phân vị giá/sao của mình |
| F33 | `GET /api/analytics/shop-comparison` | 539 | radar 5 trục vs 5 shop mạnh nhất phân khúc |
| F34 | `GET /api/analytics/tag-gap` | 441 | tag đối thủ dẫn đầu có mà mình chưa có |
| F35 | `GET /api/analytics/pricing` | 254 | phân bố giá p10–p90 của nhóm bán chạy |
| F36 | `GET·POST·DELETE /api/analytics/competitor-tracking` | 344 | theo dõi tối đa 10 shop |
| F37 | `GET /api/analytics/forecast/revenue` | 257 | 30/60/90 ngày · ARIMA MASE 0,83 vs mốc 1,10 |
| F38 | `GET /api/analytics/forecast/seasonal` | 254 | "quà tết" đỉnh tuần 1 → tung hàng 23/11–14/12 |
| F39 | `GET /api/analytics/forecast/niches` | 168 | "áo đồng phục" cầu 97,7% / cung 13,6% |
| F40 | `GET /api/analytics/forecast/radar` | 176 | 10 tag tăng nhanh nhất |
| F41 | `GET /api/analytics/forecast/recommendations` | 269 | tối đa 5 khuyến nghị, đã cá nhân hoá |

**14/16 dưới mục tiêu p95 < 500ms.** F31 và F33 còn vượt chút — cách sửa ghi ở mục 9.4.

Ba mã cần phân biệt:

| Mã | Nghĩa |
|---|---|
| `401 unauthorized` | Chưa bật `DEV_SHOP_ID` hay `DEV_TRUST_SHOP_HEADER` — **mặc định là mã này** |
| `501 jwt_not_configured` | Có gửi token nhưng SPEC-04 chưa xong nên chưa giải mã được |
| `503 mart_not_ready` | Bảng mart rỗng — **chạy `build_marts` (mục 9.3) là hết** |

> ⚠️ `DEV_SHOP_ID` **không bao giờ** được bật ở môi trường có dữ liệu thật: bật lên là
> ai cũng tự xưng shop nào cũng được. Nhi xong SPEC-04 thì điền vào hàm
> `decode_shop_id()` trong `app/api/v1/_template.py` — đúng một hàm, 16 endpoint
> không phải sửa dòng nào — rồi xoá cửa hậu này.

### 8.4. Endpoint đã bị GỠ

`POST /api/v1/forecasting/` trả **404**. Đúng như vậy (task `API-99`).

Nó từng phục vụ `LSTMModelService`, mà `app/models/lstm_model.py` là mạng LSTM **chưa
train** — và vì `torch` không nằm trong `requirements.txt`, nó luôn rơi vào nhánh dự
phòng: kéo một đường thẳng qua hai điểm đầu-cuối rồi trả về như thể là dự báo. Số
trông rất hợp lý mà không có căn cứ nào. Ai mở `/docs` bấm thử — kể cả hội đồng — đều
nhận được số đó.

Thay bằng **F37** `GET /api/analytics/forecast/revenue`, đọc mart `forecast_point` do
job chạy đêm ghi, kèm dải `lo95`/`hi95` (`BR-206`, `BR-207`).

---

## Phần 9: Kiểm Khung API, Hợp đồng Mart & Dựng lại Mart

Hai script này **không cần MongoDB**, chạy trong vài giây.

### 9.1. Khung API có khớp hợp đồng không

```bash
python tests/test_api_contract.py
```

Kiểm 11 điều: đủ 16 mã tính năng · bảng endpoint trong code khớp `docs/API_CONTRACT.md`
· mọi endpoint đều sống · chưa có mart thì 503 đúng tên bảng · không token thì 401 ·
không endpoint nào nhận `shopId` từ query · body lỗi không bọc trong `detail` · không
lọt traceback ra ngoài · vỏ phản hồi đủ 3 trường cổng ra · `insufficient_data` trả
`null` chứ không trả 0 · Swagger không còn endpoint mô hình chưa train.

#### 🎯 Expected Output:
```text
✅ 11/11 TEST PASS — khung API khớp hợp đồng
```

### 9.2. Dữ liệu trong bảng mart có đúng hợp đồng không

```bash
python scripts/validate_mart.py --all --offline     # không cần MongoDB
python scripts/validate_mart.py --all --sample 100  # đọc thật từ Atlas (CHỈ ĐỌC)
```

Kiểm mỗi bảng 5 thứ: đủ `run_id`/`model_version`/`computed_at` · đủ trường khoá và
không rỗng · không trùng khoá · đủ cột thân bắt buộc · cột lạ thì cảnh báo.

#### 🎯 Expected Output:
```text
  ✓ forecast_point         60 bản ghi, hợp lệ
  ✓ anomaly_event          60 bản ghi, hợp lệ
  ...
9/9 bảng đạt
✅ MỌI BẢNG ĐỀU KHỚP HỢP ĐỒNG
```

> **Bảng rỗng KHÔNG phải lỗi** — script báo `○ 0 bản ghi, schema hợp lệ`. Đó là
> trạng thái đúng khi chưa job nào chạy. Tạo dòng rỗng chỉ làm người đọc tưởng
> đã có dữ liệu.

---

### 9.3. Dựng lại toàn bộ mart — `build_marts.py`

**Đây là nửa còn lại của kiến trúc.** 16 endpoint chỉ ĐỌC mart; không job nào ghi
vào thì mọi endpoint trả `503 mart_not_ready` — đúng nhưng vô dụng.

```
ĐÊM:  build_marts.py  -> đọc listing_daily / listings / reviews / trend_interest
                       -> tính  -> ghi 9 bảng mart
NGÀY: 16 endpoint     -> chỉ đọc mart -> trả về (mục tiêu p95 < 500ms)
```

```bash
# Xem trước, KHÔNG ghi gì lên Atlas
python -m app.core.build_marts --all --dry-run

# Dựng tất cả
python -m app.core.build_marts --all

# Dựng lại một bảng
python -m app.core.build_marts mart_competitor
```

| Mart | Dòng | Nguồn | Phục vụ |
|---|---|---|---|
| `mart_competitor` | 5.000 | `listings` + `listing_daily` + `reviews` + `shops` | F32 F33 F34 F35 F36 F41 |
| `mart_listing_quality` | 3.254 | `listing_daily` (phễu 90 ngày) | F28 |
| `listing_health` | 3.254 | phễu + `reviews` + `listing_variants` | F29 |
| `anomaly_event` | 326 | `listing_daily` qua `zscore_service` | F30 |
| `mart_shop_hour` | 8.192 | `orders` + `order_items` + `listings` | F31 |
| `niche_score` | 44 | `trend_interest` (Google Trends THẬT) | F39 F41 |
| `mart_demand` | 75 | `trend_interest` + `tag_keyword_map` | F40 |
| `seasonal_profile` | 44 | `trend_interest` qua `stl_service` (STL Loess) | F38 |
| `forecast_point` | 7.200 | `listing_daily` cấp shop, ARIMA vs seasonal_naive | F37 |

Chạy cả 9 mất khoảng **3 phút**, phần lớn là `forecast_point` (fit ARIMA cho 80 shop).

> ⚠️ **Job này GHI lên cụm Atlas M0 512 MB DÙNG CHUNG CẢ NHÓM.** Toàn bộ 9 mart
> cộng lại khoảng **15 MB**, an toàn. Nhưng trước khi thêm mart mới thì đo:
> ```python
> sum(c[d].command("dbstats")["dataSize"] for d in
>     ["vietcraft-seed","data-collection","vietcraft"]) / 1048576
> ```
> Atlas tính bằng `dataSize` (chưa nén), KHÔNG phải `storageSize` — hai số lệch 3–4 lần.
> Và **đừng dựng bảng nhân đôi `listing_daily` 796.025 dòng** — đã thử 21/09, cụm
> vọt lên 526/512 MB và chặn ghi với TẤT CẢ mọi người. Xem `writer.BLOCKED`.

#### Ba quyết định đã đo, đừng đảo lại mà không đo lại

**1. Dò bất thường loại 43/80 shop.** Chuỗi doanh thu ngày của nhiều shop có tới
78% số ngày bằng 0; trên chuỗi như vậy mọi ngày CÓ bán đều thành "đột biến". Chạy
bừa cho **4.423 cảnh báo** (tỉ lệ 10%, gấp đôi `MAX_ANOMALY_RATE`). Thêm chặn
"cần ≥ 40% ngày có bán" → còn **326 cảnh báo**, tỉ lệ 1,6%. F30 nói rõ trong
`limitation` là shop bị loại **"chưa đo được"**, không phải "không có bất thường".

**2. `forecast_point` chỉ lưu MỘT chuỗi 90 ngày.** Khoá của bảng là
`(entity_type, entity_id, forecast_date)` — **không có `horizon_days`**. Ghi ba bản
30/60/90 cho cùng ngày thì chúng upsert đè lên nhau: **đã mất 7.200/14.400 dòng
trong im lặng**. API cắt cửa sổ lúc đọc, và đó là đúng về mô hình — ARIMA dự báo
90 bước cho ra đúng 30 giá trị đầu như khi dự báo 30 bước.

**3. Bảng so sánh mô hình nằm ở `model_run`, không lặp trên từng dòng.** Gắn khối
`validation` lên cả 7.200 dòng làm 46% dung lượng mart là bản sao y hệt nhau.
Đọc bằng:
```python
db.model_run.find_one({"model_name":"forecast_point"},
                      sort=[("started_at",-1)])["parameters"]["model_comparison"]
```

### 9.4. F31 và F33 còn vượt p95 < 500ms

Đo được 533ms và 539ms. Nguyên nhân là độ trễ mạng tới Atlas (~90ms mỗi lượt
đi-về) cộng với M0 free tier bóp CPU. Cách sửa: thêm một mart gộp ở độ mịn
`(shop_id, date)` — 80 shop × ~550 ngày = **44.000 dòng** thay vì quét
796.025 — đúng như `writer.BLOCKED` đã gợi ý. Chưa ai nhận việc này.

---

## Phần 10: Sửa và mở rộng một tính năng (F26–F41)

> **Cả 16 endpoint đã chạy và trả dữ liệu thật.** Phần này dành cho người tiếp
> nhận: sửa một tính năng, đổi công thức, hoặc thêm trường vào phản hồi.

### 10.1. Tìm file của mình

Mỗi tính năng một file, không ai đụng của ai:

```
app/api/v1/f26_shop_overview.py        F26  Hiếu
app/api/v1/f27_listing_timeseries.py   F27  Hiếu
app/api/v1/f28_conversion.py           F28  Hạt
app/api/v1/f29_health.py               F29  Hạt
app/api/v1/f30_alerts.py               F30  Hiếu
app/api/v1/f31_category_revenue.py     F31  Hiếu
app/api/v1/f32_competitors.py          F32  Nhi
app/api/v1/f33_shop_comparison.py      F33  Nhi
app/api/v1/f34_tag_gap.py              F34  Đạt
app/api/v1/f35_pricing.py              F35  Nhi
app/api/v1/f36_competitor_tracking.py  F36  Đạt   <- endpoint DUY NHẤT có ghi
app/api/v1/f37_forecast_revenue.py     F37  Đạt
app/api/v1/f38_seasonal.py             F38  Hưng
app/api/v1/f39_niches.py               F39  Hưng
app/api/v1/f40_radar.py                F40  Hưng
app/api/v1/f41_recommendations.py      F41  Đạt
```

Bảng đăng ký nằm ở `DA_LAM` trong `app/api/v1/analytics_routes.py` — thêm tính
năng mới thì thêm **một dòng** ở đó.

Ba file nền dùng chung, **sửa là ảnh hưởng cả 16**:

| File | Là gì |
|---|---|
| `_template.py` | vỏ `{data, meta, error}`, `ok/partial/insufficient`, 4 hàm lỗi, xác thực |
| `_mart.py` | kết nối MongoDB dùng chung, cửa sổ thời gian, `ty_le_chuyen_doi`, `tien` |
| `analytics_routes.py` | bảng 16 đường dẫn + cơ chế đăng ký |

### 10.2. Công thức nằm ở đâu

**Endpoint không tính toán.** Mọi phép tính nằm trong job:

| Muốn đổi | Sửa ở |
|---|---|
| Cách tính `est_sales_90d`, hạng trong danh mục, co ngót điểm sao | `build_marts.build_mart_competitor` |
| Trọng số 5 trục điểm sức khoẻ | `build_marts.TRONG_SO` |
| Ngưỡng dò bất thường, chặn chuỗi thưa | `build_marts.TOI_THIEU_NGAY_CO_BAN`, `zscore_service.DEFAULT_THRESHOLD` |
| Mô hình dự báo | `build_marts.build_forecast_point` |
| Cách chọn ngách | `build_marts.build_niche_score` |

Sửa xong thì **chạy lại job**, không chỉ sửa endpoint:
```bash
python -m app.core.build_marts <tên_mart>
python scripts/validate_mart.py <tên_mart>
```

### 10.3. Bốn hàm phản hồi, hết

| Hàm | Khi nào gọi | Trả ra |
|---|---|---|
| `ok(data, meta)` | Có số, tin được | `200` · `meta.status = "ok"` |
| `partial(data, reason, meta)` | Có số nhưng độ tin cậy thấp | `200` · `meta.status = "partial"` |
| `insufficient(reason, meta)` | Chưa đủ dữ liệu để tính | `200` · `data: null` |
| `mart_not_ready("tên_bảng")` | Bảng rỗng, chưa job nào ghi | `503` |

Thêm `invalid_param(field)` → `400`, `forbidden()` → `403`, `not_found()` → `404`.

**Đừng tự `return {...}` hay tự `raise HTTPException`.** Gọi mấy hàm này thì khối
`meta` và body lỗi tự đúng hợp đồng; tự viết thì sớm muộn lệch và test sẽ đỏ.

### 10.4. Sáu cái bẫy — đều đã mắc phải thật

**1. THIẾU ≠ 0.** Chưa đủ dữ liệu thì `insufficient(...)`, không `return {"revenue_vnd": 0}`.
Shop mới nhìn thấy *"doanh thu 0đ"* thay vì *"chưa đủ dữ liệu"* là lỗi nặng nhất
của loại dashboard này. Test `test_thieu_khac_khong` canh chỗ này.

**2. Mốc thời gian lấy từ DỮ LIỆU, không phải hôm nay.** Dữ liệu mồi dừng ở
2026-08-30. Lấy `date.today()` làm mốc thì cửa sổ 30 ngày rơi vào vùng trống và
mọi KPI ra 0 — cũng là lỗi THIẾU ≠ 0, chỉ ở tầng chọn thời gian. Dùng
`_mart.ngay_moi_nhat()`.

**3. Đừng lấy giờ hiện tại làm `computed_at`.** Dùng `meta_from_record(doc, ...)`
để lấy xuất xứ **từ chính bản ghi mart**. Số có thể đã tính từ hôm kia.

**4. `shop_id` chỉ đến từ `CurrentShop`.** Đừng thêm tham số `shopId` vào query —
ai cũng đổi được thành shop người khác (`BR-174`, `BR-177`). Có test canh.

**5. Tiền là số nguyên VND.** `sum()` trên dữ liệu có `float` ra `244000.0`. Dùng
`_mart.tien()`. Tên trường kết thúc `_vnd`.

**6. % tính trên nền gần 0 là vô nghĩa.** 1,3 → 3,9 trên thang 0–100 ra "tăng
200%", nghe như bùng nổ nhưng là nhiễu. Đặt ngưỡng nền rồi trả `null` kèm cờ,
đừng trả một con số ai cũng tin nhầm. Xem `build_marts.NEN_TOI_THIEU`.

### 10.5. Bốn chỗ CỐ Ý không có số — đừng "sửa" bằng cách điền vào

| Chỗ | Vì sao để null |
|---|---|
| `mart_demand.searches_per_week` | Google Trends trả **chỉ số 0–100**, không phải lượt tìm tuyệt đối. Quy đổi là bịa. `BR-213` (ngưỡng 100 lượt/tuần) vì vậy **chưa áp dụng được** |
| `forecast_point` → `lstm_mase` | SPEC-03 chưa chốt làm LSTM hay không. Xem `docs/ADR-002.md` |
| F34 `signal.has_signal = false` | Tag trong dữ liệu mồi gán **ngẫu nhiên**; đã tính cả hiệu ứng thử nhiều lần |
| F41 `validated: false` | Chưa chạy backtest khuyến nghị. Mốc bắt buộc là *"cứ làm tiếp thứ đang bán chạy nhất"* |

Trong `listing_health`, trục thiếu dữ liệu bị **loại khỏi phép tính rồi chia lại
trọng số**, không cho 0 điểm — thiếu dữ liệu khác với kém.

### 10.6. Xong một thay đổi là khi nào

```bash
python tests/test_api_contract.py              # 12/12
python scripts/validate_mart.py --all --offline
```

Và gọi thật endpoint của mình trên `http://localhost:8000/docs`, thấy số đúng.

---

## 🚀 Lệnh Chạy Toàn Bộ Test Suite Trong 1 Dòng (One-Liner)

Đứng ở thư mục `AI-Analysic/`.

**Không cần MongoDB** — chạy được ngay sau khi clone, vài giây:

```bash
.venv/bin/python tests/test_api_contract.py \
  && .venv/bin/python scripts/validate_mart.py --all --offline \
  && .venv/bin/python app/api/v1/_template.py \
  && .venv/bin/python app/api/v1/analytics_routes.py \
  && .venv/bin/python app/core/calendar_vn.py \
  && .venv/bin/python app/services/stl_service.py
```

**Dựng lại toàn bộ mart** (cần MongoDB, ~3 phút):

```bash
.venv/bin/python -m app.core.build_marts --all \
  && .venv/bin/python scripts/validate_mart.py --all --sample 100
```

**Cần MongoDB** (`app/.env` đã có `MONGODB_URI`) — chạy trước khi tạo Pull Request:

```bash
.venv/bin/python app/seed/catalog/verify_tags.py \
  && .venv/bin/python app/seed/catalog/verify_catalog.py \
  && .venv/bin/python app/core/init_seed_db.py \
  && .venv/bin/python app/core/loader.py \
  && .venv/bin/python app/core/writer.py \
  && .venv/bin/python app/core/compute_baselines.py \
  && .venv/bin/python app/core/benchmark_m5.py \
  && .venv/bin/python app/core/verify_trends_freq.py \
  && .venv/bin/python app/seed/verify_integration_5_members.py
```
