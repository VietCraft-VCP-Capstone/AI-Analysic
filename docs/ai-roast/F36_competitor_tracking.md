# F36 Đối thủ đang theo dõi: roast và đường ra

> Endpoint `GET | POST | DELETE /api/analytics/competitor-tracking` (BE `/api/seller/analytics/competitor-tracking`, shop thật ghi qua BE) · Trang FE `/seller/insights/tracking` (`FE/src/modules/analytics/pages/TrackingPage.tsx`) · File chính `app/api/v1/f36_competitor_tracking.py`, `app/api/v1/_competitor_live.py:204-253,330-370`, `app/api/v1/_live_guard.py`, `BE/src/modules/analytics/application/competitor-tracking.service.ts` · Ngày 2026-10-21 · Người viết: Claude (subagent)

## 0. Bản đăng ký nói gì

| Mục | SRS 3.9.5 Competitor Tracking (tóm tắt) |
|---|---|
| Actor | Seller đã đăng nhập |
| Trigger | (1) Seller bấm [+ Thêm shop] ở tab "Theo dõi đối thủ", mở `SellerCompetitorTrackingPage`; (2) một shop đang được theo dõi đăng sản phẩm mới trong ngách đang hoạt động của seller |
| Endpoint | `GET /api/analytics/competitor-tracking`, `POST /api/analytics/competitor-tracking`, `DELETE /api/analytics/competitor-tracking/{shopId}`, Bearer JWT (Seller) |
| Input | `shopId` (bắt buộc khi thêm hoặc bỏ); hệ thống lấy `sellerId` từ JWT, danh sách `competitorTracking[]`, tag và danh mục ngách của seller, kết quả quét listing mới hằng ngày |
| Output | Danh sách shop đang theo dõi; cảnh báo khi đối thủ ra hàng mới trong ngách |
| Xử lý | Thêm, bỏ là CRUD có kiểm tối đa 10 shop và chống trùng. **Một job lịch hằng ngày** quét listing mới của từng shop được theo dõi. Listing mới trùng tag hoặc danh mục với listing của seller thì gửi cảnh báo qua **Notification System (in-app và email)** |
| Màn hình | Tiêu đề "Theo dõi đối thủ" và nút [+ Thêm shop], nút bị tắt khi đủ 10 shop và có tooltip. Danh sách: tên shop, danh mục, số listing, **ngày ra sản phẩm mới gần nhất**, nút [Bỏ theo dõi]. Hộp thoại thêm shop **tìm theo tên shop**. Có trạng thái rỗng |
| BR-201 | Theo dõi tối đa 10 shop cùng lúc |
| BR-202 | Không theo dõi trùng một shop; trùng thì từ chối, không tạo bản ghi |
| BR-203 | Chỉ báo khi listing mới của đối thủ nằm trong ngách của seller (trùng tag hoặc danh mục), không báo mọi listing mới |
| BR-204 | Bỏ theo dõi thì dừng ngay cảnh báo tương lai, **không xoá cảnh báo cũ đã gửi** |
| Thông báo | MSG143 vượt 10 shop, MSG144 trùng shop, MSG145 thêm lỗi, MSG146 xoá lỗi, MSG147 tải danh sách lỗi |

## 1. Roast: code hiện tại thực chất là gì

**"Cảnh báo" không được gửi đi đâu cả.** Nó là một danh sách tính lại mỗi lần seller mở trang (`_competitor_live.py:345-350`), và code tự ghi điều đó ở `:366-367`. Không có job, không lưu, không đẩy qua Notification. Grep `competitor` trong `BE/src/modules/notification` ra rỗng. Seller không mở trang thì đéo bao giờ biết đối thủ vừa ra hàng. SRS gọi chức năng này là "receiving alerts", còn code là "tự vào mà xem".

**Đường seed báo cả kho hàng cũ là "cảnh báo".** Seed lấy **mọi** listing của shop đang theo dõi có chung ít nhất một tag (`f36_competitor_tracking.py:69-81`). Không có chữ "mới" nào trong logic. `detected_at` là giờ chạy job (`:78`), danh sách xếp theo doanh số (`:82`). Code tự thú ở `:95-97`. Tag seed lại gán bằng `random.sample` (`app/seed/fix_seed_linkage.py:149`), nên "cảnh báo trong ngách" của demo là bốc thăm.

**Nói dối ngay trong response.** DELETE seed trả câu "Cảnh báo cũ vẫn giữ (BR-204)" (`f36_competitor_tracking.py:146`). Nhưng cảnh báo chưa bao giờ được lưu, và GET chỉ đọc tracker có `active: True` (`:60`). Bỏ theo dõi là cảnh báo bay sạch. Bản live của BE thì thật thà hơn: "Cảnh báo của gian hàng này sẽ không còn hiện" (`competitor-tracking.service.ts:64-65`). Thật thà, nhưng vẫn vi phạm BR-204. Viết một câu nói dối để "đạt BR" đúng là ngáo vl.

**Ngách rộng bằng cả ngành.** Live coi "trùng danh mục" là trùng **danh mục cấp 1** (`_competitor_live.py:163,225,235`). Seller bán một mẫu cốc thì mọi sản phẩm mới thuộc "Nhà cửa" của shop đang theo dõi đều nổ cảnh báo. Thêm nữa `"in_my_niche": True` được gán cứng (`:247`), không có điểm liên quan nào, chỉ xếp theo ngày đăng (`:350`). BR-203 có làm, nhưng làm kiểu chữ không làm kiểu nghĩa.

**Code chết, đếm cả sàn mỗi lần mở trang.** `_live_guard.py:6` (`dem_shop_cung_danh_muc`) không ai import, grep chỉ ra chính định nghĩa của nó. Mỗi GET gọi `dong_live(now)` (`_competitor_live.py:346`), tức đọc toàn bộ products, variants, orders, reviews, wishlists của sàn (`:256-274`) chỉ để lọc ra vài sản phẩm 7 ngày tuổi. Đm, lấy xe ben chở một quả trứng.

**Ghi công, phần này khá:**
- BR-201 và BR-202 được chặn ở BE cho shop thật (`competitor-tracking.service.ts:34-42`, `SELLER_FOLLOW_LIMIT = 10` ở `shop.service.ts:10`) và ở AI cho seed (`f36_competitor_tracking.py:115-120`).
- Module AI không cho shop thật ghi (`:40-43`), nên danh sách theo dõi chỉ có một nguồn là `shop_followers`, dùng chung với nút "Theo dõi" ngoài trang shop.
- `listed_at` là ngày đăng thật, và có test khẳng định điều đó (`tests/test_competitor_live.py:285-291`).

### Lệch bản đăng ký

- **Không có job hằng ngày, không có Notification in-app và email.** Cảnh báo chỉ tính khi seller mở trang (`_competitor_live.py:345-350`). Bước 6 của Normal Flow không tồn tại.
- **BR-204:** cảnh báo không được lưu, nên không có "cảnh báo cũ đã gửi" để mà giữ. Seed còn khẳng định ngược lại (`f36_competitor_tracking.py:146`).
- **BR-203 ở seed:** báo mọi listing có chung tag, không cần là listing mới (`:69-81`).
- **Endpoint DELETE:** SRS là `DELETE /competitor-tracking/{shopId}`. Code nhận `shop_id` trong body hoặc query (`f36_competitor_tracking.py:132-136`). BE (`seller-analytics.router.ts:44`) và FE (`analyticsApi.ts:62`) cũng gửi trong body.
- **Danh sách theo dõi thiếu cột:** không có danh mục, không có ngày ra sản phẩm mới gần nhất. `added_at` luôn là `None` ở live (`_competitor_live.py:356`).
- **Hộp thoại thêm shop không tìm theo tên.** Live chỉ cho chọn trong danh sách shop bán chạy cùng danh mục chính, lấy từ F32 (`TrackingPage.tsx:53-60`). Seed bắt gõ mã shop (`:245`).
- **Tên trang, tab, route khác:** code là `TrackingPage.tsx`, nhãn "Đối thủ đang theo dõi" (`nav.ts:71`), `/seller/insights/tracking`; SRS là `SellerCompetitorTrackingPage.tsx`, "Theo dõi đối thủ", `/seller/analytics/competitor-tracking`.

## 2. Mổ xẻ lỗi

| # | Mức | Chỗ | Lỗi | Hậu quả | Sửa nhanh |
|---|---|---|---|---|---|
| 1 | Chết người | `f36_competitor_tracking.py:146` vs `:60` | Response khẳng định giữ cảnh báo cũ, thực tế không lưu gì | Nói dối người dùng và hội đồng về BR-204 | Sửa câu ngay; lưu cảnh báo (#3) |
| 2 | Nặng (lệch SRS) | `_competitor_live.py:345-350,366-367` | Không có job ngày, không gửi in-app hay email | Chức năng "nhận cảnh báo" của SRS không có | Job đêm sinh cảnh báo; BE ghi `competitor_alerts` và gọi Notification |
| 3 | Nặng (lệch SRS) | BR-204: không có collection cảnh báo | Bỏ theo dõi là mất hết lịch sử | Vi phạm BR-204 | Lưu cảnh báo kèm `delivered_at`; bỏ theo dõi chỉ chặn cảnh báo mới |
| 4 | Nặng (lệch SRS) | BR-203: `f36_competitor_tracking.py:69-81` | Seed không có điều kiện "mới" | Báo cả catalog cũ | Lọc `created_at` trong cửa sổ quét; seed không có ngày thì tắt cảnh báo |
| 5 | Nặng (lệch SRS) | `f36_competitor_tracking.py:132-136`; BE router `:44`; FE `analyticsApi.ts:62` | DELETE nhận body, không nhận path `{shopId}` | Sai hợp đồng API đã đăng ký | Thêm route `DELETE /competitor-tracking/{shopId}`, giữ body làm alias |
| 6 | Nặng (lệch SRS) | `_competitor_live.py:353-358`; `TrackingPage.tsx:53-60,245` | Thiếu danh mục và ngày ra hàng mới; không tìm shop theo tên | Màn hình đăng ký thiếu | Trả `category`, `last_new_listing_at`; thêm ô tìm shop theo tên (BE chỉ có `ShopService.resolveShop` theo id hoặc slug, `shop.service.ts:64-73`, phải viết thêm tìm theo tên) |
| 7 | Nặng (lệch SRS) | `nav.ts:71`, route | Tên trang, tab, route khác | Hội đồng dò theo SRS không thấy | Đổi nhãn, hoặc ghi ánh xạ vào phụ lục |
| 8 | Nặng | `_competitor_live.py:163,225,235` | "Trùng danh mục" là trùng cấp 1 | Cảnh báo nhiễu, BR-203 mất nghĩa | So ở cấp lá (`product_type_id`, `:165`) |
| 9 | Vừa | `_competitor_live.py:247,350` | `in_my_niche` gán cứng, không có điểm liên quan | Cảnh báo quan trọng bị chìm | Thêm điểm liên quan (mục 4.3), xếp theo điểm |
| 10 | Vừa | `_competitor_live.py:346,256-274` | Đọc cả sàn mỗi GET | Chậm dần theo quy mô sàn | Đọc cảnh báo đã lưu |
| 11 | Nhẹ | `_live_guard.py` | Code chết | Gây nhiễu khi đọc | Xoá |
| 12 | Nhẹ | `_competitor_live.py:356` | `added_at = None` | Không biết đã theo dõi từ bao giờ | BE lưu thời điểm follow, hoặc ghi rõ "không có" |

## 3. Tính năng này nên là AI gì

Phần CRUD (thêm, bỏ, giới hạn 10, chống trùng) là nghiệp vụ thuần, **không cần AI**, và đang làm ổn ở BE. Việc cần AI trong hợp đồng 3.9.5 là câu hỏi "listing mới này có nằm trong ngách của tôi không và đáng chú ý tới đâu".

- **Bài toán:** với listing mới `L` của shop đang theo dõi và tập listing đang bán `S` của seller, ước lượng `r(L, S) = P(seller coi L là hàng cạnh tranh trực tiếp)`.
- **Giữ BR-203:** điều kiện kích hoạt vẫn là trùng tag hoặc danh mục. Ngách được định nghĩa rõ là tag và danh mục **lá** của listing đang PUBLISHED. Định nghĩa này phải ghi vào phụ lục. `r` chỉ dùng để xếp hạng cảnh báo và chọn thứ tự trong email tổng hợp hằng ngày. Mọi cảnh báo đủ điều kiện vẫn vào in-app, nên không tự ý bỏ cảnh báo nào.
- **Nhãn:** cặp (listing mới, seller) do người chấm tay; về sau là hành vi thật của seller (mở, bấm vào listing, bấm "không liên quan").
- **Nằm ngoài SRS, không làm mặc định:** cảnh báo giảm giá hoặc doanh số tăng vọt. Muốn làm thì ghi vào phụ lục như tính năng bổ sung (**cần cập nhật SRS/phụ lục**). Gợi ý shop tương tự trong hộp thoại thêm shop được phép làm, vì seller vẫn tự chọn và hợp đồng không đổi.
- **Giới hạn trung thực:** đối thủ cố tình né cả tag lẫn danh mục thì theo BR-203 không được báo, kể cả khi embedding thấy giống. Nếu muốn dùng độ giống làm điều kiện ngách thì cũng phải cập nhật SRS.

## 4. Đường ra: thiết kế AI chính hiệu

### 4.1 Dữ liệu: train / validation / test / thực
- **Tập chấm tay (nguồn chính):** chọn 80 listing "của tôi" từ tiki26 (3,998 dòng có ảnh và seller). Với mỗi listing, lấy 5 ứng viên của seller khác trong cùng nhóm (trộn ứng viên gần và xa theo cosine), được 400 cặp. Hai người chấm "cạnh tranh trực tiếp / không", báo Cohen's kappa. Chia validation và test **theo seller của listing gốc**, mỗi bên 50%.
- **Mô phỏng có nhãn:** dùng ảnh chụp catalog Tiki làm "kho cũ", rút 10% listing ra làm "listing mới" kèm ngày đăng giả. Gán mỗi seller giả theo dõi 5–10 shop. Bơm thêm các ca có đáp án chắc chắn: bản sao listing của tôi do shop theo dõi đăng (phải báo), sản phẩm khác danh mục và khác tag (không được báo), sản phẩm trùng tag phổ thông nhưng khác loại (phải xếp thấp).
- **Local:** `vietcraft-test` có 29 sản phẩm, 26 shop, 3 bản ghi `shop_followers` (đếm chỉ đọc hôm nay). Đủ cho test tích hợp, không đủ để đánh giá.
- **Thực:** khi đã lưu cảnh báo, ghi `opened_at`, `clicked_at`, `dismissed_reason`. Chỉ huấn luyện lại khi có ít nhất 200 phản hồi có nhãn. Mốc này là đề xuất.

### 4.2 Làm sạch và sanity
- "Mới" nghĩa là `created_at` nằm trong cửa sổ của lần quét và `status = PUBLISHED`. Sửa tiêu đề hay đổi giá không làm listing thành mới. Hiện code đã dùng `created_at` (`_competitor_live.py:231-233`), giữ như vậy.
- Khoá chống trùng là `(watcher_shop_id, listing_id)`, nên chạy lại job không gửi lại cảnh báo.
- Gộp gần-trùng: các listing cùng shop có cosine ảnh trên ngưỡng đã hiệu chỉnh thì gộp thành một cảnh báo, chống spam biến thể.
- Ranh giới: `shopId` phải là shop có thật (BE `resolveShop`, `shop.service.ts:64-73`). Không tự theo dõi chính mình (đã có, `competitor-tracking.service.ts:31-33`).
- Sanity bắt buộc:
  1. xáo vector embedding thì precision@5 phải rơi về mức B0;
  2. 100% ca bơm "bản sao" phải được báo, 0% ca "khác danh mục và khác tag" được báo, vì đây là luật cứng;
  3. bỏ theo dõi xong thì job hôm sau không sinh cảnh báo mới, còn cảnh báo cũ vẫn đọc được.

### 4.3 Model
- **B0 (hiện tại):** trùng tag hoặc danh mục cấp 1, xếp theo ngày đăng.
- **B1:** trùng danh mục lá, cộng Jaccard tag có trọng số IDF (tag phổ thông như "qua-tang" nhẹ ký).
- **M:** hồi quy logistic (sklearn) trên các feature:
  - cosine ảnh và cosine tiêu đề SigLIP2, lấy max theo các listing của tôi (`app/core/listing_intel/embedder.py:87,91`);
  - cờ trùng danh mục lá;
  - Jaccard tag theo IDF;
  - `|log(giá L / trung vị giá của tôi)|`.

  Hiệu chỉnh xác suất bằng isotonic trên validation. Chạy trên CPU bằng ONNX, không cần torch. Vector ảnh dùng lại cache `listing_embeddings` (`app/core/listing_intel/store.py:12,72-79`).
- **Kiến trúc:** AI chỉ đọc sàn (`_live.py:22`). Job AI tính danh sách cảnh báo kèm `r`, sau đó BE ghi `competitor_alerts` và gọi Notification. Như vậy không phá ranh giới chỉ-đọc hiện có.

### 4.4 Học từ dữ liệu thật
- Mỗi tháng fit lại M trên phản hồi thật, nhưng chỉ khi đã đủ 200 nhãn. Chưa đủ thì giữ trọng số học từ tập chấm tay.
- Cold start: seller chưa có listing nào thì không có ngách, nên không có cảnh báo, và trang ghi rõ lý do. Shop vừa được theo dõi thì không báo bù catalog cũ.
- Theo dõi drift: số cảnh báo mỗi seller mỗi ngày, tỉ lệ bấm "không liên quan", phân phối `r`. Tỉ lệ "không liên quan" vượt ngưỡng hai tuần liền thì xem lại ngưỡng.
- Phản hồi "không liên quan" của một seller chỉ áp cho seller đó (hạ thứ hạng cảnh báo của họ), không làm hỏng model chung.

### 4.5 Bảo mật và chống gian lận
- **Spam cảnh báo:** đối thủ đăng hàng loạt biến thể để làm nhiễu. Gộp gần-trùng (4.2), mỗi shop theo dõi tối đa 5 cảnh báo mỗi ngày, gom email thành bản tổng hợp hằng ngày.
- **Né theo dõi bằng cách khai sai danh mục và tag:** BR-203 không bắt được (xem mục 3). Có thể gắn cờ cho admin bằng embedding, nhưng không tự gửi cảnh báo nếu SRS chưa đổi.
- **SSRF khi nhúng ảnh:** dùng lại `image_fetch.py`, vốn chỉ cho phép `res.cloudinary.com` và `salt.tikicdn.com` (`:10`).
- **Lộ thông tin:** cảnh báo chỉ chứa dữ liệu công khai của listing. Không lộ cho shop bị theo dõi biết ai đang theo dõi họ, trừ khi BE đã công khai số follower. Email không chứa dữ liệu người mua.
- Không có LLM, nên không có prompt injection. Nếu sau này dùng Gemini để tóm tắt cảnh báo thì tiêu đề và mô tả của đối thủ là đầu vào không tin cậy, phải cách ly và không cho model làm theo nội dung đó.

### 4.6 Benchmark và kiểm chứng
- **Metric chính:** precision@5 của thứ hạng cảnh báo cho mỗi seller trên tập chấm tay, cộng recall của các cặp được chấm "trực tiếp". CI bằng bootstrap theo seller của listing gốc.
- **Baseline:** B0 và B1.
- **Cổng "đạt":** M hơn B0 ở precision@5, CI không chứa 0, recall không giảm quá 5 điểm. Tách riêng phần luật cứng: mô phỏng phải đạt 100% và 0% như sanity ở 4.2.
- **Khi chạy thật:** tỉ lệ mở và bấm vào cảnh báo, tỉ lệ "không liên quan". So M với B0 bằng cách xếp ngẫu nhiên một nửa số seller theo mỗi cách trong 4 tuần, chỉ làm khi mỗi nhóm có ít nhất 30 seller.
- **Không thắng thì sao:** giữ B1 (danh mục lá và tag theo IDF). Đây là luật, ghi rõ là luật, không gọi là AI.

## 5. Lộ trình

| Giai đoạn | Việc | Kết quả kiểm chứng |
|---|---|---|
| Ngay 1–2 ngày | Sửa câu nói dối ở `f36_competitor_tracking.py:146`; tắt cảnh báo seed không có ngày; thêm `DELETE /competitor-tracking/{shopId}`; so danh mục ở cấp lá; trả `category` và `last_new_listing_at`; xoá `_live_guard.py` | Test: DELETE theo path chạy được; listing cũ không bao giờ thành cảnh báo; không còn câu "vẫn giữ" khi không lưu |
| 1–2 tuần | Job đêm (APScheduler, giống `app/core/f29_scheduler.py:109-131`); BE ghi `competitor_alerts` và gửi Notification in-app cùng email tổng hợp; ô tìm shop theo tên | Test tích hợp trên `vietcraft-test`: chạy job 2 lần thì cảnh báo không nhân đôi; bỏ theo dõi thì cảnh báo cũ còn, cảnh báo mới không sinh |
| 1–2 tuần | Tập chấm tay 400 cặp; benchmark B0, B1, M; mô phỏng có nhãn | Bảng precision@5 và recall kèm CI; kappa của người chấm |
| Khi có dữ liệu thật | Ghi phản hồi; fit lại hằng tháng; thử A/B khi đủ seller | Tỉ lệ bấm và tỉ lệ "không liên quan" theo tuần |

**Xong khi:**
- cảnh báo được gửi qua in-app và email mà seller không cần mở trang;
- M thắng B0 có CI, hoặc báo cáo ghi rõ là không thắng và đang dùng B1;
- khớp các BR và endpoint của mục SRS 3.9.5: `GET` và `POST /api/analytics/competitor-tracking`, `DELETE /api/analytics/competitor-tracking/{shopId}`; BR-201 (tối đa 10, nút tắt khi đủ); BR-202 (từ chối trùng, không tạo bản ghi); BR-203 (chỉ báo listing **mới** trùng tag hoặc danh mục); BR-204 (bỏ theo dõi thì dừng cảnh báo mới, cảnh báo cũ còn tra được); MSG143–MSG147; job quét hằng ngày.

## 6. Hội đồng sẽ hỏi

- **"Cảnh báo gửi qua đâu?"** Hiện tại không gửi đi đâu, chỉ tính lại khi mở trang. Bản sửa có job đêm, lưu cảnh báo ở BE và gửi qua Notification in-app cùng email tổng hợp.
- **"BR-204 làm thế nào nếu không lưu cảnh báo?"** Không làm được, và câu trong response seed đang nói sai. Phải có collection cảnh báo, bỏ theo dõi chỉ chặn cảnh báo mới.
- **"AI ở đâu trong tính năng theo dõi?"** CRUD không cần AI. AI nằm ở điểm liên quan giữa listing mới và ngách của seller, dùng để xếp hạng cảnh báo, và được đo bằng precision@5 trên tập chấm tay so với luật hiện tại.
- **"Đối thủ đổi danh mục để né thì sao?"** Theo BR-203 thì không báo được. Embedding có thể gắn cờ cho admin. Muốn báo theo độ giống thì phải sửa SRS trước.
- **"Đối thủ spam biến thể làm ngập cảnh báo?"** Gộp gần-trùng bằng cosine ảnh, mỗi shop tối đa 5 cảnh báo mỗi ngày, email gom theo ngày.
