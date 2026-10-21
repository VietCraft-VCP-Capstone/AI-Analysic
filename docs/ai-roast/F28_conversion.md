# F28 Tỷ lệ chuyển đổi từng listing: roast và đường ra

> Endpoint `GET /api/analytics/listings/{id}/conversion` (BE proxy `GET /api/seller/analytics/listings/:id/conversion`) · Trang FE "Sức khoẻ sản phẩm" → chi tiết listing, thẻ phễu (`FE/src/modules/analytics/components/ListingTraffic.tsx`) · File chính `app/api/v1/f28_conversion.py`, `app/api/v1/_live_listing.py`, `app/core/build_marts.py:357-424`, tracking `FE/.../BuyerProductDetailPage.tsx:300-308`, `BE/.../event.service.ts`, `BE/.../cart.service.ts:160-170` · Ngày 2026-10-21 · Người viết: Claude (subagent)

## 0. Bản đăng ký nói gì

| Hạng mục | SRS 3.8.3 Conversion Rate Analysis (`report3.txt:4889-4940`) và UC-58 (`report3.txt:518-520`) |
|---|---|
| Actor, trigger | Seller đã đăng nhập; bấm tab [Tỷ lệ chuyển đổi] trên `SellerListingAnalyticsPage` |
| Endpoint | `GET /api/analytics/listings/{listingId}/conversion`, Bearer JWT |
| Input | `listingId` (URL param) |
| Output | CR của listing (đơn / lượt xem), CR trung bình danh mục, kết quả so sánh, danh sách mẹo |
| Xử lý | Tính CR listing; lấy CR trung bình danh mục từ cache; nếu thấp hơn từ 20% thì sinh mẹo "theo ngữ cảnh" |
| System data | `shopId`, số liệu trung bình danh mục trong Redis, số liệu listing |
| UC-58 | Seller xem CR toàn shop **và từng sản phẩm** theo kỳ ngày, tuần, tháng |
| BR-177 (3.8.2, áp cho mọi analytics listing) | Seller chỉ xem listing mình sở hữu |
| BR-179 | Chỉ sinh và hiện mẹo khi CR thấp hơn trung bình danh mục từ 20% trở lên |
| BR-180 | Trung bình danh mục cập nhật hằng ngày bằng batch job |
| Validation | 0 lượt xem → CR đặt 0%, kèm mẹo "Tăng cường quảng cáo để có lượt xem" (MSG153) |
| Abnormal 3.8.3.a1 | Cache thiếu trung bình danh mục → dùng trung bình toàn sàn |
| Màn hình | `ListingConversionPage.tsx`: gauge CR listing so với danh mục, dòng trạng thái kiểu "Thấp hơn 25%…", thẻ mẹo kiểu "Cải thiện hình ảnh mockup" |

## 1. Roast: code hiện tại thực chất là gì

- **"Phân tích chuyển đổi" thực chất là ba phép chia và một `if`** (`build_marts.py:393-424`). Đây là thống kê mô tả. Không sao, miễn là đừng gọi nó là AI.
- **Comment nói một đằng, code làm một nẻo.**
  - Dòng `:399` ghi: "không so hai bước với nhau vì thang khác hẳn".
  - Ngay dòng `:402` lại so đúng hai bước đó: `yeu = "view_to_cart" if v2c < c2o / 4 else "cart_to_order"`. Số 4 ở đâu ra thì không ai biết.
  - Với tỉ lệ Retailrocket mà seed dùng (v2c 2.60%, c2o 32.39%, `dist_funnel.json`), `c2o/4 = 8.1% > 2.6%`. Nghĩa là listing **trung bình** luôn bị kết luận yếu ở bước xem → giỏ. Khi `carts = 0`, code cũng rơi vào nhánh đó (`:403-404`).
  - Cho nên mẹo gần như lúc nào cũng là "Ảnh đầu tiên nên chụp sản phẩm đang được dùng thật". Viết comment để làm cảnh à, vl.
- **"Mẹo theo ngữ cảnh" mà SRS đăng ký chỉ là 2 câu đóng hộp** (`:408-414`). Ngữ cảnh duy nhất là chọn câu 1 hay câu 2.
- **Ngưỡng 30 lượt xem biến nhiễu thành lời khuyên.**
  - Retailrocket có 22,457 giao dịch trên 2,664,312 lượt xem, tức khoảng 0.84% mỗi lượt xem (tao đếm từ `events.csv`).
  - Một listing đúng bằng trung bình, có 30 lượt xem, sẽ có xác suất ra 0 đơn là `(1−0.0084)^30 ≈ 78%`.
  - 0 đơn nghĩa là `cr_index = 0 ≤ 0.8`, và mẹo bật lên.
  - Gần 4/5 listing hoàn toàn bình thường bị bảo "thấp hơn danh mục từ 20%". Ở 100 lượt xem vẫn còn khoảng 43%. Đây là máy phát lời khuyên ngẫu nhiên, ngáo thật sự.
- **Trên seed thì F28 là vòng tròn hoàn hảo.**
  - Mọi listing seed dùng **cùng một** xác suất thêm giỏ (`task6_events.py:77-80`, `:155`, `:202`) và **cùng một** xác suất đặt hàng (`task7_orders.py:93`, `:105`).
  - Vậy mọi khác biệt giữa các listing chỉ là nhiễu nhị thức. "Listing yếu" là listing gieo xúc xắc xui. F28 chỉ trả lại đúng tham số nhập tay.
  - Tài liệu seed còn tự mâu thuẫn. `SEED_PARAMS.md:27` ghi view→cart 6.45%, còn `dist_funnel.json` lưu trữ (Retailrocket) ghi 2.60%. Số 6.45 trùng với `MUC_NEN_THEO_TIER["hot"]` (`task6_events.py:56`), mà đó là lượt xem mỗi ngày, không phải tỉ lệ. Cần xác minh seed thật sự đã dùng file nào.
- **Mốc danh mục có chứa chính listing đang được so** (`_live_listing.py:54-58`): `cung` gồm cả `pid`, và `moc` cộng mọi phần tử của `tong`. Danh mục có 2 sản phẩm thì listing chiếm một nửa cái mốc dùng để so nó.
  - Danh mục lấy `categories[0]`, là chữ tự do (`_live_data.py:56-57`). F29 thì lấy `category_ids[0]` (`scoring.py:37-39`). Hai tính năng, hai định nghĩa danh mục.
  - Ngưỡng cũng lệch nhau: F28 cần 30 lượt xem trong 90 ngày (`f28:18`, `_live_listing.py:12`), F29 cần 100 lượt xem trong 30 ngày (`f29/constants.py:23-24`).
- **Phễu không lồng nhau.**
  - "Mua ngay" đi thẳng tới checkout, không qua giỏ (`BuyerProductDetailPage.tsx:532-533`), nên đơn có thể không có sự kiện `add_to_cart` nào đi trước. `cart_to_order_pct` vì thế có thể vượt 100%.
  - Ngay cả Retailrocket cũng có 2,225/21,270 cặp (người, sản phẩm) đã mua (10.5%) mà không có `addtocart` (tao đếm).
  - "Đơn" ở đây gồm cả đơn chưa trả tiền và đơn đã hoàn (`_live_data.py:10`, `:66-73`, `:86-89`), trong khi F26 chỉ tính PAID.
- **Tracking có thật, nhưng có lỗ.**
  - Endpoint `POST /api/analytics/events/add-to-cart` công khai, chỉ `optionalAuthenticate`, và `session_id` do client tự gửi (`analytics.router.ts:34-58`). Rate-limit chỉ áp cho `view` (`event.service.ts:65`).
  - Ai cũng bơm được sự kiện giỏ hàng không giới hạn, chỉ cần đổi `session_id`. FE còn không dùng endpoint này: FE chỉ gọi view (`eventService.ts:23`), còn add-to-cart đã được ghi ở phía server (`cart.service.ts:160-170`). Endpoint thừa mà để mở toang, đéo hiểu.
  - Mọi `event_type` khác `view` đều bị đếm là giỏ (`_live_data.py:85`).
- **Ghi nhận điểm tốt.**
  - Lượt xem được ghi thật từ trang sản phẩm (`BuyerProductDetailPage.tsx:300-308`).
  - BE lọc bot theo user-agent, lọc chủ shop đã đăng nhập, giới hạn 10 view/phút/IP và chống trùng 30 phút (`event.service.ts:21-95`).
  - Add-to-cart được ghi ở phía server sau khi lưu giỏ.
  - BR-177 được chặn ở cả hai nhánh (`f28:30-31`, `_live_listing.py:15-22`).
  - `_phan_tram` trả `None` thay vì 0 khi chưa ai xem (`build_marts.py:357-360`).
  - Ngưỡng BR-179 `≤ 0.8` đúng nghĩa.
- **Test:** có 2 test (`tests/test_live_paths.py:59-68`), chỉ kiểm số đếm phễu và nhánh thiếu dữ liệu. Không test nào kiểm mẹo, bước yếu hay mốc danh mục.

### Lệch bản đăng ký

| Điểm | SRS | Code | Mức |
|---|---|---|---|
| UC-58: CR từng sản phẩm theo ngày/tuần/tháng | Có | Cố định 90 ngày (`_live_listing.py:12`, `:53`); BE không truyền query (`seller-analytics.router.ts:33`) | Chết người |
| Validation 0 lượt xem | CR 0% + MSG153 | Dưới 30 lượt xem trả `insufficient`, `data: null` (`f28:45-48`, `_live_listing.py:62-65`); FE hiện dòng "đang thu thập" (`ListingTraffic.tsx:40`); grep MSG153 = 0 kết quả | Nặng, cần cập nhật SRS cho phần "0%" |
| BR-180 batch hằng ngày | Mốc danh mục lấy từ cache, cập nhật mỗi ngày | Live tính lại mỗi request, không cache (`_live_listing.py:54-58`); seed dựng trong `build_marts` nhưng lịch chạy cần xác minh | Nặng |
| 3.8.3.a1 fallback | Thiếu mốc danh mục → dùng mốc toàn sàn | Không có listing cùng danh mục → `moc = None`, không có mẹo, không fallback (`_live_listing.py:57-58`) | Nặng |
| Mẹo theo ngữ cảnh | Theo ngữ cảnh | 2 câu cố định (`build_marts.py:408-414`) | Nặng |
| Màn hình | `ListingConversionPage`, gauge, tab riêng | `FunnelCard` nằm trong trang chi tiết listing (`ListingTraffic.tsx:46`), không có gauge | Nặng |
| Bước yếu nhất | Không đăng ký | Luật `v2c < c2o/4` tự đặt thêm | Bổ sung ngoài SRS, không tính là lệch; nếu giữ thì ghi vào phụ lục |

## 2. Mổ xẻ lỗi

Dòng có nhãn **[Lệch SRS]** là phần lệch bản đăng ký, xếp mức Chết người hoặc Nặng.

| # | Mức | Chỗ | Lỗi | Hậu quả | Sửa nhanh |
|---|---|---|---|---|---|
| 1 | Chết người | `build_marts.py:408`, `f28:18` | Bật mẹo dựa trên CR thô với 30 lượt xem | Khoảng 78% listing trung bình bị bảo là yếu | Chỉ bật mẹo theo hậu nghiệm Bayes (mục 4.3) |
| 2 | Chết người | `analytics.router.ts:34-58` | Endpoint add-to-cart công khai, không rate-limit | Bơm giỏ tuỳ ý, phá phễu của shop bất kỳ | Gỡ route (FE không dùng), hoặc bắt buộc auth và rate-limit |
| 3 | Chết người | UC-58 | [Lệch SRS] Không có CR theo kỳ ngày/tuần/tháng | Lệch chức năng đã đăng ký | Thêm `by_period` (mục 4.3) |
| 4 | Nặng | `build_marts.py:399-404` | Luật `c2o/4` trái với chính comment | Bước yếu gần như luôn là xem → giỏ | So từng bước với prior của danh mục ở cùng bước |
| 5 | Nặng | `_live_listing.py:54-58` | Mốc danh mục có chứa chính listing | Mốc bị kéo về phía listing | Loại `pid` khỏi mốc |
| 6 | Nặng | `_live_listing.py:57-58` | [Lệch SRS] Không fallback mốc toàn sàn | Vi phạm 3.8.3.a1 | `moc = cat or platform`, kèm `benchmark_scope` |
| 7 | Nặng | `_live_listing.py:55` | [Lệch SRS] Tính mốc mỗi request, không có batch | Vi phạm BR-180, chậm | Batch hằng ngày ghi `cr_category_prior` |
| 8 | Nặng | `f28:45-48` | [Lệch SRS] 0 lượt xem → `insufficient` | Không có MSG153 | Trả 200, `cr: null`, `display: "0%"`, mẹo MSG153 |
| 9 | Nặng | `_live_data.py:10` so với `_live_overview.py:15` | F28 và F26 định nghĩa "đơn" khác nhau | CR không đối chiếu được | Hàm định nghĩa đơn dùng chung |
| 10 | Nặng | `BuyerProductDetailPage.tsx:532` | Mua ngay bỏ qua giỏ | `c2o` > 100%, phễu sai | Ghi sự kiện `checkout_start`; tính v2o trực tiếp |
| 11 | Vừa | `analytics.router.ts:9`, `event.service.ts:79` | `session_id` do client tự cấp | Đổi session là lách được chống trùng | Session ký ở server (cookie httpOnly) |
| 12 | Vừa | `_live_data.py:56-57` và `scoring.py:37-39` | Hai định nghĩa danh mục | F28 và F29 so với hai mốc khác nhau | Dùng `category_ids` cho cả hai |
| 13 | Vừa | `_live_data.py:85` | Event không phải view → bị đếm là giỏ | Đếm sai khi thêm loại event mới | So khớp đúng `add_to_cart` |
| 14 | Nhẹ | `SEED_PARAMS.md:27` | Ghi 6.45% trong khi file Retailrocket ghi 2.60% | Tài liệu sai | Đối chiếu lại file seed thật |
| 15 | Nặng | `build_marts.py:408-414`, `ListingTraffic.tsx:46` | [Lệch SRS] Mẹo là 2 câu cố định; không có gauge hay tab riêng | Lệch "mẹo theo ngữ cảnh" và màn hình | Mẹo lấy từ tín hiệu Listing Intel (mục 3); thêm gauge |

## 3. Tính năng này nên là AI gì

**Bài toán seller cần:** "Listing của tôi chuyển đổi kém **thật**, hay chỉ là chưa đủ người xem? Nếu kém thật thì kém ở bước nào, và nên sửa gì?"

**Định nghĩa.** Mỗi listing i có xác suất mua thật trên mỗi lượt xem là θᵢ; ta quan sát kᵢ đơn trên nᵢ lượt xem.
- Model: Beta-Binomial empirical Bayes. Prior Beta(α_c, β_c) theo danh mục c, fallback sang prior toàn sàn, đúng tinh thần 3.8.3.a1.
- Output:
  - `cr_posterior_mean`, `cr_ci90`;
  - `p_below_80` = P(θᵢ ≤ 0.8·μ_c);
  - `cr_raw` (để giữ đúng định nghĩa đơn / lượt xem của SRS);
  - `category_avg`, `benchmark_scope`.
- Nhãn để kiểm chứng: CR thật ở **kỳ sau**, trên dữ liệu không dùng khi ước lượng.

**Các phần còn lại:**
- **BR-179 giữ nguyên nghĩa.** Mẹo chỉ hiện khi `cr_posterior_mean ≤ 0.8·μ_c` **và** `p_below_80 ≥ 0.8`. Điều kiện thêm làm luật chặt hơn, nên vẫn thoả "ONLY if" của BR-179.
- **Bước yếu.** Mỗi bước (xem → giỏ, giỏ → đơn) có prior riêng theo danh mục. Bước yếu là bước có `p_below` cao nhất **so với danh mục ở cùng bước**, đúng như comment `:399` từng hứa. Riêng v2o luôn tính trực tiếp, vì phễu không lồng nhau.
- **Mẹo theo ngữ cảnh** lấy từ tín hiệu Listing Intel đã có, không viết thêm câu đóng hộp:
  - Bước xem → giỏ yếu và ảnh kém → mẹo về ảnh (trục ảnh LI).
  - Giá trên trung vị kNN → mẹo về giá (`knn_price_pct`).
  - Thiếu chất liệu → mẹo về thuộc tính (lexicon chất liệu).
  - Bước giỏ → đơn yếu → mẹo về phí ship và thời gian giao.
- **UC-58.** Thêm `by_period` (ngày, tuần, tháng), mỗi ô có hậu nghiệm riêng. Ô ít lượt xem sẽ co mạnh về mốc, nên không vẽ ra răng cưa nhiễu.

## 4. Đường ra: thiết kế AI chính hiệu

### 4.1 Dữ liệu: train / validation / test / thực

| Nguồn | Dùng cho | Chia |
|---|---|---|
| Retailrocket `events.csv`: 2,756,101 event (2,664,312 view, 69,332 addtocart, 22,457 transaction), 1,407,580 visitor, 235,061 item, từ 2015-05-03 đến 2015-09-18 (tao đếm từ bản local ở `SE16-AI/data-collections-archive(do not touch)/external/funnel/`) | Benchmark chính | Theo thời gian. Ước lượng trước 2015-08-01 (12,942 item có ≥ 30 view, trong đó 12,326 item còn được xem sau mốc); trong phần trước mốc, giữ 2 tuần cuối làm validation để chọn prior; test từ 2015-08-01 trở đi |
| Retailrocket `item_properties` và `category_tree` | Prior theo danh mục | Chưa có bản local, cần tải từ Kaggle. Khi chưa có thì chỉ chạy prior toàn sàn |
| Seed VietCraft | **Chỉ** để kiểm null (mọi listing cùng θ) | Không bao giờ dùng làm bằng chứng độ chính xác |
| VietCraft live | Chạy thật | Ước lượng prior hằng ngày theo BR-180 |

- Không sửa thư mục archive. Khi dựng pipeline thì copy file sang thư mục dữ liệu riêng.
- Chuyển prior từ Retailrocket sang VietCraft khi danh mục có ít nhất 20 listing với ≥ 30 lượt xem. Trước đó dùng prior toàn sàn VietCraft, và nếu vẫn chưa đủ thì dùng prior Retailrocket có gắn nhãn `prior_source`.

### 4.2 Làm sạch và sanity

- **Tracking:**
  - Gỡ hoặc khoá endpoint add-to-cart công khai.
  - `session_id` do server ký.
  - Rate-limit theo session và theo sản phẩm.
  - Lọc chủ shop cả khi chưa đăng nhập (bằng cookie thiết bị).
  - Event lạ không được tính vào giỏ.
- **Định nghĩa đơn dùng chung với F26**: PAID, không hoàn, không huỷ. Đơn "Mua ngay" tính thẳng vào v2o.
- **Sanity bắt buộc:**
  - Hậu nghiệm luôn nằm giữa CR thô và mốc.
  - n = 0 thì hậu nghiệm bằng mốc, `cr_raw = null`, `display = "0%"`, mẹo MSG153.
  - `ci90` thu hẹp lại khi n tăng.
  - Mốc không chứa chính listing.
  - α, β > 0.
- **Null test trên seed:** vì seed dùng cùng θ cho mọi listing, tỉ lệ listing bị gắn cờ "yếu" phải ≤ 5%. Luật thô hiện tại được đo cùng lúc để so.
- **Xáo nhãn:** xáo đơn giữa các item rồi chạy lại thì EB phải co gần hết về mốc.

### 4.3 Model

1. **Baseline:**
   - B0: CR thô, kẹp ở `[1e-6, 1−1e-6]` để log-loss không vô cực.
   - B1: Laplace (cộng 1 đơn, cộng 2 lượt xem).
   - B2: mốc toàn sàn cho mọi item.
2. **Model chính:** Beta-Binomial EB.
   - Ước lượng α, β theo từng danh mục bằng cực đại likelihood biên (`scipy.optimize` trên `betabinom`; venv có scipy 1.18.1).
   - Dùng lại tinh thần co Bayes mà F29 đã làm cho rating (`K_BAYESIAN_SHRINKAGE`, `f29/constants.py:18`; `calculator.py:100-104`). Khác ở chỗ prior được **ước lượng** từ dữ liệu, không đặt tay.
3. **Phân cấp hai tầng** (danh mục → toàn sàn): làm sau, chỉ khi EB một tầng thua trên validation.
4. **`by_period`:** áp cùng prior cho từng ô ngày, tuần, tháng.

Tất cả là công thức đóng cộng một bước tối ưu nhỏ, chạy trên CPU trong vài mili giây.

### 4.4 Học từ dữ liệu thật

- **Batch hằng ngày (BR-180):** ước lượng lại α, β theo danh mục, ghi vào `cr_category_prior {category, alpha, beta, n_listings, as_of}`. BE có thể cache sang Redis như SRS ghi.
- **Cold start:** EB tự xử lý được. Listing mới nhận mốc kèm khoảng rộng, và không có mẹo cho tới khi `p_below_80 ≥ 0.8`.
- **Theo dõi:**
  - Mốc danh mục theo tuần.
  - Độ phủ `ci90` khi so với CR của kỳ sau (mục tiêu khoảng 90%).
  - Tỉ lệ listing bị gắn cờ.
- **Phản hồi:** log mẹo đã hiện, thay đổi seller đã làm (ảnh, giá), và CR 30 ngày sau. Đây chỉ là dữ liệu quan sát, không chứng minh mẹo gây ra thay đổi. Muốn biết nhân quả thì phải A/B thứ tự mẹo khi có đủ shop.

### 4.5 Bảo mật và chống gian lận

- **Phá đối thủ:** bơm view vào listing đối thủ thì CR của họ tụt và mẹo, điểm sức khoẻ của họ cũng xấu theo. Chặn bằng cách:
  - giới hạn số view mỗi IP/session trên một sản phẩm mỗi ngày;
  - loại view không có thời gian ở lại trang;
  - gắn cờ listing có lượt xem tăng vọt mà chỉ từ ít IP.
- **Tự thổi CR:** đơn tự mua, hoặc đơn để PENDING rồi bỏ. Chỉ tính đơn PAID, bỏ người mua trùng chủ shop.
- **Bơm giỏ qua endpoint công khai:** gỡ endpoint, hoặc bắt buộc auth.
- **BR-177:** giữ `forbidden()`. Thêm test: shop A đọc listing của shop B → 403.
- Không có LLM. Nếu sau này dùng LLM để viết mẹo thì tên và mô tả sản phẩm là dữ liệu seller kiểm soát: chống prompt injection bằng cách đưa nội dung đó vào khối dữ liệu, xác thực output bằng schema, và cấm sinh số.

### 4.6 Benchmark và kiểm chứng

| Kiểm chứng | Metric | Baseline | Đạt khi |
|---|---|---|---|
| Dự báo CR kỳ sau (Retailrocket, mốc 2015-08-01) | Binomial log-loss và Brier trên mỗi lượt xem của kỳ test | B0, B1, B2 | EB thắng cả B1 và B2. Δlog-loss có CI 95% (bootstrap ghép cặp theo item, 1,000 lần) không chứa 0 |
| Độ ổn định của cờ "yếu" | Precision: item bị gắn cờ ở kỳ trước thì kỳ sau vẫn ≤ 0.8×mốc | Luật thô hiện tại (≥ 30 view, `cr_index ≤ 0.8`) | Precision của EB > luật thô, CI không chồng lên nhau |
| Hiệu chỉnh khoảng | Độ phủ `ci90` | Không áp dụng | Nằm trong [87%; 93%] |
| Null trên seed | Tỉ lệ gắn cờ | Luật thô | EB ≤ 5%; ghi luôn tỉ lệ của luật thô để so |
| Mô phỏng có đáp án | Sai số θ̂ so với θ thật (θ lấy từ Beta) | B0, B1 | EB có MSE thấp nhất |

Nếu EB không thắng B1 (Laplace): báo cáo thẳng, triển khai B1 vì nó đơn giản hơn, và giữ điều kiện bật mẹo dựa trên khoảng tin cậy.

## 5. Lộ trình

| Giai đoạn | Việc | Kết quả kiểm chứng |
|---|---|---|
| Ngay 1–2 ngày | Gỡ hoặc khoá endpoint add-to-cart công khai; loại `pid` khỏi mốc; thêm fallback toàn sàn; 0 lượt xem → MSG153 | Test: POST add-to-cart ẩn danh → 401 hoặc 404; danh mục rỗng → `benchmark_scope: "platform"` |
| Ngay 1–2 ngày | Tắt luật `c2o/4`; ghi rõ trên seed là "tham số nhập tay"; sửa `SEED_PARAMS.md` | Test bước yếu so theo danh mục |
| 1–2 tuần | Dựng pipeline Retailrocket; EB với B0/B1/B2; null test trên seed; batch prior hằng ngày | Bảng log-loss và precision kèm CI; `cr_category_prior` có `as_of` |
| 1–2 tuần | Thêm `by_period` theo UC-58; mẹo theo ngữ cảnh từ LI | Test ô ít lượt xem co về mốc |
| Khi có dữ liệu thật | Prior VietCraft theo danh mục; đo độ phủ `ci90` mỗi tháng; log mẹo | Báo cáo độ phủ; chuyển `prior_source` |

**Xong khi:**
- Khớp các BR và endpoint của mục SRS 3.8.3 và UC-58:
  - `GET /api/analytics/listings/{listingId}/conversion`, input `listingId`;
  - BR-177 chỉ listing của mình;
  - BR-179 mẹo chỉ khi thấp hơn ≥ 20%;
  - BR-180 mốc danh mục cập nhật bằng batch hằng ngày;
  - Validation 0 lượt xem → MSG153;
  - 3.8.3.a1 fallback toàn sàn;
  - CR theo ngày, tuần, tháng.
- EB có số log-loss và precision so với baseline kèm CI, thắng hay thua đều công bố.
- Phụ lục SRS ghi: CR thô vẫn là đơn / lượt xem; việc quyết định có hiện mẹo hay không dùng hậu nghiệm.

## 6. Hội đồng sẽ hỏi

- **"Sao không dùng thẳng đơn / lượt xem như SRS?"** Vẫn trả số đó (`cr_raw`). Nhưng với 30 lượt xem, 78% listing trung bình ra 0 đơn. Quyết định hiện mẹo vì vậy phải dựa trên ước lượng có khoảng tin cậy.
- **"Dữ liệu train ở đâu khi sàn chỉ có 4 đơn?"** Retailrocket: 2.66 triệu lượt xem thật, chia theo thời gian. Seed chỉ dùng để kiểm null, vì tỉ lệ trong seed là tham số nhập tay.
- **"Lượt xem có bị bơm không?"** Có lỗ: endpoint giỏ công khai, và `session_id` do client gửi. Kế hoạch gỡ endpoint và chuyển sang session ký ở server nằm ở giai đoạn đầu.
- **"Mẹo có làm tăng CR không?"** Chưa chứng minh được. Hiện chỉ đo được mẹo có trúng listing yếu thật hay không (precision). Muốn chứng minh nhân quả thì cần A/B khi có đủ shop.
