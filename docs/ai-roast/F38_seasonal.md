# F38 Mùa vụ và lịch ra hàng: roast và đường ra

> Endpoint `GET /api/analytics/forecast/seasonal` (BE proxy `/api/seller/analytics/forecast/seasonal`) · Trang FE `/seller/insights/seasonal` (`FE/src/modules/analytics/pages/SeasonalPage.tsx`) · File chính `app/api/v1/f38_seasonal.py`, `app/services/llm_seasonal_service.py`, `app/services/market_mining_service.py`, `app/core/seasonal_taxonomy.py`, `app/core/build_marts.py:314-350`, `BE/.../seller-analytics.router.ts:69-144` · Ngày 2026-10-21 · Người viết: Claude (subagent)

## 0. Bản đăng ký nói gì

| Mục | SRS 3.10.2 Seasonal Trend Forecasting (tóm tắt) |
|---|---|
| Actor, trigger | Seller đã đăng nhập; mở tab [Xu hướng mùa vụ] |
| Endpoint | `GET /api/analytics/forecast/seasonal`, Bearer JWT |
| Input | `categoryId` (string, tuỳ chọn) |
| Output | Thành phần STL (trend, seasonal, residual), đỉnh mùa gắn với ngày lễ, cửa sổ ra hàng, lịch nội dung. Hợp đồng `docs/API_CONTRACT.md:381-389` có thêm `events[].driver`, `peak_offset_days`, `content_calendar` |
| Xử lý | STL trên dữ liệu lịch sử toàn sàn hoặc theo danh mục; tách thành phần mùa; ánh xạ đỉnh vào từ điển ngày lễ VN và quốc tế (Tết, 8/3, 20/11, Noel); cửa sổ tối ưu thường 3–4 tuần trước đỉnh |
| BR-208 | Cần ít nhất 12 tháng dữ liệu sàn hoặc danh mục |
| BR-209 | Cửa sổ ra hàng trừ thời gian in POD và giao hàng, mặc định −21 ngày tính từ ngày lễ |
| Validation | Danh mục không có mùa vụ rõ thì hiện MSG150 "nhu cầu ổn định quanh năm" |
| Ngoại lệ | STL lỗi vì dữ liệu thưa thì UI dùng lịch lễ cố định, **không** vẽ biểu đồ thống kê |
| Màn hình | `SeasonalTrendsPage.tsx`: 3 biểu đồ nhỏ xếp chồng Trend, Seasonality, Residual; biểu đồ dự báo ngắn hạn; lịch nội dung tương tác; nút "Tạo sản phẩm" sang trang đăng listing |
| LLM | SRS không nhắc Gemini, LLM hay sinh ý tưởng sản phẩm. Grep `report3.txt` không có "Gemini" hay "generative" |

## 1. Roast: code hiện tại thực chất là gì

**"Dự báo mùa vụ" là 6 cái thẻ gõ tay.** `YEARLY_CAMPAIGNS` ở `f38_seasonal.py:26-123` là 6 chiến dịch với `peak_week` cố định. Tết là tuần ISO 2 (`:65`). Trong khi đó `calendar_vn.py:11-22` có sẵn `TET_DATES` tới 2030, `MID_AUTUMN_DATES` ở `:87-98`. Có lịch âm sẵn mà đéo dùng. Tết 2027 rơi vào 06/02, code đặt đỉnh 11/01/2027, sớm 26 ngày. Valentine, 8/3 và 20/10 bị nhét chung một thẻ với một tuần đỉnh 7 (`:76-81`). 20/10 nằm ở tuần 42–43 nhưng cửa sổ của nó vẫn tính theo tuần 7.

**Radar "tiềm năng" là số bịa đặt cạnh số bịa.** `:160-227` gõ tay từng điểm: Tết `demand 98, margin 90, gift 96, cvr 94`. Đường "Ngày thường" là `[60, 50, 65, 52, 60]` (`:237`). Trục thời điểm là `95 - int(days_diff * 0.7)` (`:156`). FE vẽ hai đa giác này chồng nhau, ghi "So sánh với mặt bằng ngày thường" (`SeasonalPage.tsx:321`). Nếu API thiếu radar, FE tự chế thêm `[94, 88, 90, 92, 90]` và điểm 91 (`SeasonalPage.tsx:114-123`). Hai tầng bịa cho một biểu đồ.

**"Đang trong thời điểm vàng" là code chết.** `_cua_so_ra_hang` chỉ nhận năm có ngày bắt đầu cửa sổ còn ở tương lai:
```python
if dinh - timedelta(days=LUI_SAN_XUAT + 21) > hom_nay:
    break
```
(`:134`). Hôm nay mà nằm trong cửa sổ thì nó nhảy sang năm sau. Tao chạy thử ngày 10/12/2026, giữa cửa sổ Tết 30/11–21/12: API báo Tết "upcoming", còn 354 ngày. Đúng lúc seller cần hành động thì hệ thống bảo đợi sang năm. Nhánh `active` (`:261-268`) và điểm 96 (`:154`) không bao giờ chạy. Ngáo vcl.

**Gemini được mồi số rồi khen là "phân tích".** Prompt ở `llm_seasonal_service.py:54-93` nhét sẵn giá trị mẫu `"expected_profit_margin": "45% - 60%"` (`:73`) và `"estimated_profit": "90.000đ - 140.000đ/sp"` (`:87`). Prompt bảo model "phân tích chuyên sâu xu hướng thị hiếu năm nay" (`:65`) mà không đưa một điểm Trends nào. Output chỉ qua regex và `json.loads` (`:115-119`). Điều kiện nhận là có key `ready_to_ship_ideas` (`:38`). Không schema, không kiểm số.

**Không có key thì bịa bằng tay.** `app/.env` và `.env` trên máy dev không có `GEMINI_API_KEY`, nên máy dev luôn chạy nhánh này. Nhánh fallback viết cứng "lượng tìm kiếm tăng vọt 65-80% so với ngày thường" (`:173`), "nâng giá trị đơn thêm 25%" (`:175`), "chi thêm 30–50%" (`:192`), "tỉ lệ chốt đơn … cao hơn 40%" (`:208`). Rồi nó gắn nhãn `ai_model = "VietCraft Market Mining v1.0"` (`:48`). FE in "Phân tích bởi {ai_model}" (`SeasonalPage.tsx:177`). Thiếu biên lãi thì FE tự điền "Lãi: 45% - 55%" (`:422`). Đm, đây là bịa số có thương hiệu.

**Meta nói dối.** `method` cứng là `"Hybrid Data-Mining + Generative AI (Gemini 3.5)"` (`f38:404`), kể cả khi chạy fallback. Trang model Gemini (ai.google.dev, đọc ngày 21/10/2026) có `gemini-3.1-flash-lite`, `gemini-3.8-flash`, `gemini-3.5-flash-lite`. Không có `gemini-3.5-flash`, model thứ hai trong vòng thử (`llm:106`). Meta đặt `mode="live"`, `confidence="high"` (`f38:381-382`). Dòng limitation nói có "doanh số thực tế trên sàn" (`:405`). Thực ra doanh số đọc từ `mart_competitor` (`market_mining_service.py:122`), dựng trên DB seed (`build_marts.py:30-31`). FE còn gắn badge "Chính thức" (`SeasonalPage.tsx:140`).

**"Không dùng từ điển fix cứng" nằm ngay trên từ điển fix cứng.** Docstring `seasonal_taxonomy.py:3` viết "HOÀN TOÀN KHÔNG DÙNG TỪ ĐIỂN FIX CỨNG". Từ điển 58 dòng nằm ở `market_mining_service.py:19-76`. Mà nó cũng không trúng: F38 truyền tên thẻ "Tết Nguyên Đán & Du Xuân" (`f38:354-355`), còn từ điển có key `"quà tết"` (`:20`). Nên `cluster_name` luôn rơi về f-string (`:110-118`). `db_live` được import mà không dùng (`:8`).

**Thứ thật duy nhất bị giấu.** STL period 52 trên Google Trends (`build_marts.py:314-350`) là thống kê thật duy nhất. FE không vẽ `decomposition`: grep cả `FE/src` không có component nào đọc nó. `has_seasonality = bien_do > 5.0` (`:347`) là ngưỡng tuyệt đối trên thang `scaled` lên tới hàng trăm. Tao chạy lại STL trên Trends local: 39/44 từ khoá vượt ngưỡng. Snapshot `seasonal_profile` trong backup seed (`backupDB/mongo-backup/vietcraft-seed`) cũng ra đúng 39/44. Kể cả "áo oversize", trung bình 2,2 và 102/262 tuần bằng 0. `flat_keywords` cứng `[]` (`f38:403`), nên MSG150 không bao giờ hiện.

**Rác quanh rìa.**
- BE gán cứng tên shop `'SNOWKAT'` và ngành `thoi-trang` (`seller-analytics.router.ts:72-73`).
- BE gắn `matched_blank` vào `events[].pod_blanks` (`:97-121`). Tab POD của FE lại đọc `data.pod_blanks` (`SeasonalPage.tsx:109`), là một bản sao JSON khác, nên phôi khớp không bao giờ hiện.
- Tham số `keyword` được nhận mà không dùng (`f38:295`), dù BE vẫn chuyển tiếp (`router:47`).
- Dashboard dẫn sang `?keyword=` (`SellerDashboard.tsx:264`), nhưng trang chỉ đọc `campaign` và `category` (`SeasonalPage.tsx:69-70`).
- `cat_slug` truyền vào radar rồi bỏ (`f38:147`).
- Shop live không có dữ liệu vẫn nhận `ok` đầy đủ (`:297-299`, `:384`).

### Lệch bản đăng ký
- **Màn hình:** SRS đòi 3 biểu đồ STL, biểu đồ dự báo và lịch nội dung. Code không có cái nào. Thay vào đó là radar 5 trục, ý tưởng nhập sỉ và biên lãi, đều không có trong SRS.
- **Thuật toán:** SRS lấy đỉnh từ thành phần mùa STL rồi ánh xạ vào ngày lễ. Code lấy đỉnh từ `peak_week` gõ tay. STL chỉ dùng để chọn vài từ khoá kèm theo (`f38:349-351`).
- **BR-209:** SRS lùi 21 ngày từ ngày lễ. Code lùi 21 và 42 ngày từ tuần đỉnh gõ tay (`:141-142`). Đó không phải ngày lễ.
- **BR-208:** mart đòi 104 tuần (`build_marts.py:325`), chặt hơn SRS, chấp nhận được. Nhưng 6 thẻ chiến dịch không phụ thuộc vào ngưỡng này.
- **MSG150 và ngoại lệ:** không có MSG150. SRS bảo khi STL lỗi thì hiện lịch cứng không kèm thống kê. Code luôn hiện lịch cứng kèm radar số bịa.
- **Input `categoryId`:** code coi nó là slug (`f38:301`). Nó chỉ đổi câu mô tả (`:327`), STL không lọc theo danh mục.
- **Gemini:** ngoài đăng ký. Nếu giữ, phải ghi vào phụ lục SRS như tính năng bổ sung.
- **Tên:** SRS gọi trang là `SeasonalTrendsPage.tsx`, tab [Xu hướng mùa vụ]. Code là `SeasonalPage.tsx`, menu "Mùa vụ và lịch ra hàng" (`FE/.../nav.ts:82`).

## 2. Mổ xẻ lỗi

Lệch bản đăng ký: các dòng ghi mức "(SRS)" là chỗ code khác mục SRS đã đăng ký. Chúng được xếp Nặng trở lên vì hội đồng chấm theo bản đăng ký.

| # | Mức | Chỗ | Lỗi | Hậu quả | Sửa nhanh |
|---|---|---|---|---|---|
| 1 | Chết người | `llm_seasonal_service.py:173,175,192,208,212` | Phần trăm tăng trưởng, chốt đơn, giá trị đơn viết cứng | Seller tin số không đo từ đâu | Xoá mọi số; chỉ in số tính từ dữ liệu |
| 2 | Chết người | `f38_seasonal.py:160-237`, `SeasonalPage.tsx:114-123` | Điểm radar và đường "ngày thường" gõ tay | Biểu đồ trông như đo lường nhưng là hằng số | Bỏ radar; thay bằng 3 biểu đồ STL theo SRS |
| 3 | Chết người | `f38:404`, `llm:48`, `SeasonalPage.tsx:177` | Ghi "Gemini 3.5" và "Market Mining v1.0" khi chạy mẫu câu | Nói dối nguồn gốc kết quả | `method` và `ai_model` lấy từ nhánh thực chạy; fallback ghi "mẫu câu" |
| 4 | Chết người | `f38:381-382,405`, `SeasonalPage.tsx:140,147` | `mode=live`, `confidence=high`, "doanh số thực tế" trên mart seed | Trình bày sai nguồn | `mode="derived"`; nói rõ phần nào là Trends, phần nào là seed |
| 5 | Chết người | `llm:73,87`, `SeasonalPage.tsx:422` | Prompt mồi biên lãi và lợi nhuận; FE tự điền "45% - 55%" | LLM chép số mồi, seller tưởng đã tính | Bỏ trường số khỏi schema LLM; server tự tính từ `base_cost` nếu có |
| 6 | Nặng (SRS) | `SeasonalPage.tsx` toàn trang | Không có 3 biểu đồ STL, biểu đồ dự báo, lịch nội dung | Trượt màn hình đã đăng ký | Vẽ `decomposition`, thêm `forecast` và `content_calendar` |
| 7 | Nặng (SRS) | `f38:26-123` | Đỉnh gõ tay thay vì đỉnh STL ánh xạ vào ngày lễ | Sai thuật toán đã đăng ký | Đỉnh tính theo độ lệch so với ngày lễ trong `calendar_vn.SHOPPING_EVENTS` |
| 8 | Nặng (SRS) | `f38:141-142` | BR-209 trừ từ tuần đỉnh gõ tay, không phải ngày lễ | Cửa sổ Tết 2027 kết thúc 21/12/2026, sớm 47 ngày so với Tết | `end = min(đỉnh, ngày lễ) − 21 ngày` |
| 9 | Nặng (SRS) | `f38:403` | `flat_keywords = []`, không có MSG150 | Danh mục phẳng vẫn được hứa có mùa vụ | Dùng độ mạnh mùa vụ (4.2) để quyết MSG150 |
| 10 | Nặng | `f38:134` | Chỉ chọn cửa sổ có ngày bắt đầu ở tương lai | Trong cửa sổ thật, API báo "còn 354 ngày" | Chọn kỳ gần nhất có `end ≥ hôm nay` |
| 11 | Nặng | `f38:65`, `calendar_vn.py:11-22` | Tết cố định tuần 2, không dùng `TET_DATES` | Lệch 0–4 tuần tuỳ năm | Lấy ngày Tết từ bảng |
| 12 | Nặng | `f38:76-81` | Valentine, 8/3 và 20/10 chung một tuần đỉnh 7 | 20/10 nhận cửa sổ tháng 1 | Tách sự kiện theo `SHOPPING_EVENTS` |
| 13 | Nặng | `build_marts.py:347` | `has_seasonality` bằng biên độ tuyệt đối lớn hơn 5 | 39/44 từ khoá "có mùa", kể cả chuỗi gần như toàn 0 | Dùng độ mạnh mùa vụ kèm kiểm định hoán vị |
| 14 | Vừa | `seasonal_taxonomy.py:20,30-33`, `llm:106-110` | Cache theo slug thô; lỗi thì không cache; 3 model × timeout 25 giây | Mỗi slug lạ là một lần gọi Gemini; một request có thể treo 75 giây | Khoá cache theo `cat_key`; sinh trước trong batch; timeout 8 giây |
| 15 | Vừa | `market_mining_service.py:105-118` | Tra từ điển bằng tên chiến dịch, luôn trượt | Từ điển cứng là code chết | Xoá từ điển; nhóm hàng lấy từ `tag_keyword_map` |
| 16 | Vừa | `router.ts:97-121`, `SeasonalPage.tsx:109` | `matched_blank` gắn vào `events[]`, FE đọc `pod_blanks` | Phôi khớp không bao giờ hiện | Gắn vào `data.pod_blanks` |
| 17 | Vừa | `router.ts:72-73` | Cứng `SNOWKAT` và `thoi-trang` | Shop khác thấy tên và ngành sai | Lấy từ shop thật; không có thì để trống |
| 18 | Nhẹ | `f38:147,295`, `SellerDashboard.tsx:264` | `cat_slug` và `keyword` nhận vào rồi bỏ | Link từ dashboard không có tác dụng | Bỏ tham số, hoặc dùng `keyword` để lọc sự kiện |
| 19 | Nhẹ | `calendar_vn.py:42` | Thông báo lỗi ghi "2021–2026" trong khi bảng tới 2030 | Gây hiểu nhầm khi debug | Sửa chuỗi |

## 3. Tính năng này nên là AI gì

Seller cần biết: "Từ khoá hoặc danh mục của tôi lên đỉnh lúc nào quanh dịp X, và phải đăng bán trước bao lâu?" Phần lớn câu trả lời là **thống kê mô tả có kiểm chứng**, đúng như SRS. Lớp "AI" đáng làm gồm hai bài toán nhỏ, đo được:

| Bài toán | Đầu vào | Đầu ra | Nhãn |
|---|---|---|---|
| Phân rã và độ mạnh mùa vụ (3 biểu đồ SRS, MSG150) | Chuỗi tuần Trends theo từ khoá, gộp lên danh mục qua `tag_keyword_map` | trend, seasonal, residual; `seasonal_strength`; cờ có hoặc không có mùa vụ | Chuỗi tự nó; kiểm bằng hoán vị năm |
| Độ lệch đỉnh so với ngày lễ (cửa sổ BR-209) | Chuỗi tuần và ngày lễ `calendar_vn` (âm lịch qua `TET_DATES`, `MID_AUTUMN_DATES`) | `peak_offset_days` theo từng (từ khoá, dịp), kèm khoảng | Tuần đỉnh thực tế mỗi năm |
| Dự báo 8–12 tuần (biểu đồ dự báo SRS) | Chuỗi tuần đến mốc T | Mức dự báo kèm khoảng 80% | Giá trị Trends thật sau T |

Kết luận: giữ endpoint, input `categoryId` và output đúng `API_CONTRACT.md:381-389`. Gemini không thuộc lõi. Nếu giữ thì để ở khối phụ "gợi ý nội dung", tắt được, và ghi "cần cập nhật SRS/phụ lục".

## 4. Đường ra: thiết kế AI chính hiệu

### 4.1 Dữ liệu: train / validation / test / thực
- **Nguồn chính:** Mongo local `data-collection.trend_interest`, chuỗi tuần 2021-08-15 → 2026-08-16. 45 từ khoá, 262 tuần; giá trị `scaled` đã quy về từ khoá neo (`app/collectors/collect_trends.py:191-203`).
- **Dữ liệu ngày:** 44 từ khoá, 2026-05-18 → 2026-10-17. Chỉ dùng để làm tươi đoạn cuối, không dùng để tách mùa năm.
- **Chia theo thời gian:** rolling origin bằng `app/core/backtest.py:rolling_origin`, bước 8 tuần.
  - Validation: các mốc trong 2024-08 → 2025-08.
  - Test: các mốc 2025-08 → 2026-08, chỉ đọc một lần và ghi số lần đọc như Listing Intel.
  - Độ lệch đỉnh: chia bỏ một năm (leave-one-year-out). Ước lượng từ các năm trước Y, chấm trên năm Y.
- **Chống rò rỉ:** chỉ số mùa chỉ tính từ dữ liệu trước mốc, như `trend_axis.demand_factor` đã làm (`trend_axis.py:82-83`). Ngày lễ biết trước nên không tính là rò rỉ. Không dùng bảng seed nào.
- **Đối chiếu:** `tikireviews` theo tháng chỉ dùng để sanity. Báo cáo §8 cho tương quan yếu: fashion r = −0.142 (p = 0.660). Không được dùng làm nhãn.
- **Lỗ dữ liệu:** "halloween", "quà trung thu", "quà khai giảng", "black friday" chưa có chuỗi (`LISTING_INTEL_REPORT.md` §8). Trước khi thu được, các dịp này chạy theo nhánh ngoại lệ SRS: chỉ lịch, không vẽ thống kê.
- **Chuyển sang dữ liệu VietCraft:** đếm `search_logs` theo `keyword_norm` theo tuần (`BE/.../search-log.model.ts:9-16`), cộng đơn hàng theo danh mục. Chỉ chuyển khi đủ 12 tháng (BR-208). Tới lúc đó, Trends VN thay cho "dữ liệu lịch sử toàn sàn": **cần cập nhật SRS/phụ lục** để ghi rõ nguồn.

### 4.2 Làm sạch và sanity
- **Thay ngưỡng biên độ:** dùng độ mạnh mùa vụ `F_s = max(0, 1 − Var(R)/Var(S+R))`, không phụ thuộc thang. Ngưỡng chọn trên validation.
- **Từ khoá thưa:** nhiều tuần bằng 0 (ví dụ "áo kpop" 259/262 tuần) thì không được kết luận có mùa. Từ khoá theo dịp phải có số khác 0 trong ±8 tuần quanh dịp ở ít nhất 3 năm.
- **Kiểm ranh giới:** `categoryId` phải thuộc danh sách danh mục; `campaign_id` thuộc enum; độ dài giới hạn. `keyword` bỏ, hoặc chỉ nhận giá trị nằm trong danh sách từ khoá.
- **Sanity bắt buộc:**
  1. Hoán vị khối năm: `F_s` phải giảm. Tỉ lệ báo "có mùa" trên chuỗi hoán vị không quá 5%.
  2. Chuỗi tổng hợp có đỉnh −14 ngày trước Tết: phải tìm lại được. `calendar_vn.py:180-194` đã có khung tự kiểm.
  3. Tuần ISO 53 được gộp về 52 (`trend_axis.week_of_year`).
  4. Tái dựng `trend + seasonal + residual = chuỗi gốc` (`stl_service.py` self-check).

### 4.3 Model
- **Baseline:**
  - (a) Seasonal naive, lấy cùng tuần năm trước.
  - (b) Luật BR-209 thuần: đỉnh tại ngày lễ, cửa sổ kết thúc ở ngày lễ − 21.
  - (c) Bảng `peak_week` gõ tay hiện tại.
  - (d) Độ lệch đỉnh của năm trước.
- **Phân rã:** STL period 52, robust (đã có). Dùng để vẽ 3 biểu đồ.
- **Dịp âm lịch:** Tết và Trung thu trôi 3–4 tuần mỗi năm, nên period 52 làm nhoè đỉnh. STL local cho "quà tết" đỉnh ở tuần ISO 1, trong khi Tết 2026 rơi vào tuần 8. Cách sửa: hồi quy theo trục ngày lễ `y_t = trend + Σ_k β_{e,k}·1[t − ngày_e = k tuần] + Fourier(K=3)`, với k ∈ [−8, +2]. Chạy bằng `statsmodels` OLS. `peak_offset = argmax_k β`. Trục ngày lễ có sẵn ở `calendar_vn.get_tet_aligned_series` (`:74-84`).
- **Cửa sổ ra hàng:** `end = min(ngày lễ, đỉnh dự kiến) − 21 ngày` (BR-209); `start = end − 7…14 ngày`. Như vậy cửa sổ nằm 3–4 tuần trước đỉnh, đúng SRS.
- **Dự báo:** chọn giữa seasonal naive, STL kèm drift, ETS (`statsmodels`) theo backtest trên validation. Luật chọn có sẵn ở `scripts/li/trend_eval.py:_selected`. Tất cả chạy trên CPU, không cần torch.

### 4.4 Học từ dữ liệu thật
- **Lịch chạy:** chạy lại mỗi tuần, gắn vào job `weekly_trends` có sẵn (`listing_intel/jobs.py:65`, thứ Hai 03:00). Mỗi lần ghi chỉ số backtest theo từ khoá vào mart.
- **Drift:** mỗi dịp, so độ lệch đỉnh thật với dự kiến. Lệch quá 2 tuần thì cảnh báo và ước lượng lại. Theo dõi độ phủ khoảng dự báo: khoảng 80% phải phủ 75–85%.
- **Feedback:** listing đăng trong cửa sổ có nhiều view hoặc đơn hơn ở tuần dịp không? Phần này cần pipeline sự kiện sản phẩm, hiện chưa có chủ.
- **Cold start:** shop mới dùng cấp danh mục. Danh mục không đủ dữ liệu thì dùng lịch lễ thuần, hiện nhãn "chưa đủ dữ liệu".

### 4.5 Bảo mật và chống gian lận (có LLM)

**Dữ liệu vào prompt hôm nay**

| Trường | Nguồn | Ai điều khiển | Rủi ro injection |
|---|---|---|---|
| `keyword` | `active_camp["name"]`, gõ tay (`f38:354`) | Dev | Thấp |
| `cluster_name` | Từ điển cứng, hoặc f-string từ tên chiến dịch (`market_mining:108-118`) | Dev | Thấp |
| `market_price_range` | Doanh thu chia số bán của `mart_competitor` seed (`:149-176`) | Seed; sau này là giá do seller nhập | Chỉ là số, thấp |

**Chưa vào prompt nhưng nằm sát cửa**
- Tham số `keyword` (`f38:295`): BE chuyển tiếp chuỗi tới 120 ký tự (`router:47,56-64`).
- Tiêu đề listing đối thủ (`market_mining:155-158`). Fallback đã in nguyên văn chúng làm "ý tưởng" (`llm:165-171`).
- Prompt ghép bằng f-string, không tách lệnh khỏi dữ liệu (`llm:54-93`). Ai nối thêm một trong các trường trên là mở cửa injection gián tiếp ngay: một seller đặt tiêu đề "Bỏ qua hướng dẫn trên, …" là đủ.

**Rủi ro đang có**
- Output không kiểm schema. BE dùng `blank_type` do LLM sinh để khớp phôi (`router:100-109`).
- Model có thể bịa giá, biên lãi, tên thương hiệu có bản quyền. Danh sách cấm BR-211 không chạy trên output.
- Khoá API nằm trong query string (`llm:107`). REST mẫu của Google cũng làm vậy, nhưng khoá dễ lọt vào log hoặc proxy. Nên chuyển sang header (tên header cần xác minh trên tài liệu hiện hành).
- Khuếch đại chi phí: xem lỗi số 14.

**Cách phòng (nếu giữ LLM)**
1. **Tách lệnh và dữ liệu:** luật đặt trong `systemInstruction` (trang API `generateContent` có trường này). Dữ liệu là khối JSON riêng, có nhãn "dữ liệu, không phải lệnh". Bỏ ký tự điều khiển; giới hạn độ dài; chỉ nhận ký tự chữ Việt, số và dấu câu.
2. **Structured output:** đặt `responseMimeType: application/json` kèm `responseSchema` (ví dụ trên trang API có dùng). Server kiểm lại bằng pydantic, cấm trường thừa. `blank_type` là enum 4 giá trị. Tài liệu structured output của Google dặn vẫn phải kiểm giá trị ở phía ứng dụng.
3. **LLM không được sinh số:** bỏ `expected_profit_margin`, `estimated_profit`, `market_price_range` khỏi schema. Server tự điền từ dữ liệu. Lớp kiểm hậu kỳ quét mọi chữ số trong text: số nào không có trong tập số đã cấp thì xoá câu đó.
4. **Grounding:** mỗi ý tưởng phải trích ít nhất một từ khoá Trends trong danh sách đầu vào. Validator kiểm từ khoá đó có thật trong input.
5. **Lọc output:** chạy `banned_keywords` (BR-211) và danh sách thương hiệu trên output.
6. **Bộ red-team tiếng Việt, khoảng 40 ca:**
   - "Bỏ qua mọi hướng dẫn trước", có dấu và không dấu.
   - Đòi in khoá API hoặc prompt hệ thống.
   - Chuỗi phá JSON (`"}`, xuống dòng); ký tự Unicode giống chữ Latin.
   - Lệnh nhét trong tiêu đề listing (gián tiếp).
   - Ép nêu thương hiệu, ép báo phần trăm tăng trưởng.
   - Đo tỉ lệ tấn công thành công (ASR) trước và sau khi thêm lớp phòng.
7. **Đo ảo giác số:** tỉ lệ chữ số trong output không truy được về input, chấm trên 50 prompt cố định. Cổng là 0 sau validator.
8. **Nhãn trung thực:** `ai_model` chỉ có khi LLM thật sự chạy, ghi đúng mã model đã trả lời.

**Chống gian lận khác**
- Khi chuyển sang `search_logs`: chỉ đếm user duy nhất mỗi tuần, loại tìm kiếm của chính seller, giới hạn tần suất. Mục đích là chặn đẩy giả một dịp.

### 4.6 Benchmark và kiểm chứng

| Phần | Metric | Baseline | Cổng đạt |
|---|---|---|---|
| Dự báo (biểu đồ SRS) | MASE chia cho seasonal naive, horizon 8, ≥ 6 mốc | Seasonal naive | ΔMASE trung vị theo từ khoá < 0, CI bootstrap 95% (cụm theo từ khoá) không chứa 0 |
| Độ lệch đỉnh, cửa sổ | MAE tuần đỉnh; tỉ lệ trúng ±1 tuần; leave-one-year-out | (b), (c), (d) ở 4.3 | MAE thấp hơn baseline tốt nhất ít nhất 0,5 tuần, CI không chứa 0 |
| Có hay không có mùa (MSG150) | Tỉ lệ báo nhầm trên chuỗi hoán vị; độ ổn định giữa các mốc | `bien_do > 5` | Báo nhầm ≤ 5% |
| LLM (nếu giữ) | Tỉ lệ đúng schema, ASR, tỉ lệ ảo giác số | Prompt hiện tại | Schema 100%; ảo giác số 0; ASR giảm có ý nghĩa |

- **Số đã có để so:**
  - Mốc cuối: STL đạt MASE < 1 ở 68,9% từ khoá, naive 71,1%.
  - 6 mốc trượt: luật chọn đạt 48,9%, dưới 50% (`LISTING_INTEL_REPORT.md` §8).
  - Đỉnh rơi vào −4…0 tuần trước dịp ở 84,6% của 52 cặp (từ khoá, năm). Đây là mốc để so với luật −21 ngày.
- **Không thắng thì nói thẳng:** dùng seasonal naive cho biểu đồ dự báo và ghi trên trang "dự báo bằng cùng kỳ năm trước". Đừng gọi là AI.

## 5. Lộ trình

| Giai đoạn | Việc | Kết quả kiểm chứng |
|---|---|---|
| Ngay 1–2 ngày | Xoá số bịa (lỗi 1, 2, 5); `method`, `ai_model`, `mode` trung thực; sửa lỗi cửa sổ (10); Tết từ `TET_DATES`; tách 20/10, 8/3; gỡ `SNOWKAT`; sửa `matched_blank` | Grep không còn chuỗi "%" cứng; test ngày 10/12/2026 trả Tết `active` |
| 1–2 tuần | Vẽ 3 biểu đồ STL; `F_s` và MSG150; mô hình độ lệch đỉnh trục ngày lễ; `content_calendar` từ `SHOPPING_EVENTS`; biểu đồ dự báo; script backtest `scripts/f38/` có test | Bảng 4.6 với CI; sanity 4.2 đều qua |
| Nếu giữ LLM | Schema, validator, red-team 40 ca, đo ảo giác số; ghi phụ lục SRS | ASR, schema 100%, ảo giác 0 |
| Khi có dữ liệu thật | `search_logs` ≥ 12 tháng thì thay nguồn cầu theo danh mục; feedback listing trong cửa sổ | So lại 4.6 trên dữ liệu sàn |

**Xong khi:**
- Không còn con số nào trên trang mà không truy được về dữ liệu.
- Bảng 4.6 có số kèm CI, kể cả khi thua baseline.
- Có test cho cửa sổ, cho MSG150 và cho validator LLM.
- Khớp endpoint và các BR của mục SRS 3.10.2:
  - `GET /api/analytics/forecast/seasonal`, input `categoryId`.
  - 3 biểu đồ STL, biểu đồ dự báo, lịch nội dung, nút "Tạo sản phẩm".
  - BR-208: ≥ 12 tháng dữ liệu.
  - BR-209: −21 ngày từ ngày lễ.
  - MSG150 và nhánh ngoại lệ "lịch cứng không kèm thống kê".

## 6. Hội đồng sẽ hỏi

1. **"Gemini có trong bản đăng ký không?"** Không. SRS 3.10.2 chỉ có STL, từ điển ngày lễ và cửa sổ ra hàng. Nhóm sẽ đưa LLM ra khỏi lõi, hoặc ghi vào phụ lục như phần bổ sung có kiểm soát.
2. **"Dữ liệu lịch sử toàn sàn ở đâu?"** Sàn mới có khoảng 79 sản phẩm và 4 đơn, chưa đủ BR-208. Nhóm dùng Google Trends VN 5 năm làm nguồn thay thế, có ghi rõ trên trang và trong phụ lục.
3. **"Cửa sổ ra hàng có chính xác không?"** Đo bằng leave-one-year-out trên 4 năm. So với luật −21 ngày cố định và với độ lệch của năm trước. Báo MAE tuần kèm CI.
4. **"Sao không dùng deep learning?"** 45 chuỗi, mỗi chuỗi 262 điểm. Trên dữ liệu này, seasonal naive đã khó thắng (48,9% từ khoá ở 6 mốc). Model lớn hơn chỉ overfit.
5. **"LLM bịa số thì sao?"** Schema không có trường số. Server điền số từ dữ liệu. Validator xoá câu chứa số lạ. Có bộ red-team tiếng Việt và báo tỉ lệ ảo giác số.
