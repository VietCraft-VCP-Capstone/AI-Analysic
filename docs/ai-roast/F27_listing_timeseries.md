# F27 Biểu đồ theo thời gian của từng sản phẩm: roast và đường ra

> Endpoint `GET /api/analytics/listings/{id}/timeseries` (BE proxy `GET /api/seller/analytics/listings/:id/timeseries`) · Trang FE "Sức khoẻ sản phẩm", thẻ "Mỗi ngày có bao nhiêu người xem" (`FE/src/modules/analytics/components/listing/DailyCards.tsx`) · File chính `app/api/v1/f27_listing_timeseries.py`, `app/api/v1/_live_listing.py` · Ngày 2026-10-21 · Người viết: Claude (subagent)

## 0. Bản đăng ký nói gì

| Hạng mục | SRS 3.8.2 Per-listing Time-series Charts |
|---|---|
| Actor, trigger | Seller đã đăng nhập; bấm một listing trong bảng analytics, mở `SellerListingAnalyticsPage` |
| Endpoint | `GET /api/analytics/listings/{listingId}/timeseries`, Bearer JWT |
| Input | `listingId` (URL), `timeRange` (7/30/90 ngày) |
| Output | Chuỗi ngày views, add-to-cart, orders, revenue và nhãn xu hướng tăng/giảm |
| Xử lý | BE gom số liệu theo ngày của listing; module Python tính độ dốc hồi quy tuyến tính trên cửa sổ để tự phát hiện xu hướng |
| BR-177 | Seller chỉ xem analytics của listing mình sở hữu |
| BR-178 | Gắn cờ tăng/giảm khi độ dốc tăng trưởng vượt ±5% "over the selected window" |
| Validation | Lỗi tải: retry (MSG130). Sai `listingId`: trang 404. Không có dữ liệu: đường phẳng kèm tooltip "No data" (MSG152) |
| Màn hình | Breadcrumb [Analytics] > [Tên SP], ảnh + tên ở sidebar, nút 7/30/90 ngày, line chart, **badge mũi tên tăng/giảm** |

SRS gọi đây là "AI module" nhưng bản chất là hồi quy tuyến tính. Đó là thống kê mô tả, và nên giữ như vậy.

## 1. Roast: code hiện tại thực chất là gì

- Cả "AI" của F27 là hàm `_xu_huong` 13 dòng (`f27_listing_timeseries.py:21-33`): độ dốc OLS chia trung bình, so với hằng số 5. Không kiểm định, không khoảng tin cậy, không mô hình đếm. Gọi là AI thì hơi ngáo, nhưng SRS cũng chỉ đòi tới đó.
- Comment `NGUONG_DOC = 5.0  # BR-178: ±5% mỗi ngày` (`:18`) đọc sai luật. BR-178 nói ±5% **trên cả cửa sổ**, code lại hiểu thành ±5% **mỗi ngày**. Ở cửa sổ 30 ngày, ngưỡng thành 150%. Ở 90 ngày, ngưỡng thành 450%. Đọc spec kiểu đéo gì vậy.
- Tao chạy chính `_xu_huong` trên dữ liệu giả lập có đáp án:
  - 7 ngày, chỉ 1 lượt xem vào ngày cuối → `("up", 75.0)`. Một người click là thành "đang tăng 75%/ngày".
  - Chuỗi Poisson(0,3)/ngày không đổi trong 30 ngày (đúng kiểu listing đuôi) → 21,9% số lần bị gắn up/down, dù không có gì thay đổi.
  - Lượt xem tăng gấp đôi trong 90 ngày → `flat` (0,73%/ngày). Lượt xem tụt 70% giữa kỳ 90 ngày → `flat` (-1,86%/ngày).
  - Kết quả: sai cả hai chiều. Nhiễu thì báo có xu hướng, thay đổi thật thì báo phẳng. Vl.
- Đọc BR-178 theo nghĩa đen (5% trên cửa sổ, không kiểm định) cũng không cứu được. Cũng phép thử đó gắn cờ 55–95% chuỗi đứng yên. Luật này thiếu điều kiện có ý nghĩa thống kê, nên phải ghi vào phụ lục SRS.
- `category_median` trên seed thực ra là `$avg` (`:79`). Trung bình đó chỉ tính trên những listing có dòng trong ngày, mà listing tier tail chỉ có dòng vào ngày có hoạt động (`app/seed/behavior/task9_listing_daily.py:131-132`). Vừa sai tên, vừa thổi phồng mức nền danh mục.
- Trên seed, chuỗi của listing tail có lỗ hổng ngày (không điền 0). `_xu_huong` lại hồi quy theo chỉ số mảng chứ không theo ngày thật (`:92-93`). FE thì ghép đường danh mục theo chỉ số `i`, không theo ngày (`DailyCards.tsx:41`). Hai đường trên biểu đồ có thể lệch ngày nhau mà không ai biết.
- Badge xu hướng mà SRS đòi thì FE đéo hiển thị: không component nào trong `FE/src/modules/analytics` đọc `trend` của F27 (chỉ có kiểu ở `types.ts:110`). Backend tính một nhãn sai, rồi FE cũng không dùng.
- Test có 2 cái, chỉ kiểm hình dạng và quyền sở hữu (`tests/test_live_paths.py:71-79`). Không có test nào kiểm nhãn xu hướng đúng hay sai.

### Lệch bản đăng ký

| Điểm | SRS | Code | Mức |
|---|---|---|---|
| BR-178 | ±5% trên cả cửa sổ | ±5% mỗi ngày (`:18`, `:33`) | Nặng |
| Badge xu hướng | Bắt buộc có trên màn hình | FE không render `trend` | Nặng |
| Chỉ số có xu hướng | views, add-to-cart, orders, revenue | Chỉ views và orders (`:92-93`) | Nặng |
| Trang | `SellerListingAnalyticsPage` + breadcrumb | Thẻ trong trang "Sức khoẻ sản phẩm" | Nặng |
| Không có dữ liệu | Đường phẳng + tooltip MSG152 | `data: null` + insufficient (`:68-71`, `_live_listing.py:38-39`) | Nặng |
| timeRange | 7/30/90 | Có đủ 7/30/90; nhận thêm 180d/365d/1y (`app/api/v1/_mart.py:40`), không vi phạm | Đạt |
| BR-177 | Chỉ chủ listing | Đúng: `forbidden()` (`:50-51`, `_live_listing.py:20-21`) | Đạt |

## 2. Mổ xẻ lỗi

| # | Mức | Chỗ | Lỗi | Hậu quả | Sửa nhanh |
|---|---|---|---|---|---|
| 1 | Nặng | `f27_listing_timeseries.py:18,33` | Lệch BR-178: ngưỡng hiểu thành %/ngày | Cửa sổ 30/90 ngày gần như luôn `flat` | Đổi thành tăng trưởng trên cửa sổ: `slope·(n-1)/mean` |
| 2 | Nặng | `:21-33` | Không kiểm định thống kê | 1 click thành "up 75%" | Thêm điều kiện CI của độ dốc không chứa 0 (mục 4.3) |
| 3 | Nặng | FE `DailyCards.tsx` | Không có badge xu hướng | Thiếu màn hình đã đăng ký | Render `trend.views/orders` kèm p-value |
| 4 | Nặng | `:92-93` | Thiếu xu hướng carts và revenue | Thiếu output đã đăng ký | Gọi `_xu_huong` cho cả 4 chỉ số |
| 5 | Vừa | `:79`, `:86` | `$avg` nhưng đặt tên `category_median` | Sai nhãn, nền danh mục bị thổi phồng | Điền 0 theo lưới ngày rồi lấy trung vị thật |
| 6 | Vừa | `:58-61`, `:92` | Seed tail có lỗ ngày, hồi quy theo chỉ số | Độ dốc sai trục thời gian | Điền 0 theo ngày trước khi hồi quy |
| 7 | Vừa | `DailyCards.tsx:41` | Ghép đường danh mục theo chỉ số mảng | Hai đường lệch ngày | Ghép theo `date` |
| 8 | Vừa | `_live_listing.py:44` | Trung vị live chỉ tính listing có ≥1 view | Mức "thường gặp" bị đẩy lên | Tính trên mọi listing đang bán cùng danh mục |
| 9 | Vừa | `_live_data.py:10,105-110` | Đơn chưa thanh toán vẫn tính doanh thu | Lệch với F37 (chỉ PAID, `_live_data.py:117`) | Thống nhất một định nghĩa doanh thu |
| 10 | Nhẹ | `:66` | `confidence` theo số dòng, không theo số sự kiện | 30 ngày toàn 0 vẫn "high" | Theo tổng views/orders như `_live_listing.py:29` |
| 11 | Nặng | `:68-71`, `_live_listing.py:38-39` | Lệch MSG152: không có dữ liệu thì trả `data: null` thay vì đường phẳng + "No data" | Khác hành vi đã đăng ký | Trả chuỗi 0 kèm cờ `no_data` |

Lệch bản đăng ký trong bảng này là #1, #3, #4 và #11. Chi tiết từng điểm ở bảng "Lệch bản đăng ký" của mục 1.

## 3. Tính năng này nên là AI gì

Seller cần biết listing này đang lên hay xuống, và có chắc không. Đây là bài toán **kiểm định xu hướng trên chuỗi đếm thưa**, không phải bài toán học máy có nhãn.

- **Giữ đúng hợp đồng SRS:** cùng endpoint, input, 4 chuỗi ngày, BR-177, và hồi quy độ dốc như BR-178.
- **Lớp thống kê bắt buộc:** hồi quy Poisson hoặc Negative Binomial `count ~ t` (statsmodels có sẵn). Tăng trưởng trên cửa sổ là `exp(β·(n-1)) - 1`. Badge chỉ bật khi đồng thời:
  - |tăng trưởng| > 5% (BR-178);
  - khoảng tin cậy 95% của β không chứa 0.
  Điều kiện thứ hai là phần thêm vào. **Cần cập nhật SRS/phụ lục BR-178**, vì nếu thiếu nó thì luật gắn cờ 55–95% chuỗi đứng yên (đã đo ở mục 1).
- **Lớp "AI" đáng làm (tuỳ chọn):** phát hiện điểm gãy (changepoint), để nói "lượt xem đổi mức từ ngày X". Hồi quy tuyến tính không thấy được kiểu đổi mức này, như ví dụ tụt 70% giữa kỳ ở mục 1. `ruptures` **chưa cài** (đã kiểm `import ruptures` lỗi), nên phải tự viết PELT với chi phí Poisson hoặc CUSUM, khoảng 60 dòng numpy. Chỉ đưa lên UI nếu thắng baseline ở mục 4.6.
- Không dùng ML có giám sát: không có nhãn "xu hướng thật", và cũng không cần.

## 4. Đường ra: thiết kế AI chính hiệu

### 4.1 Dữ liệu: train / validation / test / thực

| Tập | Nguồn | Dùng để |
|---|---|---|
| Chuỗi nền thật | Olist `olist_order_items` + `olist_orders`, đếm đơn theo `product_id` × ngày (2017-01 → 2018-08) | Chuỗi đếm thưa thật để cấy xu hướng hoặc điểm gãy |
| Chuỗi views thật | Retailrocket events (Kaggle; giấy phép và kích thước **cần xác minh**, bản gốc không có trong máy) | Kiểm trên chuỗi lượt xem, vì Olist không có views |
| Hiệu chỉnh (dev) | 50% product Olist, chia theo `seller_id` (GroupShuffleSplit như Listing Intel) | Chọn ngưỡng PELT, kiểu chi phí |
| Test | 50% còn lại, chỉ đọc một lần, ghi số lần đọc | Báo cáo cuối |
| Thực | `product_events` + `orders` live | Theo dõi tỉ lệ badge; chưa đủ để đánh giá |

- Seed `listing_daily` **không được dùng làm bằng chứng**: views được sinh bằng `nền × mùa vụ × thứ × tuổi` (`app/seed/behavior/task6_events.py:184-187`). Đo trên đó chỉ là đo lại công thức sinh.
- Cấy nhãn: lấy đoạn chuỗi Olist đứng yên (đoạn khớp giả thuyết H0 qua block-permutation), rồi nhân với ramp `1+g·t/n` (g ∈ {±20%, ±50%, ±100%}) hoặc bước nhảy mức tại ngày ngẫu nhiên. Nhãn = (g, vị trí gãy).

### 4.2 Làm sạch và sanity

- Điền 0 theo lưới ngày (VN GMT+7) trước mọi phép tính. Chặn `listingId` không phải ObjectId thì trả 404 (đã có `oid()` trả None).
- Một định nghĩa doanh thu chung cho F27, F30, F37: đơn PAID, trừ CANCELLED.
- Sanity bắt buộc, viết thành pytest:
  - chuỗi hằng 0 → `flat`, không có p-value;
  - 1 view ngày cuối → **không** badge;
  - Poisson đứng yên → tỉ lệ badge ≤ 5% ± sai số mô phỏng;
  - ramp +100%/30 ngày với λ ≥ 2 → badge `up`;
  - đường danh mục và chuỗi listing cùng ngày.

### 4.3 Model

| Bước | Phương pháp | Vai trò |
|---|---|---|
| Baseline 1 | OLS hiện tại, ngưỡng BR-178 theo cửa sổ | Mốc theo đúng chữ SRS |
| Baseline 2 | So trung bình nửa đầu với nửa sau (tỉ số Poisson, kiểm định exact) | Mốc rẻ, dễ giải thích |
| Chính | GLM Poisson/NB + CI Wald hoặc profile; NB khi phương sai lớn hơn trung bình | Badge |
| Tuỳ chọn | PELT tự viết, chi phí Poisson, phạt BIC | Ghi chú "đổi mức từ ngày X" |

Toàn bộ chạy CPU, mỗi chuỗi 7–90 điểm, dưới 10 ms. Không cần torch.

### 4.4 Học từ dữ liệu thật

- Ở đây không có trọng số để retrain. Cái cần "học" là tham số hiệu chỉnh: hệ số phạt PELT và ngưỡng phân tán NB, chỉnh lại mỗi quý trên dữ liệu live đã tích luỹ.
- Ghi log mỗi lần FE hiện badge (`listing_id`, nhãn, p, g). Khi seller có thao tác như sửa giá hay ảnh, đối chiếu ngày đổi mức với ngày sửa. Đây là nguồn nhãn yếu, miễn phí cho changepoint.
- Cold start: listing dưới 7 ngày hoặc tổng views dưới 20 → không badge, hiện MSG152 hoặc "chưa đủ dữ liệu", đúng SRS.
- Drift: theo dõi tỉ lệ badge theo tuần. Nếu vượt 3 lần mức đo ở test, kiểm lại pipeline sự kiện trước khi nghi model.

### 4.5 Bảo mật và chống gian lận

- BR-177: giữ kiểm `shop_id` ở cả nhánh seed và live (đã có). Thêm test cho nhánh seed.
- Bơm view ảo để tạo badge `up`, nhằm khoe hoặc đẩy F29: lọc session trùng, bot user-agent, nhiều view cùng IP trong thời gian ngắn ở BE trước khi ghi `product_events`. Chạy kiểm định trên views đã lọc.
- Không trả về danh tính listing của shop khác trong đường danh mục. Chỉ trả trung vị, và chỉ khi có ≥ 5 listing (k-anonymity tối thiểu).
- Không có LLM, nên không có prompt injection.

### 4.6 Benchmark và kiểm chứng

- **Metric:**
  - tỉ lệ badge giả trên chuỗi H0 (FPR);
  - power theo (g, λ, cửa sổ);
  - với changepoint: F1 với dung sai ±3 ngày, sai lệch vị trí trung vị.
- **Baseline:** OLS hiện tại (ngưỡng/ngày), OLS theo đúng chữ BR-178, và so nửa đầu/nửa sau.
- **CI:** bootstrap theo cụm `seller_id`, 1.000 vòng.
- **Cổng "đạt khi":**
  - FPR ≤ 5% (CI trên ≤ 7%) ở cả 7/30/90 ngày;
  - power ≥ 80% cho g = +100% / 30 ngày với λ ≥ 2/ngày;
  - PELT chỉ lên UI khi F1 cao hơn baseline "so nửa đầu/nửa sau" với CI ghép cặp không chứa 0.
- **Sanity xáo nhãn:** xáo thứ tự ngày trong mỗi chuỗi → power phải rơi về khoảng FPR.
- **Nếu không thắng:** công bố bảng FPR và power, giữ GLM có kiểm định, bỏ PELT, ghi vào Hạn chế. Không nói "AI phát hiện xu hướng".

## 5. Lộ trình

| Giai đoạn | Việc | Kết quả kiểm chứng |
|---|---|---|
| Ngay 1–2 ngày | Sửa ngưỡng BR-178 theo cửa sổ, điền 0 seed, đổi `$avg` thành trung vị, ghép FE theo ngày, render badge, xu hướng cho đủ 4 chỉ số | Pytest sanity mục 4.2 xanh |
| 1–2 tuần | GLM + CI; script `scripts/f27/bench_trend.py` cấy ramp/gãy vào Olist; PELT tự viết | Bảng FPR/power kèm CI; quyết định giữ hay bỏ PELT |
| Khi có dữ liệu thật | ≥ 50 listing live có ≥ 30 ngày views: đo tỉ lệ badge, đối chiếu ngày sửa listing | Tỉ lệ badge live nằm trong CI của test |

**Xong khi:**
- FPR ≤ 5% và power đạt cổng trên tập test Olist, có CI theo seller;
- badge hiện trên FE cho đủ views, carts, orders, revenue;
- khớp các BR và endpoint của mục SRS 3.8.2:
  - `GET /api/analytics/listings/{listingId}/timeseries` với `timeRange` 7/30/90;
  - BR-177 có test cho cả seed và live;
  - BR-178 tính ±5% trên cả cửa sổ;
  - MSG130 và MSG152 đúng hành vi;
- phụ lục SRS ghi thêm điều kiện ý nghĩa thống kê cho BR-178.

## 6. Hội đồng sẽ hỏi

1. **"Hồi quy tuyến tính mà gọi là AI à?"** Không phải AI, và bọn em không gọi nó là AI. Đó là kiểm định thống kê có đo FPR và power. Lớp changepoint chỉ lên UI nếu thắng baseline trên chuỗi Olist có nhãn cấy.
2. **"Sao lệch BR-178?"** Bản cũ hiểu sai thành %/ngày, và đó là lỗi. Bản sửa dùng đúng ±5% trên cửa sổ. Bọn em thêm điều kiện CI vì luật nguyên văn gắn cờ 55–95% chuỗi đứng yên (số đo ở mục 1). Phần thêm này cần cập nhật phụ lục SRS.
3. **"Kiểm chứng trên dữ liệu nào, seed à?"** Không. Seed sinh views bằng công thức, nên chỉ dùng để chạy demo. Kiểm chứng dùng chuỗi đơn Olist thật, cấy xu hướng có đáp án, chia theo seller.
4. **"Listing chỉ có vài view thì sao?"** Không đủ bằng chứng thì không bật badge. Nói "chưa đủ dữ liệu" vẫn trung thực hơn một mũi tên 75%.
