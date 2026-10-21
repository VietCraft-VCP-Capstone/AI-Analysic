# F32 Ai đang bán chạy: roast và đường ra

> Endpoint `GET /api/analytics/competitors?categoryId=` (BE proxy `/api/seller/analytics/competitors`) · Trang FE `/seller/insights/competitors` (`FE/src/modules/analytics/pages/CompetitorsPage.tsx`) · File chính `app/api/v1/f32_competitors.py`, `app/api/v1/_competitor_live.py`, `app/core/build_marts.py:57-147` · Ngày 2026-10-21 · Người viết: Claude (subagent)

## 0. Bản đăng ký nói gì

| Mục | SRS 3.9.1 In-Category Competitor Analysis (tóm tắt) |
|---|---|
| Actor | Seller đã đăng nhập, có ít nhất một listing đang bán trong danh mục được chọn |
| Trigger | Seller chọn danh mục ở dropdown [Danh mục], tab "Đối thủ cạnh tranh" của Product Analytics |
| Endpoint | `GET /api/analytics/competitors?categoryId={categoryId}`, Bearer JWT (Seller) |
| Input | `categoryId` (bắt buộc); hệ thống lấy `sellerId` từ JWT |
| Output | Top 20 listing đối thủ xếp theo doanh số ước lượng, kèm các listing của chính seller trong danh mục |
| Xử lý | Đọc cache "competitor scan" tính trước trong Mongo, làm mới hằng ngày bằng job lịch; không tính tại chỗ |
| Màn hình | `SellerCompetitorAnalysisPage.tsx`, route `/seller/analytics/competitors`; tiêu đề "Phân tích đối thủ trong danh mục"; dải "Cập nhật lần cuối"; 3 biểu đồ cột Recharts (giá, số review, số yêu thích); bảng: hạng, tên shop (bấm sang trang shop công khai), tên sản phẩm, giá, số review, số yêu thích, doanh số ước lượng |
| BR-186 | Dropdown chỉ liệt kê danh mục seller có ít nhất một listing đang bán |
| BR-187 | Dữ liệu đối thủ làm mới mỗi ngày một lần; mốc "cập nhật lần cuối" là giờ quét, không phải giờ thực |
| BR-188 | Top 20 xếp theo doanh số ước lượng giảm dần; hoà thì phá bằng số review giảm dần |
| BR-189 | Shop của seller không nằm trong top 20, nhưng luôn được vẽ chồng lên biểu đồ để so |
| Validation | Mặc định chọn danh mục seller có nhiều listing nhất; không có listing thì empty state MSG137; lỗi tải thì MSG136 |
| Ngoại lệ | Danh mục có dưới 20 listing đối thủ thì hiện đúng số đang có, không chèn dòng giả |

## 1. Roast: code hiện tại thực chất là gì

**Tên là "Ai đang bán chạy", ruột là một câu `sort`.** `f32_competitors.py:62` là toàn bộ "trí tuệ":
```python
doi_thu.sort(key=lambda r: (-r["est_sales_90d"], r.get("rank_in_cat") or 0))
```
Không ước lượng, không độ bất định, không model. Đếm đơn rồi xếp. Đây là `ORDER BY`, đéo phải AI.

**Bảng xếp hạng theo ngày sinh.** Sàn thật có 4 đơn (`docs/LISTING_INTEL_TECH_REPORT.md:136`). `est_sales_90d` ở live là tổng số lượng của đơn DELIVERED trong 90 ngày (`_competitor_live.py:103-114`), nên gần như mọi sản phẩm bằng 0. Hoà thì phá bằng doanh thu (cũng 0) rồi bằng `listing_id` (`_competitor_live.py:197`). `listing_id` là chuỗi ObjectId, mà 4 byte đầu của ObjectId là thời điểm tạo. Kết quả: sản phẩm đăng sớm nhất thành "bán chạy nhất". Thế mà FE vẫn in "Bán chạy nhất là X của Y (0 cái trong 90 ngày)" (`CompetitorsPage.tsx:208`) và "đứng hạng k/n" (`:202`). Ngáo vl.

**Comment nói dối, tài liệu nói một đằng code làm một nẻo.** `_competitor_live.py:25` ghi `K_CO_NGOT = 10  # giống build_marts.K_CO_NGOT`. Trong `build_marts.py` đéo có `K_CO_NGOT`, chỉ có `M_BAYES = 50` (`build_marts.py:20`). Cùng một cột `rating_shrunk` mà hai đường co ngót lệch nhau 5 lần. `docs/BAYES_M_SELECTION.md:12,25` khoe đã chuyển sang prior toàn sàn, trong khi cả live (`_competitor_live.py:181-191`) lẫn seed (`build_marts.py:83-91`) vẫn co về trung bình danh mục.

**"Cao hơn 100% sản phẩm cùng danh mục".** `_phan_vi` đếm tỉ lệ phần tử `<=` giá trị (`f32_competitors.py:26-30`), và mẫu so sánh có cả sản phẩm của chính mình (`:63-64`). Nếu trong danh mục chỉ sản phẩm của mình có review thì `sao_cat = [của mình]`, ra 100. FE in luôn "Cao hơn 100% sản phẩm cùng danh mục" (`CompetitorsPage.tsx:234`). Một mình một chợ mà dám khoe hơn cả chợ, đm.

**Đường seed là xổ số.** `est_sales_90d` seed cộng `units_sold` từ `listing_daily` (`build_marts.py:61-68`). Số đó sinh theo tier hot/medium/tail (`docs/SEED_PARAMS.md:52-55`), và tier được gán bằng `random.shuffle` (`app/seed/marketplace/generate_seed.py:237-238`), độc lập với giá. Demo xếp hạng một biến ngẫu nhiên rồi gọi đó là thị trường.

**Ghi công cho đúng.** `tests/test_competitor_live.py` có 22 test, chạy hôm nay: `22 passed in 0.39s`. Các test kiểm đúng việc chỉ đếm đơn đã giao, bỏ đơn mô phỏng, review rỗng thì trả null, không trộn seed với live (`_competitor_live.py:105, 293-301`). `GHI_CHU` cũng nói thật nguồn số (`f32_competitors.py:19-23`). Nhưng các test chỉ chứng minh code làm đúng điều nó định làm. Chưa test nào hỏi: top này kỳ sau còn là top không.

### Lệch bản đăng ký

- **BR-187, không có cache hằng ngày.** Live tính lại cả sàn mỗi request (`_competitor_live.py:277-280`, code tự ghi `shortcut`), và `computed_at = now` (`:177`). Vì vậy "cập nhật lần cuối" là giờ request, ngược đúng câu chữ BR-187. Mart seed chỉ dựng khi chạy tay `python -m app.core.build_marts --all` (`app/main.py:52`). Scheduler (`app/core/f29_scheduler.py:109-131`) chỉ có job F29.
- **BR-188, phá hoà sai.** SRS bảo phá hoà bằng số review giảm dần. Live phá bằng doanh thu rồi `listing_id`, mà dòng đó còn dán nhãn `# BR-188` (`_competitor_live.py:197`). Seed phá bằng doanh thu (`build_marts.py:137`).
- **BR-189 và màn hình, không có biểu đồ.** `CompetitorsPage.tsx` không import Recharts (grep `recharts` ra 0), chỉ có các ô số `MiniStat` (`:223-242`). Cả 3 biểu đồ đăng ký đều không có. Payload `my_listings` cũng thiếu `n_reviews` và `favorite_count` (`f32_competitors.py:76-84`), nên có muốn vẽ chồng lên biểu đồ review và yêu thích thì cũng không có số.
- **Ngoại lệ "dưới 20 thì hiện số đang có".** Code trả `insufficient` khi có dưới 5 sản phẩm đối thủ (`f32_competitors.py:57-60`). SRS không đặt ngưỡng tối thiểu.
- **Tên shop dẫn sai chỗ.** SRS muốn mở trang shop công khai. Code dẫn sang `/seller/competitors/{shop_id}` (`CompetitorsPage.tsx:281`).
- **Tên trang, tab, route khác.** SRS là `SellerCompetitorAnalysisPage.tsx`, tab "Đối thủ cạnh tranh", `/seller/analytics/competitors`. Code là `CompetitorsPage.tsx`, nhãn "Ai đang bán chạy" (`FE/src/modules/analytics/nav.ts:70`), `/seller/insights/competitors`.
- **Cấp danh mục.** Ví dụ trong SRS là "[Danh mục: Áo thun]", tức cấp lá. Code gộp về danh mục cấp 1 (`_competitor_live.py:142-144,163`), còn cấp lá chỉ nằm ở `product_type_id` (`:165`).
- **BR-186 ở seed.** Mart seed lấy listing mọi trạng thái (`build_marts.py:78-81`) và `danh_muc_cua_toi` đếm tất cả (`_competitor_live.py:304-311`). Live thì đúng, vì chỉ lấy PUBLISHED (`:131`).

## 2. Mổ xẻ lỗi

| # | Mức | Chỗ | Lỗi | Hậu quả | Sửa nhanh |
|---|---|---|---|---|---|
| 1 | Chết người | `_competitor_live.py:197`; FE `CompetitorsPage.tsx:202,208` | 0 đơn thì thứ hạng là thứ tự ObjectId | Nói với seller "bán chạy nhất" cho sản phẩm 0 đơn | Top có `est_sales_90d = 0` thì không in "bán chạy nhất", hiện "chưa đủ đơn để xếp hạng" |
| 2 | Chết người | `f32_competitors.py:26-30,63-64`; FE `:234` | Phân vị `<=` tính cả sản phẩm của mình | "Cao hơn 100%" khi mình là sản phẩm duy nhất có review | Bỏ sản phẩm của mình khỏi mẫu, dùng mid-rank, mẫu dưới 5 thì trả null |
| 3 | Nặng (lệch SRS) | BR-187: `_competitor_live.py:177,277-280`; `f29_scheduler.py` | Không có job hằng ngày; giờ cập nhật là giờ request | Vi phạm BR-187, đọc cả sàn mỗi lần mở trang | Job đêm ghi `mart_competitor_live`, endpoint chỉ đọc, `computed_at` lấy từ job |
| 4 | Nặng (lệch SRS) | BR-188: `_competitor_live.py:197`, `build_marts.py:137` | Phá hoà bằng doanh thu và id thay vì số review | Vi phạm BR-188 ngay trên dòng ghi `# BR-188` | Khoá xếp `(-est_sales, -n_reviews, listing_id)` |
| 5 | Nặng (lệch SRS) | BR-189: FE chỉ có `MiniStat`, không có biểu đồ; `f32_competitors.py:76-84` | Thiếu 3 biểu đồ; `my_listings` thiếu review và yêu thích | Màn hình đăng ký không tồn tại | Thêm 3 BarChart, trả đủ cột cho `my_listings` |
| 6 | Nặng (lệch SRS) | `f32_competitors.py:57-60` | Có dưới 5 đối thủ thì chặn | Trái ngoại lệ "hiện số đang có" | Vẫn trả danh sách, kèm cờ `low_sample` |
| 7 | Nặng (lệch SRS) | `CompetitorsPage.tsx:281`, `nav.ts:70`, route | Link shop, tên trang, route khác SRS | Hội đồng dò theo SRS không thấy | Đổi nhãn và link, hoặc ghi ánh xạ vào phụ lục SRS |
| 8 | Nặng (lệch SRS) | `_competitor_live.py:142-144,163` | Danh mục cấp 1 thay cho cấp lá | Bán cốc gốm phải so với chăn, thảm, đèn | Cho `categoryId` nhận cấp lá (`product_type_id`) |
| 9 | Nặng | `_competitor_live.py:25` và `build_marts.py:20` | K=10 ở live, M=50 ở seed, comment sai | Cùng tên cột, hai nghĩa | Import `K_BAYESIAN_SHRINKAGE` từ `app/core/f29/constants.py:18` |
| 10 | Vừa | `_competitor_live.py:181-191`; `build_marts.py:83-91` | Prior theo danh mục, trái `BAYES_M_SELECTION.md:12,25` | Doc và code nói ngược nhau | Chọn một, sửa phía còn lại |
| 11 | Vừa | `_competitor_live.py:103-114,267-268` | Không đọc `buyer_id`, không giới hạn số lượng mỗi buyer, không trừ hàng trả | Tự mua hoặc một buyer mua 50 cái là leo top | Đếm buyer phân biệt, loại đơn của chủ shop |
| 12 | Vừa | `_template.py:42`; `f32_competitors.py:55` | `confidence` mặc định "medium" | Meta báo tin cậy vừa trong khi toàn số 0 | Tính `confidence` từ số đơn và độ rộng khoảng |
| 13 | Nhẹ | `_competitor_live.py:105-106` | Lọc theo `created_at` nhưng đòi DELIVERED | Đơn mấy ngày gần nhất chưa giao bị bỏ, số lệch về quá khứ | Lọc theo ngày giao, ghi rõ trong note |
| 14 | Nhẹ | `BAYES_M_SELECTION.md:43-57,65` | Chỉ thử m = 10/20/50, chọn ở mép lưới trong khi Pearson vẫn đang tăng | m chưa chắc tối ưu | Mở rộng lưới, chọn theo log-likelihood trên phần giữ lại |

## 3. Tính năng này nên là AI gì

Phải giữ đúng hợp đồng 3.9.1: cùng endpoint, top 20 xếp theo **doanh số ước lượng**, phá hoà bằng số review, có danh sách của seller để vẽ chồng. AI nằm ở chữ "ước lượng": khi dữ liệu thưa, số đếm thô 90 ngày không phải ước lượng tốt cho câu "ai đang bán chạy".

- **Bài toán:** với mỗi listing `i` trong danh mục `c`, ước lượng tốc độ bán `λ_i` (đơn vị/ngày) từ số bán `y_i` trong thời gian lên sàn `t_i` (≤ 90 ngày). Output chính: `est_sales_90d = 90·E[λ_i | dữ liệu]`, kèm khoảng 80% và khoảng thứ hạng.
- **Nhãn để kiểm chứng:** số bán thật ở kỳ 90 ngày kế tiếp. Ước lượng nào xếp đúng top của kỳ sau hơn thì tốt hơn.
- **Phần nên giữ là thống kê mô tả:** giá, số review, số yêu thích trên 3 biểu đồ. Không cần ML cho phần này.
- **Phần không làm:** chọn đối thủ bằng embedding thay cho danh mục. SRS ghi rõ "in-category". SigLIP2 chỉ dùng phía sau để bắt listing khai sai danh mục (mục 4.5), và có thể thêm một cột phụ "giống sản phẩm của bạn". Cột này không được đổi thứ tự BR-188.

## 4. Đường ra: thiết kế AI chính hiệu

### 4.1 Dữ liệu: train / validation / test / thực
- **Olist** (`/home/rio/Documents/CODE/nodejs/vietcraft/olist/`) là nguồn chính, vì có panel theo thời gian: `order_items` gồm `product_id` và `seller_id`, `orders` có ngày mua và trạng thái, `products` có danh mục. Đo nhanh hôm nay (đơn delivered, một cặp cửa sổ 2017-10-01→2017-12-30 so với 2017-12-30→2018-03-30, chưa có CI):
  - 8,232 sản phẩm có bán trong cửa sổ đầu, 63.6% trong số đó chỉ bán đúng 1 cái;
  - 23 danh mục có ít nhất 50 sản phẩm có bán;
  - baseline "top kỳ trước" (chính là code hiện tại) đạt precision trung bình 0.39 ở cả @10 và @20;
  - ở vị trí thứ 20, trung vị có 7 sản phẩm hoà điểm. Hoà là chuyện thường, không phải ngoại lệ.
- **Chia tập:** rolling origin theo thời gian, cửa sổ 90 ngày trượt mỗi 30 ngày. Train là các mốc đến 2017-12, validation là mốc 2018-Q1, test là mốc cuối 2018-Q2. `app/core/backtest.py:15` (`rolling_origin`) chỉ nhận một chuỗi, nên cần thêm bộ cắt cửa sổ cho panel, có thể dùng lại cách sinh mốc của nó.
- **Chống rò rỉ:** feature chỉ lấy từ dữ liệu trước mốc. Prior `α_c, β_c` fit lại ở từng mốc. Cụm bootstrap theo seller.
- **Tiki:** tiki23 và tiki26 là ảnh chụp một thời điểm, không có panel. Chỉ dùng để kiểm bước kNN và khai sai danh mục, không dùng cho kiểm chứng dự báo.
- **VietCraft thật:** 4 đơn là chưa có gì để đánh giá. Chỉ chuyển sang kiểm trên dữ liệu sàn khi có ít nhất khoảng 2 kỳ 90 ngày và mỗi danh mục có ≥ 30 đơn. Ngưỡng này là đề xuất, phải tự đo lại.

### 4.2 Làm sạch và sanity
- Chỉ đếm đơn DELIVERED, không mô phỏng, không có `seed_ref` (giữ như `_live.py:104-105`). Trừ item đã hoàn hoặc trả nếu BE có trạng thái đó (cần xác minh trạng thái hoàn sau giao).
- Mỗi listing có `t_i` = số ngày nằm trong cửa sổ kể từ `created_at`. Listing 3 ngày tuổi bán 2 cái không được coi như listing 90 ngày bán 2 cái.
- Ranh giới tin cậy: `categoryId` phải thuộc BR-186 (đã có `invalid_param`, `f32_competitors.py:43-44`); giá ≤ 0 hoặc thiếu thì loại (đã có, `_competitor_live.py:97,138-140`).
- Sanity bắt buộc:
  1. xáo nhãn kỳ sau thì NDCG phải rơi về mức ngẫu nhiên;
  2. danh mục toàn 0 đơn thì endpoint không được in "bán chạy nhất";
  3. tổng `est_sales_90d` của danh mục phải nằm trong ±10% tổng số bán thô (co ngót chỉ chia lại, không tạo thêm doanh số).

### 4.3 Model
- **B0 (hiện tại):** đếm thô `y_i` của 90 ngày.
- **B1:** tốc độ thô `y_i / t_i × 90`.
- **M1, Gamma-Poisson empirical Bayes theo danh mục:** `λ_i ~ Gamma(α_c, β_c)`, hậu nghiệm `(y_i + α_c)/(t_i + β_c)`. Fit `α_c, β_c` bằng cực đại likelihood biên (negative binomial) bằng scipy hoặc statsmodels, chạy được trên CPU, không cần torch. Đây là bản đếm-đơn của chính phép co ngót Bayes dự án đã dùng cho rating.
- **Khoảng thứ hạng:** rút 1,000 mẫu `λ` từ hậu nghiệm, xếp hạng từng mẫu, lấy phân vị 10–90 của hạng. FE hiện "hạng 3–9". Nếu khoảng hạng của top 1 chồng lên quá nửa top 20 thì ghi "chưa phân biệt được".
- **M2 (chỉ làm khi M1 thắng B0):** `HistGradientBoostingRegressor(loss="poisson")` của sklearn. Feature gồm hậu nghiệm M1, tuổi listing, phân vị giá trong danh mục, số review, rating co ngót. Target là số bán kỳ sau.
- Thứ tự xuất ra vẫn theo BR-188: `est_sales_90d` giảm dần, rồi số review giảm dần.

### 4.4 Học từ dữ liệu thật
- Job đêm (BR-187) fit lại `α_c, β_c` và ghi `model_version` cùng `computed_at` vào mart.
- Cold start: danh mục ít hơn 30 đơn thì mượn prior của danh mục cha hoặc toàn sàn. Payload ghi rõ prior lấy từ đâu.
- Mỗi tháng backtest lại: so top 20 của tháng trước với số bán thật của tháng này, lưu NDCG@20 vào một collection để theo dõi drift. Hai tháng liền thua B0 thì tự quay về B0 và báo lên.
- Thống nhất K co ngót của rating (mục 2, #9 và #10).

### 4.5 Bảo mật và chống gian lận
- **Tự mua:** đọc `buyer_id`, bỏ đơn của chủ shop. BE đã chặn tự đánh giá (`BE/.../order/application/review.service.ts:93-94`), nhưng grep chưa thấy chặn tự mua (cần xác minh).
- **Đơn ảo, nick phụ:** đếm theo buyer phân biệt, giới hạn mỗi buyer tối đa 2 cái cho mỗi listing trong mỗi cửa sổ. Gắn cờ listing có trên 50% số bán đến từ một buyer, hoặc buyer mới tạo chỉ mua của đúng một shop.
- **Review ảo:** BR-188 phá hoà bằng số review, nên review ảo cũng thành đòn bẩy leo hạng. Chỉ đếm review gắn với đơn đã giao. Kaggle `farmingfree/vietnamese-e-commerce-suspicious-reviews-dataset` dự án đã từng tải (`scripts/li/reviews.py:10-13`) có thể dùng làm dữ liệu huấn luyện bộ lọc, nếu bộ này thật sự có nhãn (cần xác minh).
- **Khai sai danh mục để né đối thủ:** dùng SigLIP2 (`app/core/listing_intel/embedder.py`) tính độ giống giữa listing và tâm danh mục. Listing lệch xa thì gắn cờ cho admin, không tự đổi danh mục.
- **Đo được:** bơm k đơn giả vào một sản phẩm ngẫu nhiên trong backtest Olist, đo số đơn giả cần để vào top 20, trước và sau khi có lớp phòng vệ. Cổng đạt: chi phí leo top tăng ít nhất 2 lần.
- Endpoint không có LLM, nên không có rủi ro prompt injection. PII: không trả `buyer_id` ra FE.

### 4.6 Benchmark và kiểm chứng
- **Metric:** NDCG@20 và precision@20 so với top 20 thật của kỳ sau, tính theo từng danh mục rồi lấy trung bình. Kèm độ phủ của khoảng 80% (tỉ lệ số bán thật nằm trong khoảng).
- **Baseline:** B0 (code hiện tại, precision@20 khoảng 0.39 theo lần đo nhanh) và B1.
- **CI:** bootstrap ghép cặp theo cụm seller, 1,000 lần, trên chênh lệch M1 trừ B0.
- **Cổng "đạt":** M1 hơn B0 ở NDCG@20 trên test với CI không chứa 0, và độ phủ khoảng 80% nằm trong [0.75; 0.85].
- **Không thắng thì sao:** ghi thẳng "đếm thô tốt ngang EB trên Olist", giữ B0 nhưng vẫn hiện khoảng thứ hạng. Phần trung thực về độ bất định vẫn có giá trị cho seller.
- Công bố số lần đã đọc test, như Listing Intel đã làm.

## 5. Lộ trình

| Giai đoạn | Việc | Kết quả kiểm chứng |
|---|---|---|
| Ngay 1–2 ngày | Sửa #1, #2 (không in "bán chạy nhất" khi 0 đơn; phân vị bỏ chính mình); phá hoà theo BR-188; thống nhất K; bỏ ngưỡng 5 và thay bằng cờ `low_sample` | Test mới: danh mục toàn 0 đơn không có câu "bán chạy nhất"; hai listing hoà thì listing nhiều review đứng trước |
| 1–2 tuần | Job đêm và mart live (BR-187); 3 biểu đồ Recharts (BR-189); `my_listings` đủ cột; script `scripts/f32/backtest_olist.py` với B0, B1, M1 | Bảng NDCG@20 và precision@20 kèm CI; sanity xáo nhãn; test giờ cập nhật bằng giờ job |
| 1–2 tuần | Lọc tự mua và giới hạn theo buyer; mô phỏng bơm đơn giả | Chi phí leo top trước và sau |
| Khi có dữ liệu thật | Backtest hằng tháng trên VietCraft; fit prior theo danh mục lá | NDCG@20 theo tháng, cảnh báo drift |

**Xong khi:**
- M1 thắng B0 có CI trên test Olist, hoặc báo cáo ghi rõ là không thắng;
- FE không bao giờ gọi sản phẩm 0 đơn là bán chạy;
- khoảng thứ hạng hiện trên bảng;
- khớp các BR và endpoint của mục SRS 3.9.1: `GET /api/analytics/competitors?categoryId=`; BR-186 (dropdown chỉ danh mục có listing đang bán, cả seed); BR-187 (job ngày, mốc là giờ quét); BR-188 (doanh số ước lượng giảm dần, hoà thì theo số review); BR-189 (loại shop mình khỏi top 20, vẽ chồng trên 3 biểu đồ); MSG136, MSG137; dưới 20 đối thủ thì hiện số đang có.

## 6. Hội đồng sẽ hỏi

- **"Sàn có 4 đơn thì xếp hạng cái gì?"** Hiện tại đang xếp theo thứ tự đăng bài, và đó là lỗi. Bản sửa nói thẳng "chưa đủ đơn" và hiện khoảng thứ hạng rộng. Kiểm chứng được làm trên Olist, nơi có panel thật.
- **"EB có hơn đếm thô không?"** Chưa biết, phải chạy backtest. Baseline đếm thô đạt precision@20 khoảng 0.39 trong lần đo nhanh. Nếu không vượt được có CI thì nhóm sẽ báo là không vượt.
- **"Sao không dùng embedding để tìm đối thủ thật?"** Vì đăng ký là "in-category". Embedding chỉ dùng để bắt khai sai danh mục và làm cột phụ, không đổi thứ hạng.
- **"Seller tự mua để leo top thì sao?"** Bỏ đơn của chủ shop, đếm theo buyer phân biệt, có giới hạn mỗi buyer. Hiệu quả đo bằng chi phí leo top trong mô phỏng.
- **"Olist là Brazil, áp cho Việt Nam được không?"** Olist chỉ dùng để kiểm phương pháp xếp hạng khi dữ liệu thưa, không dùng để chuyển tham số sang. Prior được fit lại trên VietCraft khi có đơn.
