# F41 Việc nên làm: roast và đường ra

> Endpoint `GET /api/analytics/forecast/recommendations` (BE proxy `GET /api/seller/analytics/forecast/recommendations`) · Trang FE "Việc nên làm" `/seller/insights/actions` (`FE/src/modules/analytics/pages/ActionsPage.tsx`) · File chính `app/api/v1/f41_recommendations.py`, `app/api/v1/_live_recommendations.py` · Ngày 2026-10-21 · Người viết: Claude (subagent)

## 0. Bản đăng ký nói gì

| Hạng mục | SRS 3.10.5 Investment Recommendations (`report3.txt:5734-5790`) |
|---|---|
| Actor, trigger | Seller đã đăng nhập; mở trang tổng hợp [Khuyến nghị đầu tư] |
| Endpoint | `GET /api/analytics/forecast/recommendations`, Bearer JWT |
| Input | Không có. `shopId` lấy từ JWT |
| Output | Mảng thẻ hành động đã xếp ưu tiên, viết bằng câu tự nhiên cụ thể (ví dụ: tăng ngân sách cho sản phẩm A vì dự báo doanh thu tăng; chuẩn bị thiết kế cho một dịp lễ) |
| Xử lý | Đối chiếu listing đang bán của seller với Niche Opportunities và mùa vụ; xét sản phẩm có dự báo doanh thu giảm ("sản phẩm đang chết") rồi nối sang cơ hội mới |
| System data | Kết quả dự báo ARIMA/LSTM (F37), mùa vụ STL (F38), Gap Score ngách (F39) |
| BR-214 | Cá nhân hoá theo hiệu quả lịch sử từng danh mục của seller; không gợi ý loại mà seller có CR lịch sử 0% |
| BR-215 | Tối đa 5 khuyến nghị |
| Validation | Seller mới chưa có lịch sử → trả gợi ý chung toàn sàn |
| Abnormal | Engine lỗi → trạng thái gợi ý mặc định (tối ưu từ khoá cho 5 sản phẩm ít lượt xem nhất) kèm MSG151 |
| Màn hình | `InvestmentRecommendationsPage.tsx`; hero "Kế hoạch 30 ngày tới của bạn"; thẻ ưu tiên cao và trung bình; bấm CTA sang trang quản lý khuyến mãi |

Tóm lại: SRS đăng ký một bộ máy tổng hợp các dự báo (F37, F38, F39) thành kế hoạch 30 ngày. Lõi của nó là "dự báo sản phẩm nào sắp chết, sản phẩm nào nên đẩy".

## 1. Roast: code hiện tại thực chất là gì

- **Bản đăng ký là "Khuyến nghị đầu tư" dựa trên dự báo doanh thu. Code đéo đọc một dòng dự báo nào.** Grep cả hai file không có F37 hay `forecast` ngoài đường route (`f41_recommendations.py:20`). Cái lõi "sản phẩm đang chết" mà SRS đòi thì không tồn tại.
- **Nhánh live ghép cứng ba vòng for.** Code chạy lần lượt: listing yếu theo F29 → đỉnh mùa vụ → tag nóng (`_live_recommendations.py:89-126`). `priority` chỉ là thứ tự `append`, không phải điểm. Ưu tiên kiểu này thì gọi là "danh sách theo thứ tự code" mới đúng.
- **Nói dối về cá nhân hoá.** Response luôn ghi `"personalised": True` (`_live_recommendations.py:131`). Thực tế, hai trong ba nguồn là bảng toàn sàn, shop nào đọc cũng ra y hệt (`:48-74`). FE dựa vào đúng cờ này để quyết định có hiện cảnh báo "Đây là gợi ý chung cho toàn sàn" hay không (`ActionsPage.tsx:169`, `:178-183`). Hậu quả: shop không có listing yếu nhận 5 thẻ giống mọi shop khác, và cảnh báo bị giấu. Nói dối vl.
- **Câu thanh minh cũng sai.** `validation_note` ghi "KHÔNG dùng mart dữ liệu mồi" (`:135-138`). Nhưng `db()` trỏ vào `MONGO_DB_SEED` (`_mart.py:35-37`), và cả `seasonal_profile` lẫn `mart_demand` đều đọc từ đó (`:50`, `:72`). Số Trends là thật, nhưng ánh xạ tag và phía cung là listing seed (`build_marts.py:177-183`).
- **"Tag đang tăng trưởng X% tuần này" (`:122`) là chém.** `growth_pct` là trung bình 4 điểm weekly gần nhất so với 4 điểm trước đó (`build_marts.py:279-288`). Chuỗi weekly trong Mongo local dừng ở 2026-08-16 (tao query `data-collection.trend_interest`, `granularity: weekly`). Vậy "tuần này" thực ra là tháng 8.
- **Thẻ "sửa listing" trỏ sang chứng cứ không liên quan.** Thẻ `fix` có `target.type = "listing"` (`_live_recommendations.py:98`). FE không có nhánh cho loại này, nên rơi xuống link mặc định "Cung và cầu của ngách" và "Dự báo doanh thu" (`ActionsPage.tsx:56-66`). Backend không dùng dự báo mà FE vẫn đưa nó ra làm bằng chứng. Ngáo.
- **Nhánh seed chọn "scale" theo hạng thô `rank_in_cat`** (`f41_recommendations.py:69-70`) và bỏ qua `n_in_cat`. Hạng 1/2 trong một ngách 2 listing sẽ thắng hạng 3/500. BR-214 cũng chỉ lọc ở bước "scale" (`:92-94`). Bước "expand" vẫn gợi ý ngách mà không xét shop từng thất bại ở loại đó (`:75-89`).
- **Ghi nhận điểm tốt, vì nó có thật.**
  - Code tự khai `validated: False`, "Chưa chạy backtest", và `expected: "chưa đo được"` (`f41_recommendations.py:114-117`, `_live_recommendations.py:134-138`). Nó không bịa "+40%" như ví dụ trong SRS.
  - Nhánh seed cho shop mới trả `personalised: False` (`:42-60`), đúng mục Validation.
  - Định tuyến đúng: shop live là ObjectId 24 hex, seed là `shp_*` (`_live.py:16-18`); dữ liệu live lọc `seed_ref`, `is_simulated`, `is_hidden` (`_live.py:104-105`).
  - Ở BE (`ai-gateway.service.ts:38-47`), seller có shop thật xem số live. Có hai ngoại lệ: email nằm trong `aiShopMap` thì bị ép sang demo kể cả khi có shop thật; user chưa có shop thì xem demo toàn cục. Cả hai trường hợp đều gắn `demo: true`, và FE có `DemoBanner` (`InsightsPortal.tsx:33`).
- **Không có test.** Không file nào trong `tests/` gọi F41.

### Lệch bản đăng ký

| Điểm | SRS 3.10.5 | Code | Mức |
|---|---|---|---|
| Nguồn dữ liệu | F37 dự báo + F38 STL + F39 Gap Score | Seed: F39 + `mart_competitor`. Live: F29 + F38 + F40. Không nhánh nào dùng F37; live không dùng F39 | Chết người |
| Sản phẩm đang chết | Xét dự báo doanh thu giảm, nối sang cơ hội | Không có. Live "fix" dùng điểm luật F29 < 50 (`_live_recommendations.py:40`) | Chết người |
| BR-214 | Cá nhân hoá theo CR lịch sử từng danh mục | Live: không có. Seed: chỉ loại phôi ≥ 50 view và 0 đơn, chỉ áp cho "scale" (`f41:64-65`, `:92-94`) | Nặng |
| Validation seller mới | Gợi ý toàn sàn, ghi rõ là chung | Live luôn `personalised: True`, không có nhánh toàn sàn | Chết người |
| Abnormal MSG151 | Gợi ý mặc định kèm MSG151 | Seed trả 503 (`f41:27-28`, `_template.py:133-139`); live trả mảng rỗng; grep MSG151 trong FE/BE/AI = 0 kết quả | Nặng |
| Trang, CTA | `InvestmentRecommendationsPage`, [Khuyến nghị đầu tư], CTA sang trang khuyến mãi | `ActionsPage`, "Việc nên làm" (`nav.ts:51`); chỉ có link chứng cứ, không có CTA khuyến mãi | Nặng |
| Gap Score thừa hưởng | (tăng trưởng tìm kiếm × CR trung bình) / mật độ (`report3.txt:5643-5644`) | `demand_pct − supply_pct` (`build_marts.py:228`) | Nặng |

## 2. Mổ xẻ lỗi

Dòng có nhãn **[Lệch SRS]** là phần lệch bản đăng ký, xếp mức Chết người hoặc Nặng.

| # | Mức | Chỗ | Lỗi | Hậu quả | Sửa nhanh |
|---|---|---|---|---|---|
| 1 | Chết người | `_live_recommendations.py:131` | `personalised` ghi cứng `True` | FE giấu cảnh báo "gợi ý chung" (`ActionsPage.tsx:169`) | Tính cờ từ số thẻ thật sự dựa trên dữ liệu của shop; thêm `scope: "mixed"` |
| 2 | Chết người | `:135-138` | Ghi chú nói không dùng DB seed nhưng thực tế đọc DB seed | Khai sai nguồn trước hội đồng | Ghi rõ từng bảng đọc ở DB nào |
| 3 | Chết người | cả hai file | [Lệch SRS] Không dùng dự báo F37, không có "sản phẩm đang chết" | Lệch phần lõi đã đăng ký | Nối F29 ML (xác suất bán trong 90 ngày) và F37 (mục 4.3) |
| 4 | Chết người | live | [Lệch SRS] Không có nhánh seller mới → toàn sàn | Vi phạm Validation | `len(yeu)==0` và không có đơn → `scope: "platform"`, `personalised: False` |
| 5 | Nặng | `_live_recommendations.py:77-126` | [Lệch SRS] Không áp BR-214 | Có thể gợi ý đúng loại mà shop đã thất bại | Lọc theo CR danh mục đã co Bayes (dùng chung prior với F28) |
| 6 | Nặng | `f41:27-28`; live | [Lệch SRS] Không có fallback MSG151 | Trang lỗi 503 hoặc rỗng | Bắt lỗi, trả 5 listing ít lượt xem nhất kèm `fallback: true` và mã MSG151 |
| 7 | Nặng | `:89-126` | `priority` = thứ tự vòng for | Xếp hạng không có cơ sở | Xếp theo điểm kỳ vọng ở mục 4.3 |
| 8 | Nặng | `nav.ts:51`, `ActionsPage.tsx` | [Lệch SRS] Sai tên trang, thiếu CTA khuyến mãi | Lệch màn hình đã đăng ký | Đổi nhãn sang "Khuyến nghị đầu tư"; thêm CTA |
| 9 | Vừa | `:122` | "tuần này" thực chất là 4 tuần so với 4 tuần trước; dữ liệu weekly dừng 2026-08-16 | Số cũ 2 tháng nhưng trình bày như số mới | Ghi "4 tuần tới ngày X"; bỏ thẻ nếu dữ liệu trễ quá 21 ngày |
| 10 | Vừa | `:25`, `_live.py:118` | `_f29_thap` chỉ xét 50 sản phẩm đầu tiên | Shop lớn bị bỏ sót listing yếu | Bỏ giới hạn, hoặc lọc trước bằng điểm trong DB |
| 11 | Vừa | `:133` | `my_listings_analysed` = số listing **yếu** | Hiển thị sai nghĩa | Trả riêng `n_analysed` và `n_weak` |
| 12 | Vừa | `f41:69-70` | `rank_in_cat` thô, bỏ qua `n_in_cat` | Ngách nhỏ thắng ảo | Dùng phân vị hạng hoặc doanh thu dự báo |
| 13 | Vừa | `ActionsPage.tsx:56-66` | Thẻ `listing` dùng link chứng cứ mặc định | Chứng cứ không liên quan tới thẻ | Thêm nhánh `listing` → trang Phân tích listing |
| 14 | Nhẹ | `:78` | `estimated_document_count` trên toàn collection để quyết định có đọc điểm của shop | Shop chưa có điểm vẫn chạy query thừa | Bỏ check; query theo `product_id` là đủ |
| 15 | Nặng | `tests/` | Không có test nào | Mọi lỗi ở trên lọt qua | Thêm test BR-214, BR-215, nhánh seller mới, MSG151 |

## 3. Tính năng này nên là AI gì

**Bài toán seller cần:** trong 30 ngày tới, nên bỏ công và tiền vào việc gì để có thêm doanh thu. Đây đúng là chức năng SRS đã đăng ký, nên giữ nguyên hợp đồng.

**Định nghĩa ML.** Xếp hạng các hành động ứng viên của một shop theo doanh thu tăng thêm kỳ vọng trong 30 ngày, kèm độ bất định. Vẫn chịu BR-214 và BR-215.

| Loại thẻ (khớp ví dụ SRS) | Bộ sinh ứng viên | Model bên dưới | Nhãn để kiểm chứng |
|---|---|---|---|
| Đẩy mạnh sản phẩm A | Sản phẩm có dự báo doanh thu 60 ngày tăng | Hồi quy đếm theo listing (mới) + F37 ở mức shop | Doanh thu thật của sản phẩm trong 60 ngày sau mốc |
| Cứu hoặc thay sản phẩm đang chết | Xác suất không bán được trong 90 ngày cao | **F29 ML có sẵn** (nhãn `future_sales > 0`, `app/core/f29/ml/features.py:86`) | Không có đơn trong `[T, T+90)` |
| Sửa listing | Lời khuyên Listing Intel | `impact` counterfactual có sẵn (`listing_intel/fusion.py:134`) | Chỉ là ước lượng, không phải nhân quả (TECH_REPORT:186) |
| Thiết kế mới cho ngách hoặc dịp lễ | F39 Gap + cửa sổ ra hàng F38 | Dự báo cầu Trends (STL/ETS) | Tăng trưởng cầu thật 4–8 tuần sau mốc |

- **Điểm của mỗi thẻ** = xác suất thành công × quy mô doanh thu, với hai thành phần lấy từ các model đã qua cổng ở mục 4.6. Thẻ nào có thành phần chưa qua cổng thì giữ `expected: "chưa đo được"`.
- **Nhãn hiệu quả của chính khuyến nghị**, tức seller làm theo thì có hơn không, **không học được từ Olist**, vì Olist không có log hành động. Nói thẳng: phần nhân quả chỉ đo được bằng thí nghiệm trên seller thật (mục 4.4).
- **Câu tự nhiên** sinh bằng template từ trường có cấu trúc. Nếu dùng Gemini thì chỉ để diễn đạt lại, và không được sinh số.

## 4. Đường ra: thiết kế AI chính hiệu

### 4.1 Dữ liệu: train / validation / test / thực

| Nguồn | Dùng cho | Chia | Chống rò rỉ |
|---|---|---|---|
| Olist (`/home/rio/Documents/CODE/nodejs/vietcraft/olist/`): 99,441 đơn từ 2016-09 đến 2018-10, 3,095 seller, trong đó 818 seller có ≥ 20 đơn (tao đếm từ `olist_order_items_dataset.csv`) | Thẻ "đẩy mạnh" và "đang chết" | Theo mốc thời gian, dùng chung các mốc của F29 ML (`scripts/f29_ml/run.py`) | Feature chỉ dùng dữ liệu trước T; nhãn chỉ trong `[T, T+H)`; CI bootstrap theo cụm seller |
| Trends VN (`data-collection.trend_interest`, 45 từ khoá weekly) | Thẻ ngách và mùa vụ | `rolling_origin` (`app/core/backtest.py:15`) | Đã bỏ điểm `is_anchor`; không dùng điểm daily trộn vào weekly |
| Listing Intel (Tiki, đã chia theo seller) | Thẻ "sửa listing" | Giữ nguyên tập test đã công bố | Không đọc thêm test |
| VietCraft live | Log hành động và kết quả (mục 4.4) | Theo thời gian | Chỉ dùng shop live, bỏ `seed_ref` và `is_simulated` |

Chuyển sang dữ liệu VietCraft khi có ít nhất 30 shop có ≥ 8 tuần log thẻ đã hiển thị và kết quả. Hiện mới có 16 shop và 4 đơn, nên giai đoạn này chỉ dùng được cho sanity.

### 4.2 Làm sạch và sanity

- **Ranh giới tin cậy:** `shop_id` chỉ lấy từ gateway (đã có test `test_gateway_be_san`). Nhánh live không được đọc bảng seed mà không ghi rõ trong `meta.sources[]`.
- **Độ mới:** mỗi nguồn phải có `as_of`. Trends trễ quá 21 ngày thì bỏ thẻ mùa vụ và tag nóng, hoặc gắn nhãn "dữ liệu cũ".
- **Sanity bắt buộc (assert trong test):**
  - `len(recommendations) ≤ 5` (BR-215).
  - Không thẻ nào nhắm danh mục có CR lịch sử co Bayes ≈ 0 khi đã đủ lượt xem (BR-214).
  - `personalised` phải bằng `any(thẻ dựa trên dữ liệu shop)`.
  - Mọi số trong `why` phải truy ngược được về bản ghi DB.
- **Sanity model:** xáo nhãn doanh thu tương lai giữa các sản phẩm thì NDCG phải tụt về mức ngẫu nhiên. Nếu không tụt là có rò rỉ.

### 4.3 Model

1. **Baseline trước:**
   - B0 "cứ đẩy thứ đang bán chạy nhất kỳ trước". Đây là mốc chính code đã tự cam kết (`f41:115-117`).
   - B1 thứ tự luật hiện tại.
   - B2 ngẫu nhiên.
2. **Sản phẩm đang chết:** dùng lại `app/core/f29/ml/listing_model.joblib`, đã có AUC test 0.761 so với baseline 0.734, CI chênh lệch [0.016; 0.040]. F41 chỉ tiêu thụ kết quả, không train lại.
3. **Đẩy mạnh:** `HistGradientBoostingRegressor(loss="poisson")` dự báo số món bán trong 60 ngày, dùng chung bộ feature F29 ML. Xếp hạng theo dự báo nhân giá.
4. **Ngách và mùa vụ:** đỉnh STL của F38 cộng dự báo ETS (statsmodels) cho 4–8 tuần. Chỉ dùng khi thắng seasonal naive.
5. **Gộp:** `score = p × quy_mô`. Không dùng LambdaMART vì sklearn không có; xếp hạng theo dạng pointwise là đủ và dễ giải thích. Tất cả chạy trên CPU, không cần torch.

### 4.4 Học từ dữ liệu thật

- **Log mọi thẻ được hiển thị:** `shop_id`, `card_id`, `action`, `target`, `score`, `model_version`, `shown_at`. Kèm theo là click, việc đã làm và doanh thu 30 ngày của mục tiêu.
- **Phát hiện "đã làm" từ dữ liệu sàn**, không cần seller tự khai: listing mới có tag X, giá đổi, thêm ảnh, khuyến mãi được tạo.
- **Khám phá:** một trong 5 vị trí được xáo ngẫu nhiên với xác suất 0.2, và ghi lại xác suất hiển thị. Nhờ đó, sau này đánh giá được policy mới bằng IPS mà không phải bật nó lên thật.
- **Thí nghiệm:** A/B theo shop (nhóm giữ lại thấy thứ tự B0). Với 16 shop, thí nghiệm không đủ lực thống kê. Ghi rõ đây là thiết kế, chưa phải kết quả.
- **Cold start** theo đúng Validation SRS: trả gợi ý toàn sàn.
- **Retrain và theo dõi:** retrain hằng tháng; theo dõi calibration của xác suất bán 90 ngày (Brier theo tháng) và độ trễ của Trends.

### 4.5 Bảo mật và chống gian lận

- **Nhồi tag để làm méo phía cung:** giới hạn mỗi shop đóng góp tối đa k listing vào số cung của một tag.
- **Đơn ảo để được "đẩy mạnh":** bỏ đơn có người mua là chủ shop hoặc trùng thiết bị/IP; bỏ đơn huỷ, đơn hoàn tiền và đơn `is_simulated`.
- **Lượt xem ảo** (endpoint view công khai, xem F28): F41 chỉ dùng lượt xem đã qua lọc của F28.
- **Nếu dùng Gemini để diễn đạt:**
  - Tên sản phẩm và tag do seller kiểm soát, nên phải coi là dữ liệu: đặt trong khối dữ liệu, không ghép vào chỉ thị.
  - Output phải theo JSON schema; số liệu lấy từ trường có cấu trúc, không lấy từ text LLM.
  - Chặn output có URL hoặc chỉ thị lạ. Không đưa PII vào prompt.
- **Chống lộ dữ liệu giữa các shop:** số tổng hợp toàn sàn chỉ trả khi có ít nhất 5 shop đóng góp.

### 4.6 Benchmark và kiểm chứng

| Thành phần | Metric | Baseline | Cổng "đạt khi" |
|---|---|---|---|
| Sản phẩm đang chết | AUC, Brier trên Olist test | Luật "lâu rồi không bán" | Đã đạt: chênh +0.027, CI [0.016; 0.040] |
| Đẩy mạnh | NDCG@5 doanh thu 60 ngày sau mốc, tính theo từng seller | B0 bán chạy kỳ trước | Bootstrap ghép cặp theo seller (1,000 lần), CI dưới của ΔNDCG > 0 |
| Ngách, mùa vụ | MASE theo `rolling_origin` | Seasonal naive (`metrics.py:45`) | MASE < 1, CI theo từ khoá không chứa 1 |
| Cả danh sách | Tỉ lệ vi phạm BR-214/215; sanity xáo nhãn | Không áp dụng | 0 vi phạm; NDCG khi xáo nhãn ≈ mức ngẫu nhiên |
| Online (sau này) | Doanh thu 30 ngày của nhóm thấy thẻ so với nhóm giữ lại | Nhóm giữ lại thấy thứ tự B0 | Tính MDE trước khi chạy; nếu không đủ lực thì báo "chưa kết luận" |

Nếu không thắng B0 ở thẻ đẩy mạnh: báo cáo thẳng và dùng B0 cho loại thẻ đó. Một mốc ngây thơ thắng là kết quả hợp lệ, không phải thất bại cần giấu.

## 5. Lộ trình

| Giai đoạn | Việc | Kết quả kiểm chứng |
|---|---|---|
| Ngay 1–2 ngày | Tính `personalised` thật; sửa `validation_note`; thêm nhánh seller mới và fallback MSG151; sửa chữ "tuần này"; thêm nhánh FE cho thẻ `listing` | Test: shop không có listing yếu → `personalised: False`; mart rỗng → `fallback: true` |
| Ngay 1–2 ngày | Áp BR-214 ở cả hai nhánh; thêm 4 test (BR-214, BR-215, Validation, MSG151) | `pytest` xanh |
| 1–2 tuần | Nối F29 ML vào thẻ "đang chết"; train model đẩy mạnh trên Olist; backtest Trends | Báo cáo NDCG@5 và MASE kèm CI, so với B0 và seasonal naive |
| 1–2 tuần | Thêm điểm kỳ vọng; chỉ hiện `expected` khi thành phần đã qua cổng | Snapshot response có `model_version` và `validated` theo từng thẻ |
| Khi có dữ liệu thật | Log thẻ, xáo một vị trí, A/B theo shop | Đánh giá IPS; tính MDE; báo cáo online |

**Xong khi:**
- Khớp các BR và endpoint của mục SRS 3.10.5:
  - `GET /api/analytics/forecast/recommendations`, không có input;
  - BR-214 cá nhân hoá theo CR lịch sử từng danh mục;
  - BR-215 tối đa 5 thẻ;
  - Validation seller mới → gợi ý toàn sàn;
  - Abnormal → gợi ý mặc định kèm MSG151;
  - System data có F37, F38, F39.
- Thẻ đẩy mạnh có ΔNDCG@5 so với B0 kèm CI, dù thắng hay thua.
- Không còn cờ hoặc ghi chú nào nói khác với dữ liệu thật đã dùng.

## 6. Hội đồng sẽ hỏi

- **"Khuyến nghị này có phải AI không, hay chỉ là luật?"** Hiện tại là luật ghép ba nguồn. Đường ra dùng hai model đã có đánh giá (F29 ML, Listing Intel) và một model đẩy mạnh mới. Model này được đo NDCG so với mốc "bán chạy nhất" trên Olist.
- **"Làm sao biết seller làm theo thì doanh thu tăng?"** Hiện chưa biết, vì không có log hành động. Olist chỉ kiểm được độ chính xác của từng dự báo, không kiểm được nhân quả. Nhân quả cần A/B trên seller thật, và với 16 shop thì chưa đủ lực.
- **"Sao không ghi dự báo +40% như SRS?"** Vì chưa model nào qua cổng kiểm chứng. Con số chỉ hiện khi thành phần đó đã thắng baseline có CI. Phần này cần ghi chú vào phụ lục SRS.
- **"Gợi ý có thật sự riêng cho shop không?"** Bản hiện tại thì không: cờ `personalised` sai. Sau khi sửa, cờ được tính từ số thẻ dựa trên dữ liệu của shop, và FE hiện cảnh báo khi phần lớn thẻ là gợi ý chung.
