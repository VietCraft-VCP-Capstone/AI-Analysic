# Hướng dẫn Cài đặt & Chạy — VietCraft AI Analytics

> Từ máy trắng đến 16 endpoint trả dữ liệu thật.
> **Một lệnh: `python run.py`** — Windows, macOS, Linux như nhau.
> Mọi lệnh đứng ở thư mục `AI-Analysic/`, **không phải `AI-Analysic/app/`**.

---

## 1. Chạy bằng một lệnh — Windows, macOS, Linux như nhau

```bash
git clone <repo>
cd AI-Analysic
python run.py
```

Windows dùng `python`, Linux/macOS thường là `python3` — chỉ khác đúng chỗ đó.
Không cần `source .venv/bin/activate`, không cần nhớ thứ tự bước nào trước bước nào.

`run.py` làm 6 việc, **mỗi việc tự kiểm "đã xong chưa" rồi mới làm**:

| Bước | Làm gì | Chạy lại lần 2 |
|---|---|---|
| 1 | Kiểm Python >= 3.10 | tức thì |
| 2 | Tạo `.venv`, cài `requirements.txt` | bỏ qua |
| 3 | Tạo `app/.env` từ `.env.example` | bỏ qua |
| 4 | Dựng 9 bảng mart nếu còn rỗng | bỏ qua |
| 5 | Chạy 12 test hợp đồng + kiểm 9 mart | ~15 giây |
| 6 | Bật server, mở được `/docs` | |

**Chạy đi chạy lại bao nhiêu lần cũng được.** Lần đầu ~5 phút (cài thư viện +
dựng dữ liệu), lần sau ~20 giây vì mọi thứ đã xong đều bị bỏ qua.

### Sẽ dừng ở bước 3 lần đầu — đúng như vậy

Lần đầu chạy, `run.py` tạo `app/.env` rồi **dừng lại** báo:

```
[LOI]  app/.env chua co MONGODB_URI that
       Mo file nay ra va dien chuoi ket noi Atlas:
         .../AI-Analysic/app/.env
```

Mở file đó, điền `MONGODB_URI` (xin từ người giữ Atlas), rồi chạy `python run.py`
lại. Nó nhớ những gì đã cài, đi tiếp từ bước 4.

> Script kiểm **giá trị thật**, không chỉ kiểm dòng có tồn tại — bản mẫu cũng có
> dòng `MONGODB_URI` nhưng giá trị là `<user>:<password>`, điền vậy vẫn hỏng.

### Các kiểu chạy khác

```bash
python run.py --check         # chỉ kiểm, không cài gì, không bật server
python run.py --setup-only    # cài xong thì dừng
python run.py --rebuild       # dựng LẠI toàn bộ mart (GHI lên Atlas dùng chung)
python run.py --port 8080     # đổi cổng
python run.py --no-dev-auth   # KHÔNG tắt xác thực (mọi endpoint trả 401)
```

### Đọc banner lúc khởi động

```
======================================================================
  VietCraft AI Analytics  ·  16/16 tinh nang co code that
----------------------------------------------------------------------
  [OK] Ca 9 bang mart deu co du lieu. Goi API la ra so.
----------------------------------------------------------------------
  [!!] XAC THUC DANG TAT HOAN TOAN — moi request thanh shop `shp_00017`
       Chi dung khi dang viet tinh nang. TAT truoc khi deploy hay demo.
======================================================================
```

Ba dòng, đọc từ trên xuống:

| Dòng | Nói gì |
|---|---|
| `16/16 tinh nang co code that` | Có code thật, **không còn khung rỗng**. Nhưng **chưa nói gì về dữ liệu** |
| `[OK] Ca 9 bang mart deu co du lieu` | Gọi API là ra số. Nếu thấy `[!] ... CON RONG` thì chạy `python run.py` để dựng |
| `[!!] XAC THUC DANG TAT` | Cửa hậu đang bật — tiện lúc code, **phải tắt trước khi demo** |

> Bản trước chỉ in `16 tinh nang chay that` rồi hết. Câu đó đúng về code nhưng gây
> hiểu nhầm: **có code không có nghĩa là gọi ra số**. Chưa dựng mart thì cả 16 đều
> trả `503` mà log vẫn khoe "chạy thật". Nay banner kiểm mart và nói rõ.

---

## 2. Cài thủ công — khi cần hiểu từng bước

`run.py` chỉ gói mấy lệnh này lại:

```bash
# 1. Môi trường ảo
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 2. Cấu hình — rồi mở app/.env điền MONGODB_URI
cp .env.example app/.env         # Windows: copy .env.example app\.env

# 3. Dựng dữ liệu cho API đọc (~3 phút, GHI lên Atlas dùng chung ~15MB)
python -m app.core.build_marts --all --dry-run    # xem trước
python -m app.core.build_marts --all              # dựng thật

# 4. Bật server
DEV_SHOP_ID=shp_00017 uvicorn app.main:app --reload
#   Windows PowerShell:  $env:DEV_SHOP_ID="shp_00017"; uvicorn app.main:app --reload
#   Windows CMD:         set DEV_SHOP_ID=shp_00017 && uvicorn app.main:app --reload
```

Mở **http://localhost:8000/docs** → **Try it out** → **Execute**.

> **Đứng ở `AI-Analysic/`, không phải `AI-Analysic/app/`.** `app.main:app` đọc là
> *"vào thư mục `app`, lấy `main.py`"* — đã ở trong `app/` rồi thì Python không tìm
> thấy `app` bên trong `app`, và báo `ModuleNotFoundError: No module named 'app'`.

### Vì sao cần `DEV_SHOP_ID`

API chỉ cho người bán xem dữ liệu shop của chính mình (`BR-174`, `BR-177`), nên
`shop_id` **luôn lấy từ token**, không nhận từ query. Phần giải mã token là
**SPEC-04, chưa xong** — hiện **không tồn tại token hợp lệ nào**.

`DEV_SHOP_ID` là cửa hậu chỉ dành cho lúc phát triển: bỏ kiểm tra quyền, coi mọi
request là của shop đó. Nhờ nó mà **không ai phải chờ ai**.

> **TẮT trước khi demo.** Bật lên là ai cũng tự xưng shop nào cũng được.
> SPEC-04 xong thì điền vào `decode_shop_id()` trong `app/api/v1/_template.py`
> — **một hàm, 16 endpoint không phải sửa dòng nào** — rồi xoá cửa hậu này.

Đổi shop giữa các request (thử `BR-174`: shop A xem trộm shop B được không).
**Header thắng `DEV_SHOP_ID`**:

```bash
curl -s -H "X-Debug-Shop-Id: shp_00025" http://localhost:8000/api/analytics/tag-gap
```

### Đường CHẠY THẬT: sàn gọi qua cổng BE, không ai cần `DEV_SHOP_ID`

`DEV_SHOP_ID` chỉ để chạy thử một mình. Khi ghép với sàn, **FE không gọi thẳng service
này** — nó gọi BE, BE mới gọi sang đây:

```
FE React  ──JWT của sàn──▶  BE Node  ──X-Gateway-Secret + X-Shop-Id──▶  service AI
           /api/seller/analytics/*                                      /api/analytics/*
```

BE làm ba việc mà service này không làm được: kiểm JWT của sàn, kiểm vai trò `seller`,
và tra `shop` của người đăng nhập. Xong mới gửi sang đây kèm hai header:

| Header | Là gì |
|---|---|
| `X-Gateway-Secret` | bí mật dùng chung, phải trùng `AI_GATEWAY_SECRET` hai bên |
| `X-Shop-Id` | shop mà **BE đã xác thực**. Service này tin, vì đã tin secret |

Nhờ vậy service AI **không cần biết khoá ký JWT của sàn** — một bí mật, một chỗ đổi,
và `SPEC-04` không còn chặn việc ghép với sàn.

**Cấu hình:** sinh một chuỗi rồi đặt vào **cả hai** file:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
# -> dán vào app/.env       (AI_GATEWAY_SECRET=...)  ở repo này
# -> dán vào BE/.env        (AI_GATEWAY_SECRET=...)  ở repo sàn, GIỐNG HỆT
```

Banner khởi động nói rõ đang bật hay tắt:

```
[OK] Gateway BE san: BAT (AI_GATEWAY_SECRET). BE goi kem X-Shop-Id da xac thuc.
[!]  Gateway BE san: TAT. Dat AI_GATEWAY_SECRET giong ben BE de san goi duoc.
```

Thử tay:

```bash
curl -s -H "X-Gateway-Secret: <bi-mat>" -H "X-Shop-Id: shp_00017" \
  http://localhost:8000/api/analytics/shop/overview
```

Secret sai thì **`401` ngay**, không rơi xuống nhánh `DEV_SHOP_ID` — gửi header gateway
mà sai secret là đang mạo danh BE, không phải đang chạy thử.

> Phía sàn: `AI_DEMO_SHOP_ID=shp_00017` trong `BE/.env` bật **chế độ shop mẫu** — mọi
> người bán xem số liệu của shop mẫu trong dữ liệu mồi, và giao diện hiện nhãn
> *"Đang xem gian hàng mẫu"*. Bỏ trống biến đó thì BE gửi `shop_id` thật của người bán.
> Dữ liệu mồi **không bao giờ** được trình bày như số liệu của shop thật.

---

## 3. Bốn mã trả về cần phân biệt

| Mã | Nghĩa | Làm gì |
|---|---|---|
| `200` + `meta.status: ok` | Có số thật | — |
| `200` + `meta.status: insufficient_data` | Đã tính, shop này chưa đủ dữ liệu. `data: null`, **không phải 0** | — |
| `401 unauthorized` | Chưa bật `DEV_SHOP_ID`, hoặc `X-Gateway-Secret` sai | thêm biến đó, hoặc đặt `AI_GATEWAY_SECRET` giống bên BE |
| `503 mart_not_ready` | Bảng mart rỗng | chạy `build_marts --all` (mục 2.1) |

`501 jwt_not_configured` — có gửi token nhưng SPEC-04 chưa xong. Dùng `DEV_SHOP_ID`.

---

## 4. Kiểm mọi thứ còn đúng

**Không cần MongoDB**, vài giây:

```bash
python tests/test_api_contract.py               # 12/12
python scripts/validate_mart.py --all --offline # 9/9
python app/api/v1/_template.py
python app/api/v1/_mart.py
python app/core/calendar_vn.py
python app/services/stl_service.py
```

**Cần MongoDB** — chạy trước khi mở Pull Request:

```bash
python scripts/validate_mart.py --all --sample 100   # CHỈ ĐỌC
python app/core/loader.py
python app/core/writer.py
```

---

## 5. Bảng 16 endpoint

Đo thật 21/09/2026, shop `shp_00017`. **16/16 dưới mục tiêu p95 500ms.**

| F | Đường dẫn | ms | Trả về |
|---|---|---|---|
| F26 | `GET /api/analytics/shop/overview` | 237 | 4.714 lượt xem · 158 đơn · 34.475.000đ · CR 3,35% |
| F27 | `GET /api/analytics/listings/{id}/timeseries` | 400 | chuỗi 30 ngày + trung vị danh mục + độ dốc hồi quy |
| F28 | `GET /api/analytics/listings/{id}/conversion` | 256 | phễu xem→giỏ→mua, khâu yếu nhất |
| F29 | `GET /api/analytics/listings/{id}/health` | 254 | điểm 0-100, breakdown 5 trục |
| F30 | `GET /api/notifications/alerts` | 422 | cảnh báo z-score, ngưỡng \|z\| > 7.0 |
| F31 | `GET /api/analytics/shop/categories/revenue` | 448 | 95 loại hàng + heatmap giờ Việt Nam |
| F32 | `GET /api/analytics/competitors` | 368 | top 20 đối thủ + phân vị giá/sao của mình |
| F33 | `GET /api/analytics/shop-comparison` | 465 | radar 5 trục vs 5 shop mạnh nhất |
| F34 | `GET /api/analytics/tag-gap` | 441 | tag đối thủ dẫn đầu có mà mình chưa có |
| F35 | `GET /api/analytics/pricing` | 254 | phân bố giá p10–p90 của nhóm bán chạy |
| F36 | `GET·POST·DELETE /api/analytics/competitor-tracking` | 344 | theo dõi tối đa 10 shop |
| F37 | `GET /api/analytics/forecast/revenue` | 257 | 30/60/90 ngày · ARIMA MASE 0,83 vs mốc 1,10 |
| F38 | `GET /api/analytics/forecast/seasonal` | 254 | "quà tết" đỉnh tuần 1 → tung hàng 23/11–14/12 |
| F39 | `GET /api/analytics/forecast/niches` | 168 | "áo đồng phục" cầu 97,7% / cung 13,6% |
| F40 | `GET /api/analytics/forecast/radar` | 176 | 10 tag tăng nhanh nhất |
| F41 | `GET /api/analytics/forecast/recommendations` | 269 | tối đa 5 khuyến nghị, đã cá nhân hoá |

Endpoint cũ `POST /api/v1/forecasting/` trả **404** — đã gỡ (`API-99`): nó phục vụ
LSTM chưa train, và vì `torch` không có trong `requirements.txt` nên luôn rơi vào
nhánh dự phòng kéo một đường thẳng rồi trả về như dự báo. Thay bằng **F37**.

---

## 6. Dữ liệu nằm ở đâu

**Lúc chạy thật, nguồn duy nhất là MongoDB.** CSV và file xuất ra **không bao giờ**
là đầu vào lúc chạy.

| Database | Chứa gì |
|---|---|
| `vietcraft-seed` | dữ liệu mồi + 9 bảng mart do `build_marts` ghi |
| `data-collection` | Google Trends — dữ liệu THẬT duy nhất, cron vẫn chạy |
| `vietcraft` | sàn live |

`app/data/` chỉ còn **hai file cấu hình** mà `config.py` nạp trực tiếp:
`seed_keywords.json` (44 từ khoá hạt giống) và `baselines.json`. **Không thay bằng
DB được** — chúng là tham số, không phải dữ liệu.

Bảy file CSV từng nằm ở đó (`categories`, `tags`, `tag_keyword_map`, `vc_setting`,
`vc_price_rule`, `vc_product_type`, `vc_catalog_variant`) **đã nạp hết lên
`vietcraft-seed`, khớp từng dòng**. Đọc chúng bằng `loader.py`, đừng đọc lại CSV.

> `vc-data/` là **ngoại lệ chỉ cho việc làm mô hình ngoại tuyến** — train, đo, chạy
> thử. **Không API nào được đọc từ đó.** Cách kéo: `plan/huong-dan/HUONG_DAN_CAI_DAT.md`.

---

## 7. Hỏng ở đâu thì làm gì

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `ModuleNotFoundError: No module named 'app'` | Đang đứng trong `AI-Analysic/app/` | `cd ..` |
| Mọi endpoint trả `401` | Chưa bật cờ dev | `DEV_SHOP_ID=shp_00017 uvicorn ...` |
| Mọi endpoint trả `503 mart_not_ready` | Chưa dựng mart | `python -m app.core.build_marts --all` |
| `address already in use` | Tiến trình cũ còn sống | `pkill -f "uvicorn app.main"` |
| `ServerSelectionTimeout` | `app/.env` thiếu hoặc sai `MONGODB_URI` | xin lại chuỗi kết nối |
| `MartWriteError` | Ghi sai hợp đồng mart | đọc thông báo — nó nói thiếu cột nào |

---

## 8. Sửa và mở rộng một tính năng

Mỗi tính năng một file, không ai đụng của ai:

```
app/api/v1/f26_shop_overview.py … f41_recommendations.py
```

Bảng đăng ký ở `DA_LAM` trong `app/api/v1/analytics_routes.py`.

Ba file nền dùng chung — **sửa là ảnh hưởng cả 16**:

| File | Là gì |
|---|---|
| `_template.py` | vỏ `{data, meta, error}`, `ok`/`partial`/`insufficient`, 4 hàm lỗi, xác thực |
| `_mart.py` | kết nối MongoDB dùng chung, cửa sổ thời gian, `ty_le_chuyen_doi`, `tien` |
| `analytics_routes.py` | bảng 16 đường dẫn |

### Công thức nằm ở job, không ở endpoint

**Endpoint không tính toán** — chỉ đọc mart. Muốn đổi cách tính thì sửa
`app/core/build_marts.py` rồi **chạy lại job**:

| Muốn đổi | Sửa ở |
|---|---|
| `est_sales_90d`, hạng danh mục, co ngót điểm sao | `build_mart_competitor` |
| Trọng số 5 trục điểm sức khoẻ | `TRONG_SO` |
| Ngưỡng dò bất thường, chặn chuỗi thưa | `TOI_THIEU_NGAY_CO_BAN`, `zscore_service.DEFAULT_THRESHOLD` |
| Mô hình dự báo | `build_forecast_point` |
| Cách chọn ngách | `build_niche_score` |

```bash
python -m app.core.build_marts <tên_mart>
python scripts/validate_mart.py <tên_mart>
```

### Bốn hàm phản hồi, hết

| Hàm | Khi nào | Trả ra |
|---|---|---|
| `ok(data, meta)` | Có số, tin được | `200` |
| `partial(data, reason, meta)` | Có số, độ tin cậy thấp | `200` |
| `insufficient(reason, meta)` | Chưa đủ dữ liệu | `200`, `data: null` |
| `mart_not_ready("bảng")` | Mart rỗng | `503` |

Thêm `invalid_param()` → `400`, `forbidden()` → `403`, `not_found()` → `404`.
**Đừng tự `return {...}` hay `raise HTTPException`** — gọi mấy hàm này thì `meta` và
body lỗi tự đúng hợp đồng.

### Sáu cái bẫy — đều đã mắc phải thật

1. **THIẾU ≠ 0.** Chưa đủ dữ liệu thì `insufficient()`, không trả `0`. Shop mới thấy
   *"doanh thu 0đ"* thay vì *"chưa đủ dữ liệu"* là lỗi nặng nhất của dashboard.
2. **Mốc thời gian lấy từ DỮ LIỆU, không phải hôm nay.** Dữ liệu mồi dừng ở
   2026-08-30; lấy `date.today()` thì cửa sổ 30 ngày rơi vào vùng trống. Dùng
   `_mart.ngay_moi_nhat()`.
3. **`computed_at` lấy từ bản ghi mart**, không phải giờ hiện tại. Dùng
   `meta_from_record()`.
4. **`shop_id` chỉ đến từ `CurrentShop`.** Thêm `shopId` vào query là ai cũng xem
   được shop khác.
5. **Tiền là số nguyên VND.** Dùng `_mart.tien()`.
6. **% tính trên nền gần 0 là vô nghĩa** — 1,3 → 3,9 ra "tăng 200%". Đặt ngưỡng nền
   rồi trả `null` kèm cờ. Xem `build_marts.NEN_TOI_THIEU`.

### Bốn chỗ CỐ Ý để null — đừng "sửa" bằng cách điền vào

| Chỗ | Vì sao |
|---|---|
| `mart_demand.searches_per_week` | Google Trends trả **chỉ số 0–100**, không phải lượt tìm. `BR-213` vì vậy **chưa áp dụng được** |
| `forecast_point` → `lstm_mase` | SPEC-03 chưa chốt. Xem `docs/ADR-002.md` |
| F34 `signal.has_signal = false` | Tag dữ liệu mồi gán **ngẫu nhiên**; đã tính hiệu ứng thử nhiều lần |
| F41 `validated: false` | Chưa chạy backtest khuyến nghị |

Trong `listing_health`, trục thiếu dữ liệu bị **loại khỏi phép tính rồi chia lại
trọng số**, không cho 0 điểm — thiếu dữ liệu khác với kém.

---

## 9. Lệnh gọn trong một chỗ

```bash
python run.py              # cai gi thieu + dung du lieu + bat server
python run.py --check      # chi kiem, khong doi gi
python run.py --rebuild    # dung lai toan bo mart
```

Ba dòng trên đủ dùng 95% thời gian. Khi cần lệnh lẻ:

```bash
source .venv/bin/activate                          # Windows: .venv\Scripts\activate

python -m app.core.build_marts --all               # dựng 9 mart
python -m app.core.build_marts niche_score         # dựng lại một bảng
python tests/test_api_contract.py                  # 12/12
python scripts/validate_mart.py --all --offline    # 9/9
python scripts/peek.py listing_daily --limit 3     # xem một bảng trên MongoDB
```
