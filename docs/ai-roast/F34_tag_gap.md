# F34 Từ khoá nên thêm: roast và đường ra

> Endpoint `GET /api/analytics/tag-gap?categoryId=` (BE proxy `/api/seller/analytics/tag-gap`) · Trang FE `/seller/insights/tag-gap` (`FE/src/modules/analytics/pages/TagGapPage.tsx`) · File chính `app/api/v1/f34_tag_gap.py`, `app/api/v1/_competitor_live.py`, `app/api/v1/_live_competitor.py` · Ngày 2026-10-21 · Người viết: Claude (subagent)

## 0. Bản đăng ký nói gì

| Mục | SRS 3.9.3 Tag Gap Analysis (tóm tắt) |
|---|---|
| Actor | Seller đã đăng nhập |
| Trigger | Mở tab "Phân tích từ khóa" trong Product Analytics, vào `SellerTagGapPage` |
| Endpoint | `GET /api/analytics/tag-gap?categoryId={categoryId}`, Bearer JWT (Seller) |
| Input | `categoryId` (bắt buộc); hệ thống lấy `sellerId` từ JWT, tập tag hiện có của seller trong danh mục, cache tần suất tag của đối thủ |
| Output | Danh sách tag "traffic cao" mà top đối thủ dùng còn seller chưa có; mỗi tag kèm % lượt xem tăng thêm ước tính |
| Xử lý | Đếm tần suất tag của seller và của top listing đối thủ (lấy từ cache quét hằng ngày); lấy hiệu tập hợp; xếp theo tốc độ tăng lượng tìm kiếm; ước lượng traffic tăng thêm theo **lượng tìm kiếm** của tag và **CTR quan sát được** trên listing đối thủ có tag đó |
| Màn hình | `SellerTagGapPage.tsx`, route `/seller/analytics/tag-gap`, tiêu đề "Phân tích khoảng cách từ khóa", dropdown danh mục. Mỗi dòng: tag, lượng tìm kiếm, số đối thủ dùng, nhãn kiểu "+12% lượt xem ước tính", nút [Sao chép từ khóa]. Không có khoảng trống thì hiện trạng thái tích cực |
| BR-194 | Cần ít nhất 10 listing đối thủ trong danh mục, thiếu thì báo không đủ dữ liệu (MSG141) |
| BR-195 | Chỉ lấy tag có lượng tìm kiếm trên ngưỡng "traffic cao", cấu hình được, mặc định ≥ 100 lượt/tháng |
| BR-196 | Traffic tăng thêm hiện dạng **khoảng %**, ghi rõ là ước tính, không phải cam kết |
| BR-197 | Danh sách xếp theo traffic tăng thêm ước tính, giảm dần |
| Lỗi | Tải lỗi thì log console, danh sách rỗng (MSG140) |

Bản thân SRS có chỗ mâu thuẫn: phần Xử lý bảo xếp theo "tốc độ tăng lượng tìm kiếm", còn BR-197 bảo xếp theo traffic tăng thêm. Cần cập nhật SRS. Đề xuất giữ BR-197, vì BR là ràng buộc được chấm.

## 1. Roast: code hiện tại thực chất là gì

**Con số "lượt xem có thể tăng" là bịa.** `f34_tag_gap.py:74-75`:
```python
cao = min(TRAN_UOC_LUONG, max(6, round((vuot - 1) * 20) * 2))
thap = max(3, cao // 2)
```
Không có lượng tìm kiếm, không có lượt xem, không có CTR. Chỉ lấy lift nhân 40 rồi kẹp vào [6; 25]. Lift 1.3 ra "6% đến 12%", lift từ khoảng 1.65 trở lên ra cứng "12% đến 25%". FE in thẳng thành cột "Lượt xem có thể tăng" (`TagGapPage.tsx:116,131`). Gắn nhãn `"basis": "correlational"` (`:85`) cũng không cứu được, vì đây đéo phải ước lượng tương quan mà là phép nhân tự chế.

**Trên sàn thật, endpoint gần như chắc chắn trả rỗng.** "Nhóm dẫn đầu" là 20 listing đầu (`:19,54`). Lift = tỉ lệ trong top 20 / tỉ lệ trong cả danh mục, nên lift tối đa bằng `N/20`, với `N` là số listing đối thủ. Có `N ≤ 20` thì lift luôn bằng 1, nhỏ hơn ngưỡng 1.3, nên rỗng. Code tự thú điều này ở `:103-106`. Muốn có tag "mạnh" (lift ≥ 2) thì cần `N ≥ 40` trong một danh mục, mà cả sàn chỉ có khoảng 79 sản phẩm (`docs/LISTING_INTEL_TECH_REPORT.md:136`). Cổng BR-194 (`:18,47`) cho qua từ 10 listing, tức là cho qua cả khoảng 10–20 nơi kết quả chắc chắn rỗng. Test `tests/test_competitor_live.py:377-384` còn khoá cái rỗng đó lại thành "hành vi đúng". Viết test để bảo vệ một tính năng không bao giờ ra kết quả, vcl.

**Rỗng xong FE còn khen.** `missing_tags` rỗng thì FE in "Từ khoá của bạn đã giống nhóm bán chạy … Chưa cần thêm từ khoá mới" (`TagGapPage.tsx:57-58`). Rỗng vì toán học chứ không phải vì seller đã đủ tag. Đây là nói dối người dùng.

**"Nhóm bán chạy" là 20 dòng đầu Mongo trả về.** Code chỉ sắp theo `-est_sales_90d` và không có khoá phá hoà (`:42-43`). Sàn có 4 đơn nên gần như mọi listing bằng 0. Sort của Python ổn định, nên "top 20" chính là thứ tự tự nhiên của `products.find` (`_competitor_live.py:257`).

**"Đủ mạnh để không giải thích bằng ngẫu nhiên" mà đéo kiểm định gì.** `:93,98` coi `n ≥ 5` và lift ≥ 2 là đủ. Ca nhỏ nhất đạt chuẩn: 40 listing đối thủ, tag xuất hiện 5 lần và cả 5 đều nằm trong top 20. Xác suất siêu bội của ca đó là C(20,5)/C(40,5) = 0.0236 cho **một** tag. Nhưng vòng lặp thử `so_tag_thu` tag (`:91`) mà không hiệu chỉnh đa so sánh. Đếm theo listing (`:57-58`), không theo seller, nên một shop có 5 listing cùng tag là đủ tạo ra "tín hiệu thị trường".

**Có thể gợi ý tag bị cấm.** Live đọc bảng `tags` không lọc trạng thái (`_competitor_live.py:273, 326-327`), trong khi BE có `status`/`review_status` là `banned` (`BE/src/modules/tags/application/tags.service.ts:15`). Đối thủ đang gắn tag bị cấm thì F34 vẫn khuyên seller thêm tag đó.

**Seed vô nghĩa, code tự nhận.** Tag seed được gán bằng `random.sample` (`app/seed/fix_seed_linkage.py:149`), code tự ghi điều đó ở `:112-114`. Tên tag seed lại tra trong bảng `categories` (`:62-63`), trong khi tag seed nằm ở bảng `tags` (`app/core/build_marts.py:271`), nên tên gần như chắc sẽ rơi về mã thô. Chưa kiểm được vì DB seed local đang rỗng.

**Code chết.** `so_sanh_live` và `tag_live` trong `_live_competitor.py:22,60` không ai gọi. Module này chỉ được import để patch trong `tests/test_live_paths.py:7,36`.

**Ghi công:** câu "TƯƠNG QUAN, không phải nhân quả" (`:135-136`) và khối `signal` tự nói mình yếu là trung thực. BR-194 có làm. `leader_tags` (`:124-125`) là thống kê mô tả có ích.

### Lệch bản đăng ký

- **Không có lượng tìm kiếm (BR-195).** AI không đọc `search_logs` ở đâu cả (grep trong `app/` chỉ thấy dòng ghi chú `build_mvp_export.py:331-332`). Trong khi đó BE **đang ghi** `search_logs` cho mỗi lượt tìm (`BE/src/modules/product/application/product.service.ts:788-794`), kèm click theo vị trí (`.../search-click.ts:24-29`).
- **Traffic tăng thêm không tính từ lượng tìm kiếm và CTR** như SRS yêu cầu. Code tự chế từ lift (`:74-75`). Lỗi này vừa lệch đăng ký vừa là bịa số.
- **BR-197:** code xếp theo lift (`:89`), FE xếp lại theo lift (`TagGapPage.tsx:37`). Traffic tăng thêm bị kẹp trần 25 nên nhiều tag hoà ở 25, thứ tự không còn là thứ tự gain.
- **Màn hình:** không có cột lượng tìm kiếm. Không có nút [Sao chép từ khóa] (grep `clipboard` trong `TagGapPage.tsx` ra rỗng). Tên trang, tab, route khác SRS: code là `TagGapPage.tsx`, nhãn "Từ khoá nên thêm" (`nav.ts:74`), `/seller/insights/tag-gap`; SRS là `SellerTagGapPage.tsx`, "Phân tích từ khóa", `/seller/analytics/tag-gap`.
- **Trạng thái rỗng sai nghĩa:** SRS chỉ hiện trạng thái tích cực khi seller đã phủ hết tag. Code hiện cả khi rỗng do cấu trúc (xem trên).
- **"Cache quét hằng ngày":** live tính lại mỗi request (`_competitor_live.py:277-280`), cùng lỗi BR-187 của F32.

## 2. Mổ xẻ lỗi

| # | Mức | Chỗ | Lỗi | Hậu quả | Sửa nhanh |
|---|---|---|---|---|---|
| 1 | Chết người (bịa số, lệch SRS) | `f34_tag_gap.py:74-75`; FE `TagGapPage.tsx:116,131` | % lượt xem là hàm tự chế của lift | Seller tin thêm tag sẽ được thêm 12–25% lượt xem | Bỏ cột ngay; chỉ hiện khi đã có lượng tìm kiếm và CTR (mục 4) |
| 2 | Chết người | FE `TagGapPage.tsx:57-58`; `f34_tag_gap.py:103-106` | Rỗng do cấu trúc mà FE báo "đã giống nhóm bán chạy" | Nói dối người dùng | Trả `reason` (`structural`/`no_gap`), FE chỉ khen khi `no_gap` |
| 3 | Nặng (lệch SRS) | BR-195: cả file | Không có lượng tìm kiếm, không có ngưỡng 100 lượt/tháng | Điều kiện lọc chính của SRS không tồn tại | Đọc `search_logs`, đếm user phân biệt theo `keyword_norm` mỗi 30 ngày |
| 4 | Nặng (lệch SRS) | BR-197: `:89`; FE `:37` | Xếp theo lift | Sai thứ tự đăng ký | Xếp theo cận giữa của khoảng gain |
| 5 | Nặng (lệch SRS) | FE `TagGapPage.tsx`, `nav.ts:74` | Thiếu cột lượng tìm kiếm, thiếu nút sao chép; tên trang, route khác | Màn hình đăng ký không đủ | Thêm cột và nút; đổi nhãn hoặc ghi ánh xạ vào phụ lục |
| 6 | Nặng | `:19,47,54` | Cổng 10 listing nhưng nhóm dẫn đầu cố định 20 | Có `N ≤ 20` là chắc chắn rỗng | Nhóm dẫn đầu là 25% trên của danh mục (ít nhất 5), không cố định 20 |
| 7 | Nặng | `:42-43` | Không phá hoà, gặp toàn 0 thì top là thứ tự Mongo | "Tag của nhóm bán chạy" là tag của 20 dòng đầu | Phá hoà như F32; danh mục toàn 0 đơn thì trả `insufficient` |
| 8 | Nặng | `:93,98` | Câu "không giải thích bằng ngẫu nhiên" không có kiểm định | Khẳng định thống kê sai | Kiểm định siêu bội hoặc hoán vị, hiệu chỉnh Benjamini–Hochberg |
| 9 | Nặng | `_competitor_live.py:273,326-327` | Không lọc tag `banned`/`pending` | Khuyên dùng tag bị cấm | Lọc theo `APPROVED_ONLY` giống BE |
| 10 | Vừa | `:57-58` | Đếm theo listing, không theo seller | Một shop nhiều listing là đủ tạo "xu hướng" | Đếm số seller phân biệt có dùng tag |
| 11 | Vừa | `:55` | Gợi ý ở cấp shop, không kiểm tag có hợp từng listing không | Tag "áo" bị đề xuất cho người bán cốc cùng danh mục cấp 1 | Lọc theo độ liên quan với listing (mục 4.5) |
| 12 | Nhẹ | `:62-63` | Tên tag seed tra trong `categories` | Hiện mã thô (cần xác minh) | Tra trong `tags` |
| 13 | Nhẹ | `_live_competitor.py` | Code chết | Gây nhiễu khi đọc | Xoá, sửa import trong test |

## 3. Tính năng này nên là AI gì

Hợp đồng giữ nguyên: cùng endpoint, input `categoryId`, output là danh sách tag còn thiếu, mỗi tag kèm lượng tìm kiếm, số đối thủ dùng và **khoảng %** traffic tăng thêm, xếp theo gain (BR-194..197). AI nằm ở 3 chỗ, mỗi chỗ có cách kiểm riêng:

1. **Ghép truy vấn tìm kiếm với tag.** `search_logs.keyword_norm` hiếm khi trùng y slug tag. Đầu vào là truy vấn và tag; đầu ra là xác suất cùng nghĩa. Model: khớp chuẩn hoá bỏ dấu (lexicon có sẵn của Listing Intel), sau đó cosine giữa vector chữ SigLIP2 (`app/core/listing_intel/embedder.py:91`). Nhãn: 300 cặp chấm tay.
2. **Ước lượng traffic tăng thêm** theo đúng công thức SRS: `gain = Σ_q vol_q × P(hiện | listing có tag khớp q) × CTR_q / lượt xem hiện tại`. `vol_q` lấy từ `search_logs`. CTR là số click (`clicks`) chia số lần hiện, tính trên listing đối thủ có tag. Khoảng % lấy bằng bootstrap trên các phiên tìm kiếm.
3. **Tag "đi cùng bán chạy" có tín hiệu thật:** log-lift làm trơn (`app/core/listing_intel/lift.py:7`, Laplace `alpha=1`, `min_count=20`), out-of-fold theo seller (`scripts/li/fit_context.py:41`), đếm theo seller phân biệt, có kiểm định và FDR.

**Nói thẳng chỗ chưa làm trung thực được:** BE chỉ ghi `result_count` và click (`search-log.model.ts:9-16`), không ghi danh sách sản phẩm đã hiện ra. Thiếu số lần hiện thì không có mẫu số CTR. Cách gần nhất mà vẫn trung thực:
- (a) BE ghi thêm `shown_ids` (tối đa 20 id) cho mỗi lượt tìm;
- (b) trong lúc chưa có, hiện lượng tìm kiếm và số click, còn cột gain ghi "chưa ước lượng được";
- (c) ghi vào phụ lục SRS rằng BR-196 tạm hoãn tới khi có log lượt hiện (**cần cập nhật SRS/phụ lục**).

Ngưỡng BR-195 (100 lượt/tháng) quá cao cho sàn mới, nhưng SRS cho phép cấu hình. Đặt theo phân vị của phân phối lượng tìm kiếm và ghi giá trị đang dùng vào payload.

## 4. Đường ra: thiết kế AI chính hiệu

### 4.1 Dữ liệu: train / validation / test / thực
- **Tiki tiki23** (41,575 dòng, đã chia 70/15/15 theo seller, `docs/LISTING_INTEL_TECH_REPORT.md:142-147`) dùng cho phần 3. Tiki không có tag (`:180`), nên dùng n-gram tiêu đề làm đại diện cho từ khoá. Phải ghi rõ đây là đại diện, chưa phải tag thật.
- **Google Trends VN** (`data-collection.trend_interest`, 45 từ khoá, dừng 2026-08-16) chỉ là chỉ số tương đối, không phải lượt/tháng. Chỉ dùng làm cột phụ "đà tăng", không dùng để thoả BR-195.
- **VietCraft thật:** `search_logs` (lượng tìm và click), `product_events` loại `view` (giữ 90 ngày theo TTL, `product-event.model.ts:28`) và tag thật của seller. Snapshot cũ ghi `search_logs = 0` (`build_mvp_export.py:331-332`). Số hiện tại trên Atlas chưa đo (không đụng Atlas). Chia theo thời gian: 60 ngày để fit, 30 ngày sau để kiểm.
- **Nhãn chấm tay:** 300 cặp (truy vấn, tag) do 2 người chấm, báo Cohen's kappa. Chia 50/50 làm validation và test cho ngưỡng cosine.

### 4.2 Làm sạch và sanity
- Truy vấn: chuẩn hoá NFC, bỏ dấu, gộp khoảng trắng. Bỏ truy vấn của chủ shop (`search_logs.user_id` là owner). Mỗi user đếm tối đa 1 lần cho mỗi truy vấn mỗi ngày.
- Tag: chỉ lấy tag `APPROVED_ONLY`, bỏ tag nằm trong `app/core/listing_intel/data/banned_vi.json`. Gộp tag đồng nghĩa (cosine cao hơn ngưỡng đã hiệu chỉnh).
- Ranh giới: `categoryId` phải thuộc danh mục của seller (đã có, `f34_tag_gap.py:36-37`). Không bao giờ trả tag do người dùng tự nhập chưa duyệt.
- Sanity bắt buộc:
  1. xáo nhãn top25 thì lift của mọi tag về quanh 0 và không tag nào qua FDR;
  2. danh mục có `N ≤ 20` thì payload trả `reason=structural`, không trả `no_gap`;
  3. tổng gain của tất cả gợi ý không được vượt tổng lượng tìm kiếm của danh mục.

### 4.3 Model
- **B0:** quy tắc hiện tại (tỉ lệ trong top 20 chia tỉ lệ cả danh mục, ngưỡng 1.3).
- **B1:** độ phổ biến, tức n-gram hay gặp nhất trong danh mục mà listing chưa có.
- **M:** log-lift làm trơn, out-of-fold theo seller, đếm theo seller phân biệt. Giữ lại nếu q-value Benjamini–Hochberg < 0.1. Lọc tiếp bằng độ liên quan (cosine SigLIP2 giữa n-gram và tiêu đề hoặc ảnh của listing).
- **Gain:** công thức ở mục 3, chỉ đếm và nhân, không cần ML. Khoảng % là phân vị 10–90 của bootstrap. Chạy được trên CPU, không cần torch.
- Không dùng LLM để sinh tag. Phần này không cần, mà dùng thì phải lo thêm prompt injection.

### 4.4 Học từ dữ liệu thật
- Job đêm (cùng job với F32): đếm `vol_q` và CTR theo cửa sổ 30 ngày, ghi cache. Endpoint chỉ đọc cache đó.
- Ghi sự kiện khi seller bấm [Sao chép từ khóa] và khi tag đó xuất hiện trên listing của seller trong 14 ngày. Đây là nhãn "đã chấp nhận".
- So gain dự báo với thay đổi lượt xem thực tế của listing đã thêm tag, so sánh với listing tương tự không thêm (difference-in-differences). Mỗi tháng hiệu chỉnh lại hệ số bằng hồi quy isotonic.
- Cold start: ít hơn 30 ngày log hoặc dưới ngưỡng BR-195 thì không hiện gain, chỉ hiện "đối thủ dùng" và lượng tìm kiếm.

### 4.5 Bảo mật và chống gian lận
- **Nhồi từ khoá:** schema không giới hạn số tag (`BE/.../product.model.ts:144,147`). Đề xuất: mỗi lần gợi ý tối đa 5 tag; mỗi listing tối đa 10 tag ở BE; tag có cosine thấp với listing thì không gợi ý.
- **Bơm lượng tìm kiếm:** bot hoặc đối thủ tìm một từ liên tục để tạo "traffic cao". Đếm theo user hoặc session phân biệt, có rate limit, bỏ truy vấn ẩn danh lặp lại từ cùng IP.
- **Bơm click:** BE đã chống click lặp trong cùng một lượt tìm (`search-click.ts:24-29`). Cần thêm giới hạn theo user mỗi ngày, và bỏ click của chủ shop vào sản phẩm của chính mình.
- **Tag cấm:** lọc 2 lớp, gồm trạng thái `banned` của BE và `banned_vi.json` (87 cụm theo `LISTING_INTEL_TECH_REPORT.md:179`).
- **PII:** chỉ trả số đếm tổng hợp, không trả truy vấn thô của người mua. Truy vấn nào có ít hơn 5 user phân biệt thì không hiện (chống lộ truy vấn cá nhân).

### 4.6 Benchmark và kiểm chứng
- **Gợi ý (offline, Tiki):** với mỗi listing không thuộc top25 ở test, gợi ý k từ khoá. Đáp án là n-gram của các listing top25 cùng nhóm trong test, trong số 10 láng giềng kNN gần nhất (đây là chỗ dùng lại kNN của Listing Intel). Đo precision@5 và recall@10 của M so với B0, B1. CI bằng bootstrap theo cụm seller.
- **Cổng "đạt":** M hơn cả B0 và B1 ở precision@5, CI không chứa 0.
- **Phản thực có giới hạn:** thêm từ khoá gợi ý vào tiêu đề listing test, chấm lại bằng model của Listing Intel, đo Δ P(top25) so với placebo (thêm từ phổ biến ngẫu nhiên) và so với nhồi (lặp từ). Đây là thay đổi trên **model**, không phải nhân quả. Model đó chưa thắng baseline (+0.0259 [-0.071; 0.119]), và trục chữ chưa được "đã đo" (+0.0321 [-0.013; 0.075]) (`LISTING_INTEL_TECH_REPORT.md:78-79`). Vì vậy kết quả này chỉ là sanity, không phải bằng chứng.
- **Gain (khi có dữ liệu sàn):** độ phủ của khoảng 80% trên các listing đã thêm tag phải nằm trong [0.7; 0.9]. Ghép truy vấn với tag: precision ở ngưỡng đã chọn ≥ 0.8 trên tập chấm tay.
- **Không thắng thì sao:** giữ cột "đối thủ dùng" và lượng tìm kiếm (mô tả), ẩn gain, ghi lý do trong `signal.note`.

## 5. Lộ trình

| Giai đoạn | Việc | Kết quả kiểm chứng |
|---|---|---|
| Ngay 1–2 ngày | Ẩn cột gain tự chế (#1); thêm `reason` để FE không khen sai (#2); lọc tag cấm (#9); thêm nút sao chép; xoá `_live_competitor.py` | Test: `N ≤ 20` thì `reason=structural`; tag `banned` không bao giờ có trong `missing_tags` |
| 1–2 tuần | Đọc `search_logs` (BR-195, ngưỡng cấu hình); M với log-lift làm trơn, đếm theo seller, FDR; benchmark Tiki B0/B1/M; xếp theo BR-197 | Bảng precision@5 kèm CI; sanity xáo nhãn; test thứ tự theo gain |
| 1–2 tuần (BE) | Ghi `shown_ids` mỗi lượt tìm; sự kiện bấm sao chép | Số lượt hiện và CTR theo tag trên log local |
| Khi có dữ liệu thật | Gain = lượng tìm × CTR, khoảng % bằng bootstrap; diff-in-diff hằng tháng | Độ phủ khoảng 80%, tỉ lệ gợi ý được chấp nhận |

**Xong khi:**
- không còn số % nào sinh ra mà không có lượng tìm kiếm và CTR đứng sau;
- M thắng B0 và B1 có CI, hoặc báo cáo ghi rõ là không thắng;
- khớp các BR và endpoint của mục SRS 3.9.3: `GET /api/analytics/tag-gap?categoryId=`; BR-194 (≥ 10 listing đối thủ, MSG141); BR-195 (chỉ tag có lượng tìm trên ngưỡng cấu hình, mặc định 100/tháng); BR-196 (khoảng %, ghi rõ là ước tính); BR-197 (xếp theo gain giảm dần); MSG140; có cột lượng tìm kiếm và nút [Sao chép từ khóa].

## 6. Hội đồng sẽ hỏi

- **"12–25% lượt xem lấy từ đâu?"** Từ một công thức tự đặt trên lift, không dựa trên dữ liệu nào. Nhóm đã gỡ cột này. Con số mới chỉ hiện khi có lượng tìm kiếm và CTR từ `search_logs`.
- **"Thêm tag có làm bán thêm không?"** Chưa chứng minh được, và đây không phải nhân quả. Offline chỉ đo được tag gợi ý có trùng từ khoá của listing bán chạy không. Trên sàn thật thì đo bằng diff-in-diff, kèm ghi chú giới hạn.
- **"Sàn 79 sản phẩm thì phân tích tag kiểu gì?"** Phần lớn danh mục chưa qua được BR-194 hoặc rơi vào ca rỗng do cấu trúc. Hệ thống phải nói đúng lý do, không được khen seller.
- **"Seller nhồi tag thì sao?"** Gợi ý tối đa 5 tag, lọc theo độ liên quan với listing, đề xuất BE giới hạn số tag mỗi listing. Tag cấm bị lọc 2 lớp.
- **"SRS bảo xếp theo tốc độ tăng tìm kiếm, sao lại xếp theo gain?"** Vì BR-197 ghi xếp theo gain, còn phần Xử lý thì nói khác. Nhóm sẽ ghi mâu thuẫn này vào phụ lục SRS và giữ BR-197.
