# F33 Tôi mạnh, yếu ở đâu: roast và đường ra

> Endpoint `GET /api/analytics/shop-comparison` (BE proxy `/seller/analytics/shop-comparison`, `seller-analytics.router.ts:39`) · Trang FE `/seller/insights/benchmark` (`FE/src/modules/analytics/pages/BenchmarkPage.tsx`) · File chính `app/api/v1/f33_shop_comparison.py`, `app/api/v1/_competitor_live.py`, `app/api/v1/_live_competitor.py` · Ngày 2026-10-21 · Người viết: Claude (subagent)

## 0. Bản đăng ký nói gì

| Mục | SRS 3.9.2 Shop Comparison Chart (tóm tắt) |
|---|---|
| Actor | Seller đã đăng nhập, shop có ít nhất 5 listing đang bán |
| Trigger | Mở tab "So sánh shop" trong Product Analytics, vào `SellerShopRadarPage` |
| Endpoint | `GET /api/analytics/shop-comparison`, Bearer JWT, không tham số |
| Input | Không có; phân khúc và nhóm so sánh suy ra ở server từ dữ liệu của seller |
| Output | Bộ dữ liệu radar: 5 trục đã chuẩn hoá 0–100 cho shop mình và 5 đối thủ |
| Xử lý | Phân khúc = danh mục chiếm nhiều listing nhất. Đối thủ = top 5 shop trong phân khúc theo doanh thu ước tính. Mỗi trục (số listing, điểm đánh giá, tốc độ phản hồi, giá trung bình, độ đa dạng) tính giá trị thô cho 6 shop, rồi min–max về 0–100 trên đúng 6 giá trị đó |
| BR-190 | Phân khúc là danh mục chiếm ≥ 50% listing đang bán; không có thì lấy danh mục lớn nhất |
| BR-191 | 5 đối thủ là top 5 theo doanh thu ước tính trong phân khúc |
| BR-192 | Mỗi trục min–max 0–100 trên shop mình **và 5 đối thủ cùng nhau** |
| BR-193 | Dưới 5 listing đang bán thì không tính |
| Màn hình | Tab "Thị phần & Đối thủ"; tiêu đề "So sánh shop với đối thủ cùng phân khúc" + nhãn phân khúc; radar Recharts, shop mình nổi bật, 5 đối thủ màu nhạt; legend bật/tắt từng đường; tooltip số thật khi hover |
| Validation | Dưới 5 listing thì empty state MSG139; ít hơn 5 đối thủ thì vẽ với số đang có; lỗi tải thì log console (MSG138) |

## 1. Roast: code hiện tại thực chất là gì

**Năm phép trung bình và một công thức min–max, đặt tên "Tôi mạnh, yếu ở đâu".** `f33:84-93` tính đếm, trung bình sao, trung bình giá, đếm loại. `f33:24-31` co về 0–100. Không ước lượng, không khoảng tin cậy, không model. Đây là `GROUP BY` có trang trí, đéo phải AI. Mà cũng không sao: bản đăng ký chỉ đòi đúng thế. Vấn đề là làm đúng thế cũng chưa xong.

**Chuẩn hoá sai luật đã đăng ký.** BR-192 nói min–max trên 6 shop. `f33:95-96` lấy min–max trên **mọi** shop trong phân khúc:
```python
tho_all = {sid: truc_tho(sid, s) for sid, s in tho.items()}
cot = {t: [v[t] for v in tho_all.values() if v[t] is not None] for t in TRUC}
```
Một shop rác 1 listing giá 5 triệu ở cuối bảng cũng kéo giãn thang của cả radar. Luật ghi rõ trên giấy mà code vẫn làm khác. Ngáo vl.

**API nói một đằng, số làm một nẻo.** `f33:114` tuyên bố "100 luôn là tốt hơn". `f33:91` để `avg_price` nguyên chiều: shop đắt nhất được 100. FE tự biết giá là trung tính (`BenchmarkPage.tsx:41`). Nhưng radar vẫn vẽ `data.me` y nguyên (`:165-171`), nên đắt hơn trông như "mạnh hơn".

**Thiếu dữ liệu thành điểm tuyệt đối.** Nhánh seed: `float(s.get("response_time_minutes") or 0)` (`f33:81`) và `phan_hoi.get(sid, 0)` (`f33:85`). Shop chưa đo phản hồi = 0 phút = nhanh nhất = 100 điểm. Nhánh live thì đã sửa đúng (`_competitor_live.py:176`, test ở `tests/test_competitor_live.py:351-360`). Hai nhánh hai luật.

**"5 shop bán chạy nhất" trên sàn thật là 5 shop đầu vòng lặp.** Doanh thu live chỉ đếm đơn đã giao trong 90 ngày (`_competitor_live.py:103-106`). Cả sàn có 4 đơn, nên gần như mọi shop có `dt = 0`. `sorted(..., key=lambda s: -tho[s]["dt"])[:5]` (`f33:104-105`) giữ thứ tự chèn. Vậy mà FE ghi "Xếp theo doanh thu 90 ngày" (`BenchmarkPage.tsx:124`) và "5 shop dẫn đầu" (`:129`). Đm, xếp hạng bằng thứ tự `dict`.

**Phơi doanh thu của shop khác.** `f33:124` trả `est_revenue_90d_vnd` của từng đối thủ. FE in thành bảng (`BenchmarkPage.tsx:177-193`). Ở chế độ live, đó là doanh thu thật của shop thật, cộng từ đơn thật, không phải "ước tính". SRS không đòi con số này. Đây là lộ dữ liệu kinh doanh.

**Nhận xét trấn an khi không có gì để so.** Không đối thủ nào có số thì `weakest` rỗng. FE in "Bạn không kém 5 shop dẫn đầu ở tiêu chí nào" (`BenchmarkPage.tsx:109-113`). Không có dữ liệu mà vẫn khen.

**Ngưỡng "ngang nhóm" gõ tay, lời khuyên thì đoán nhân quả.** `BenchmarkPage.tsx:37-42`: sao ±0.1, listing ±10%, phản hồi ±15% hoặc 2 phút, giá ±10%. Không có độ bất định nào đứng sau. Top 5 doanh thu đương nhiên nhiều listing hơn shop mới. Nên trục "Số sản phẩm" gần như luôn "kém", kèm nút "Đăng thêm sản phẩm" (`:37`, `:101-103`). Đó là nhầm chọn mẫu thành lời khuyên.

**Code chết.** `_live_competitor.py:22-57` (`so_sanh_live`) và `:60-69` (`tag_live`) không ai gọi. Chỉ `tests/test_live_paths.py:7`, `:36` import để patch. Đường live thật nằm ở `_competitor_live.py`. Hai file tên gần giống nhau, một file chết.

### Lệch bản đăng ký

- BR-192: min–max trên cả phân khúc thay vì 6 shop (`f33:95-99`).
- BR-193: nhánh seed đếm mọi listing, không lọc `status` (`f33:39-48`). Live chỉ lấy PUBLISHED, đúng.
- BR-191: đúng trên giấy (`f33:104-105`). Nhưng với dữ liệu live, "doanh thu ước tính" gần như bằng 0 cho mọi shop, nên top 5 là ngẫu nhiên theo thứ tự.
- Màn hình: SRS là `SellerShopRadarPage`, route `/seller/analytics/shop-comparison`, radar là biểu đồ chính, legend bật/tắt được. FE là `BenchmarkPage` ở `/seller/insights/benchmark` (`InsightsPortal.tsx:47`), tiêu đề "Tôi mạnh, yếu ở đâu" (`BenchmarkPage.tsx:63`). Radar giấu trong `<details>` (`:162-174`). Legend chỉ là danh sách tĩnh, không bật/tắt (`RadarCompare.tsx:90-97`). Radar còn bỏ cả trục nếu một shop thiếu số (`RadarCompare.tsx:51-57`).
- Ngoài SRS: bảng doanh thu đối thủ, nhận xét "Tốt/Kém hơn nhóm" so với trung bình 5 shop. Phần thêm này không có trong đăng ký và hiện còn sai (xem trên).
- BR-190: khớp. `f33:55-58` lấy danh mục nhiều listing nhất, tương đương luật "≥ 50% hoặc lớn nhất". Hoà thì phụ thuộc thứ tự, SRS không quy định.

## 2. Mổ xẻ lỗi

| # | Mức | Chỗ | Lỗi | Hậu quả | Sửa nhanh |
|---|---|---|---|---|---|
| 1 | Nặng | `f33:95-99` | Lệch BR-192: min–max trên cả phân khúc | Radar khác hợp đồng; một shop ngoại lai bóp thang | `cot` chỉ gồm `[shop_id] + top` |
| 2 | Nặng | FE `:162-174`, `RadarCompare.tsx:90-97` | Lệch màn hình: radar giấu, legend không bật/tắt, đổi tên trang | Hội đồng mở trang không thấy chức năng đã đăng ký | Radar là khối chính; legend có toggle; tooltip số thô |
| 3 | Nặng | `f33:104-105` + 4 đơn live | Top 5 thực chất theo thứ tự chèn | "5 shop dẫn đầu" là nói sai | Báo `ties`/`rank_stable=false`; phá hoà theo số review như BR-188 |
| 4 | Nặng | `f33:124`, FE `:177-193` | Trả doanh thu thật của shop khác | Lộ dữ liệu kinh doanh, không có trong SRS | Bỏ con số; chỉ ghi "top 5 theo doanh thu" |
| 5 | Nặng | `f33:91`, `:114` | "100 luôn tốt hơn" nhưng giá không đảo | Radar gợi ý đắt hơn là mạnh hơn | Ghi rõ trục giá là trung tính trong API; tô màu khác |
| 6 | Vừa | `f33:81`, `:85` | Seed thiếu phản hồi thành 0 phút | Điểm 100 cho shop chưa đo | `None` như nhánh live |
| 7 | Nặng | `f33:39-48` | Lệch BR-193: seed đếm cả listing ngừng bán | Shop dưới 5 listing đang bán vẫn được so trên demo | Lọc `status == "active"` |
| 8 | Vừa | FE `:109-113` | Khen "không kém tiêu chí nào" khi không có số | Trấn an sai | Nhánh riêng "chưa có đối thủ để so" |
| 9 | Vừa | FE `:37-42` | Ngưỡng ngang nhóm gõ tay | Kết luận "tốt/kém" không có cơ sở | Khoảng tin cậy bootstrap (mục 4.3) |
| 10 | Vừa | FE `:37`, `:101-103` | Lời khuyên nhân quả từ so sánh có chọn mẫu | Đẩy shop mới đăng hàng loạt | Bỏ nút hành động ở trục số listing |
| 11 | Vừa | `_competitor_live.py:103-106` | Doanh thu không loại đơn tự mua | Shop tự mua để lọt top 5 | Loại người mua = chủ shop |
| 12 | Nhẹ | `_live_competitor.py:22-69` | Code chết, tên gần trùng file sống | Người sau sửa nhầm file | Xoá, sửa import trong test |
| 13 | Nhẹ | `tests/test_competitor_live.py:351-360`, `tests/test_live_paths.py:82-85` | Test chỉ kiểm đường ống, không kiểm BR-192 | Lỗi #1 lọt qua | Test bất biến min–max 6 shop |

## 3. Tính năng này nên là AI gì

Seller hỏi: "Shop tôi kém đối thủ cùng ngành ở đâu, và chênh đó có thật không?" Bản đăng ký trả lời bằng radar min–max của 6 shop. **Đây là thống kê mô tả, và nên giữ là thống kê.** Không có nhãn nào để học. Nhồi model vào chỉ để có chữ AI là đúng cái hội đồng gọi là "đồ chơi".

Cái đáng làm, theo thứ tự giá trị:

| Lớp | Bản chất | Vì sao đáng | Có cần sửa SRS |
|---|---|---|---|
| Đúng BR-190…193 | Code | Hợp đồng đã đăng ký | Không |
| Độ bất định | Thống kê: bootstrap giá trị thô, độ ổn định của top 5 | Biết chênh nào là thật, top 5 nào là may rủi | Không, vì chỉ thêm trường |
| Tốc độ phản hồi đo thật | Dữ liệu: thời gian trả lời đầu tiên từ `chat_messages` | Trục này hiện là trường cấu hình của shop | Không |
| "Shop giống bạn" (tuỳ chọn) | AI: tâm vector SigLIP2 của catalog shop, kNN theo shop | Shop mới so với top 5 doanh thu thì vô nghĩa; so với shop bán đồ giống mình mới có ích | **Có: cần phụ lục**, vì BR-191 cố định đối thủ là top 5 doanh thu. Chỉ là chuỗi phụ, bật bằng toggle, không thay top 5 |

## 4. Đường ra: thiết kế AI chính hiệu

### 4.1 Dữ liệu: train / validation / test / thực

- **Sàn thật** (16 shop, 79 sản phẩm, 4 đơn): đủ để chạy đúng luật, không đủ để kết luận "mạnh/yếu" có ý nghĩa thống kê. Phải hiện cỡ mẫu và cờ ổn định.
- **Seed** (`mart_competitor`, 5,000 listing): chỉ để demo. Phản hồi lấy từ `response_time_minutes` do bộ sinh tạo (`generate_seed.py:154`), không phải hành vi thật.
- **Tiki** (cho lớp "shop giống bạn"): tiki23 có 3,806 seller kèm vector chữ; tiki26 có ảnh. Dùng split theo seller của Listing Intel. Validation để chọn ngưỡng, test đọc một lần.
- **Chống rò rỉ** khi kiểm "shop giống bạn": với mỗi seller có ≥ 10 listing, chia listing ngẫu nhiên thành nửa A và nửa B. Tâm của A dựng từ A; truy hồi tìm trên tâm B của mọi seller. Không nửa nào dùng chung listing.

### 4.2 Làm sạch và sanity

- Một giá đại diện mỗi sản phẩm, dùng chung với F35 và F42: trung vị biến thể đang bán. Hiện F33 live lấy biến thể rẻ nhất (`_competitor_live.py:97`), F35 lấy trung vị lệch trên (`_live.py:170`).
- Listing count: chỉ listing đang bán (BR-193). Rating: giữ co ngót có `n_reviews`, `null` khi chưa có. Phản hồi: `None` khi chưa đo, ở cả hai nhánh.
- Doanh thu cho BR-191: đơn đã giao, không mô phỏng, trong 90 ngày, người mua khác chủ shop.
- Ranh giới tin cậy: `shop_id` chỉ lấy từ JWT (`CurrentShop`, đã đúng). Endpoint không nhận tham số, giữ nguyên như SRS.
- Sanity bắt buộc:
  - mọi giá trị chuẩn hoá thuộc [0; 100] hoặc `null`;
  - min–max tính trên đúng `1 + len(competitors)` shop;
  - 6 giá trị bằng nhau thì ra 50;
  - shop mình không nằm trong `competitors`.

### 4.3 Model

**Phần đăng ký (thống kê):**
1. Phân khúc theo BR-190, ghi `segment_share`.
2. Top 5 theo BR-191. Hoà doanh thu thì phá bằng số review rồi số đơn, và trả `rank_ties`.
3. Min–max BR-192 trên 6 shop. Trục giá trả kèm `direction: "neutral"`.
4. Độ bất định:
   - bootstrap 1,000 lần trên listing của từng shop cho `avg_price`, `avg_rating`;
   - bootstrap trên đơn cho doanh thu, rồi tính `top5_stability`: tỉ lệ lần lấy mẫu ra đúng bộ 5 shop.
   - FE chỉ nói "kém hơn" khi khoảng 90% của hiệu (mình − trung bình nhóm) nằm hẳn dưới 0. Bỏ ngưỡng gõ tay.

**Lớp tuỳ chọn "shop giống bạn":**
- Vector shop = tâm chuẩn hoá của vector SigLIP2 (chữ + ảnh nếu có) các listing đang bán. Kèm log trung vị giá để không ghép shop 50k với shop 2 triệu.
- Peer = 5 shop gần nhất theo cosine trong cùng danh mục. Chạy CPU bằng `onnxruntime`, embedder đã có sẵn ở `app/core/listing_intel/embedder.py`.
- Baseline 1: 5 shop ngẫu nhiên cùng danh mục. Baseline 2: top 5 doanh thu (chính là SRS).

### 4.4 Học từ dữ liệu thật

- Tính lại hằng ngày cùng nhịp competitor cache (BR-187 của 3.9.1). Lưu snapshot `shop_comparison_daily` để xem xu hướng của chính shop.
- Hiện `n_listings`, `n_reviews`, `n_orders` của từng shop cạnh mỗi trục. `top5_stability < 0.6` thì ghi "thứ hạng chưa ổn định vì sàn còn ít đơn".
- Cold start: ít hơn 5 đối thủ thì vẽ số đang có (đúng SRS). Không đối thủ nào thì nói thẳng, không khen.
- Lớp "shop giống bạn": tâm shop cập nhật khi listing đổi. Không cần train lại vì embedder cố định. Theo dõi độ ổn định peer theo tuần.

### 4.5 Bảo mật và chống gian lận

- Không có LLM, nên không có prompt injection.
- **Lộ dữ liệu:** không trả doanh thu tuyệt đối của shop khác. Tên shop là công khai, giữ. Doanh thu chỉ dùng nội bộ để xếp hạng.
- **Thổi số listing:** đăng hàng loạt listing rác để to trục "Số sản phẩm" và "Độ đa dạng". Trục vẫn đếm theo BR-193. Thêm cờ nội bộ cho shop có > 50% listing 0 view trong 30 ngày, và hiện số listing có lượt xem bên cạnh.
- **Đơn ảo, tự mua:** loại người mua = chủ shop. Gom theo địa chỉ hoặc số điện thoại trùng chủ shop (cần kiểm schema `orders`). Đơn `is_simulated` đã bị loại.
- **Đánh giá ảo:** chỉ tính review gắn với đơn đã giao (cần kiểm `reviews` có `order_id` không). Co ngót hiện có làm giảm tác dụng của vài review 5 sao.

### 4.6 Benchmark và kiểm chứng

Phần thống kê không có "độ chính xác". Kiểm chứng là đúng luật, ổn định, và trung thực về độ bất định:

| Kiểm tra | Cách đo | Đạt khi |
|---|---|---|
| BR-190…193 | Fixture: phân khúc 50/50, 49/51, hoà; 4 vs 5 listing; 3 đối thủ | 100% test xanh |
| BR-192 | Test bất biến: thêm một shop ngoại lai ngoài top 5 | Giá trị chuẩn hoá của 6 shop không đổi |
| Hướng trục | Snapshot API | Trục giá có `direction: "neutral"`, FE không gọi là điểm mạnh |
| Ổn định top 5 | Bootstrap đơn trên seed và live | Live với 4 đơn phải báo `top5_stability` thấp; nếu không là lỗi |
| Độ phủ khoảng | Trên seed, chia listing mỗi shop làm đôi; khoảng 90% của nửa A có chứa trung bình nửa B không | Tỉ lệ chứa ≈ 90% (sai lệch ≤ 5 điểm) |

**Lớp "shop giống bạn" trên Tiki (seller ≥ 10 listing, nửa A/B):**
- Tự truy hồi: tâm nửa A tìm đúng seller đó trong top 1 trên tâm nửa B.
- Precision@5 cùng nhóm và cùng dải giá (log trung vị giá lệch ≤ 0.5).
- Jaccard của tập peer giữa nửa A và nửa B.
- So với baseline ngẫu nhiên cùng danh mục, CI bootstrap theo seller.
- Đạt khi cả ba chỉ số hơn baseline với cận dưới CI > 0. Không hơn thì không làm lớp này, và ghi rõ trong báo cáo.

Lớp này chỉ chứng minh "tìm được shop giống", **không** chứng minh "so với shop giống giúp bán tốt hơn". Câu đó cần dữ liệu hành vi seller sau khi xem trang, hiện chưa có.

## 5. Lộ trình

| Giai đoạn | Việc | Kết quả kiểm chứng |
|---|---|---|
| Ngay 1–2 ngày | Sửa BR-192 (6 shop); `None` phản hồi ở seed; lọc `status` ở seed; bỏ doanh thu đối thủ khỏi API/FE; sửa câu khen khi không có số; trục giá `neutral`; radar thành khối chính, legend toggle, tooltip; xoá `_live_competitor.py` | Test BR-190…193 và bất biến BR-192 xanh; trang khớp mô tả màn hình SRS |
| 1–2 tuần | Bootstrap CI và `top5_stability`; phá hoà theo review; loại đơn tự mua; phản hồi đo từ `chat_messages`; một hàm giá đại diện chung với F35/F42 | Bảng kiểm 4.6 đạt; trang ghi cỡ mẫu và độ ổn định |
| Khi có dữ liệu thật | Lớp "shop giống bạn" (sau khi viết phụ lục), benchmark trên Tiki rồi bật toggle; snapshot ngày để seller xem xu hướng của mình | Tự truy hồi, precision@5, Jaccard có CI hơn baseline; tỉ lệ seller bật toggle |

**Xong khi:**
- Khớp các BR và endpoint của mục SRS 3.9.2: `GET /api/analytics/shop-comparison` không tham số. BR-190: phân khúc ≥ 50% hoặc lớn nhất. BR-191: top 5 theo doanh thu ước tính trong phân khúc. BR-192: min–max 0–100 trên đúng 6 shop. BR-193: tối thiểu 5 listing đang bán. Có MSG139 cho dưới 5 listing, MSG138 cho lỗi tải.
- Màn hình có radar làm khối chính, legend bật/tắt, tooltip số thật. Ít hơn 5 đối thủ thì vẽ số đang có.
- Không trả doanh thu tuyệt đối của shop khác. Mọi kết luận "kém/hơn" có CI đi kèm.

## 6. Hội đồng sẽ hỏi

**"Tính năng này có AI không?"**
Phần đăng ký là thống kê mô tả theo đúng BR-190…193, và nên là thống kê. AI chỉ có ở lớp tuỳ chọn "shop giống bạn", phải ghi phụ lục và qua benchmark trên Tiki mới bật.

**"Sao lại so với top 5 doanh thu khi sàn mới có 4 đơn?"**
Vì SRS quy định vậy. Code mới sẽ báo độ ổn định của top 5. Với 4 đơn, nó sẽ nói thẳng là thứ hạng chưa ổn định.

**"Điểm 0–100 nghĩa là gì?"**
Vị trí tương đối giữa 6 shop trên từng trục, không phải điểm chất lượng. Trục giá trung tính: 100 là đắt nhất, không phải tốt nhất. Tooltip luôn hiện số thật.

**"Có lộ thông tin shop khác không?"**
Bản cũ có lộ (doanh thu 90 ngày của đối thủ). Bản sửa chỉ hiện tên shop công khai và các trục đã đăng ký.
