# F30 Cảnh báo bất thường: roast và đường ra

> Endpoint `GET /api/notifications/alerts` (chỉ có trong AI service; BE proxy là `GET /api/seller/analytics/alerts`) · Trang FE "Cảnh báo bất thường" (`FE/src/modules/analytics/pages/AlertsPage.tsx`) · File chính `app/api/v1/f30_alerts.py`, `app/services/zscore_service.py`, `app/services/stl_service.py`, `app/core/build_marts.py:614-671`, `app/api/v1/_live_shop.py`, `app/api/v1/anomaly.py` · Ngày 2026-10-21 · Người viết: Claude (subagent)

## 0. Bản đăng ký nói gì

| Hạng mục | SRS 3.8.5 Automated Anomaly Detection |
|---|---|
| Actor, trigger | System chạy batch hằng ngày, hoặc Seller bấm chuông [Cảnh báo] trên header. Seller là người nhận |
| Endpoint | `GET /api/notifications/alerts` (FE polling) **và** sự kiện WebSocket |
| Input | Không có input từ UI |
| Output | Thẻ cảnh báo trong dropdown chuông, ví dụ "Tăng đột biến: T-shirt XYZ tăng 300% doanh thu"; badge đỏ đếm chưa đọc; email |
| Xử lý | Python chạy z-score cửa sổ trượt 7 ngày trên **views và revenue theo ngày của mọi listing**. Khi \|z\| > 2, publish lên GCP Pub/Sub. Node tạo Notification, đẩy WebSocket, gửi email |
| BR-183 | Chỉ sinh cảnh báo khi z > 2,0 hoặc z < -2,0 |
| BR-184 | Chỉ gửi email khi seller bật "Cảnh báo hiệu suất" trong cài đặt thông báo |
| Validation, lỗi | Lỗi tải: badge im lặng, log console (MSG134). WebSocket rớt: lần tải trang sau fetch REST |
| Màn hình | `AlertsDropdown.tsx` trong header, email template |

## 1. Roast: code hiện tại thực chất là gì

- Lõi là STL robust (`stl_service.py:33`), rồi z bền vững (median + MAD của sai phân, `zscore_service.py:28-61`), ngưỡng **|z| > 7,0** (`:18`). Kết quả bị vứt nếu quá 5% số ngày bị gắn cờ (`:20`, `:171-176`). Bộ khung có nghĩ, nhưng ngưỡng là số vặn tay.
- Câu giải thích hiện cho seller đọc là bịa: "ngưỡng 2.0 cho 7,38% báo động giả, 7.0 còn 0,6% … xem docs/SPEC_CHANGES.md" (`f30_alerts.py:19-21`). FE in nguyên câu đó (`AlertsPage.tsx:171`) và comment FE nhắc lại "0,6%" (`AlertsPage.tsx:6-7`).
  - `docs/SPEC_CHANGES.md` (65 dòng) đéo có mục nào về F30 hay anomaly.
  - Phép đo duy nhất trong repo là self-check trên sin + nhiễu Gauss (`zscore_service.py:226-249`). Tao chạy lại đúng generator đó: ngưỡng 7,0 cho **0,00%**, ngưỡng 2,0 cho **7,82%**. Không ra 7,38%, cũng không ra 0,6%.
- "z" ở đây không phải z chuẩn. Trên chính chuỗi Gauss đó, ngưỡng 3,5 vẫn gắn cờ 2,87% số ngày, trong khi lý thuyết Gauss chỉ khoảng 0,05%. Lý do: phần dư STL robust có đuôi nặng (std 4,16 so với σ ước từ MAD là 2,90). Vì vậy 7,0 chỉ là núm vặn cho tới khi hết báo, không phải "7 sigma".
- Tao cấy bất thường có đáp án vào 63 seller Olist thật qua được cổng của F30, rồi chạy đúng `bat_thuong_chuoi`:

  | Bất thường cấy | Recall giữa chuỗi | Recall ở ngày cuối |
  |---|---|---|
  | Spike +3 σ bền vững | 45% | 26% |
  | Spike +5 σ | 89% | 61% |
  | Spike +10 σ | 98% | 89% |
  | Mất bán 7 ngày (doanh thu về 0) | 13% | **2%** |
  | Tụt mức 50% | 11% | **2%** |

  Thứ làm seller mất tiền là shop tụt hoặc ngừng bán, và nó cần được báo ngay khi đang xảy ra. Với đúng loại đó, detector gần như mù (2%). Cái nó bắt được là spike to, loại mà seller thường đã biết vì chính họ chạy khuyến mãi. Đây là nghịch lý vl.
- Cổng 40% số ngày có bán (`build_marts.py:27`, `:628`) loại gần hết shop thật: trên 3.029 seller Olist chỉ **63** seller qua cổng (khoảng 2%). Seller bình thường của một sàn bán ở 3,5% số ngày (trung vị). F30 tắt với gần như mọi shop thật.
- `shop_was_analysed` nói dối:
  ```python
  duoc_do = coll.count_documents({"entity_id": shop_id}) > 0   # f30_alerts.py:46
  ```
  Shop đã được phân tích nhưng sạch (0 sự kiện) vẫn bị coi là "không được đưa vào phép dò, dưới 40% số ngày có bán" (`:53-57`). Các lý do thật như `qua_ngan`, `khong_tin_cay`, `loi` (`build_marts.py:661`) cũng bị gộp thành một câu sai. Ngáo nặng.
- Thứ tự kiểm tra trạng thái có lỗ: `limited_few_cycles` (dưới 12 chu kỳ, tức dưới 84 ngày) được xét **trước** chốt 5% (`zscore_service.py:165-176`). Shop có 60–83 ngày thì chốt chống spam không bao giờ chạy.
- STL lỗi thì im lặng thay bằng trung bình (`stl_service.py:41-47`), mà `method` vẫn ghi `stl_residual` (`zscore_service.py:120,127`). NaN cũng bị âm thầm thành 0 (`stl_service.py:17`).
- `POST /api/v1/anomaly` (`anomaly.py:50`, mount ở `app/main.py:205`) không ai gọi. Route này không có `CurrentShop`, và `data` không giới hạn độ dài (`anomaly.py:16`): một endpoint tính STL miễn phí cho bất kỳ ai gọi được tới cổng AI.
- Test có 2 cái, chỉ kiểm cờ `shop_was_analysed` (`tests/test_live_paths.py:93-105`). Không có precision, recall, hay một nhãn nào.

### Lệch bản đăng ký

| Điểm | SRS | Code | Mức |
|---|---|---|---|
| BR-183 | \|z\| > 2,0 | \|z\| > 7,0 (`zscore_service.py:18`), lý do trích nguồn không tồn tại | Chết người |
| Thuật toán | z cửa sổ trượt 7 ngày | STL toàn chuỗi + MAD sai phân, có dùng cả dữ liệu tương lai của từng điểm | Nặng |
| Phạm vi | Mọi listing, cả views và revenue | Chỉ revenue cấp shop (`build_marts.py:652-668`); thẻ cảnh báo không có tên sản phẩm | Nặng |
| Đường đi cảnh báo | Pub/Sub → Notification → WebSocket → email | Không có. BE có kiểu `ANALYTICS_ALERT` (`BE/src/modules/notification/infrastructure/models/notification.model.ts:7`) và gateway Socket.IO (`notification.gateway.ts:16-23`), nhưng không nơi nào tạo cảnh báo analytics | Nặng |
| BR-184 | Email nếu bật "Cảnh báo hiệu suất" | Không gửi email; cài đặt chỉ có "Báo cáo hiệu suất định kỳ" (`FE/src/modules/seller/components/settings/NotificationSettingsTab.tsx:237`) | Nặng |
| Giao diện | Dropdown chuông trên header | Trang riêng trong menu insights (`FE/src/modules/analytics/nav.ts:60`); chuông (`HeaderNotificationDropdown.tsx`) không nhận cảnh báo F30 | Nặng |
| Endpoint | `/api/notifications/alerts` cho FE | BE `/api/notifications` không có `/alerts` (`notification.router.ts:14-107`); FE gọi `/seller/analytics/alerts` | Nặng |
| Trigger | Batch hằng ngày | Seed: batch tay (`build_marts.py`). Live: tính lúc request (`_live_shop.py:23-32`), không có lịch chạy | Nặng |

## 2. Mổ xẻ lỗi

| # | Mức | Chỗ | Lỗi | Hậu quả | Sửa nhanh |
|---|---|---|---|---|---|
| 1 | Chết người | `f30_alerts.py:19-21`, `AlertsPage.tsx:171`, `docs/API_CONTRACT.md:272-273` | Số báo động giả không có nguồn | Nói sai với seller và hội đồng | Xoá câu; chỉ in số từ benchmark mục 4.6 |
| 2 | Chết người | `f30_alerts.py:46,53-57` | Shop sạch bị báo "quá thưa, chưa đo" | Seller nhận thông tin sai về shop mình | Lưu bảng `anomaly_run` theo shop với lý do thật |
| 3 | Chết người | `zscore_service.py:18` | Lệch BR-183, không có bản ghi lệch | Hội đồng chấm sai đăng ký | Về z > 2 trên z đã hiệu chỉnh (mục 4.3), hoặc ghi SPEC_CHANGES kèm script |
| 4 | Nặng | probe Olist | Mất bán hay tụt mức ở cuối chuỗi: recall 2% | Không báo đúng lúc cần | Detector một phía cho tụt (mục 4.3) |
| 5 | Nặng | `build_marts.py:27,628` | Cổng 40% loại khoảng 98% seller | Tính năng tắt với shop thật | Mô hình đếm cho chuỗi thưa |
| 6 | Nặng | `build_marts.py:652-668` | Không có listing, không có views | Không giải thích được nguyên nhân | Phân rã theo listing và theo views × CR × AOV |
| 7 | Nặng | BE notification | Không có producer `ANALYTICS_ALERT` | Không có thông báo realtime như SRS | Job tạo Notification, emit `notification_received` |
| 8 | Nặng | `zscore_service.py:165-176` | Chốt 5% bị bỏ qua khi dưới 84 ngày | Shop mới có thể bị spam | Kiểm tỉ lệ trước, ghép trạng thái |
| 9 | Vừa | `stl_service.py:17,41-47` | NaN thành 0, STL lỗi thì thay bằng trung bình, không báo | Nhãn `method` sai | Ném lỗi hoặc ghi `method: mean_fallback` |
| 10 | Vừa | `anomaly.py:16,50` | Route không xác thực, không giới hạn độ dài | DoS CPU nếu cổng AI lộ | Xoá route hoặc thêm `CurrentShop` + `max_length` |
| 11 | Vừa | `build_marts.py:643-644` | Mức độ 10/15 không có căn cứ | Nhãn high/medium vô nghĩa | Theo tác động tiền: Δ VND so với kỳ vọng |
| 12 | Nhẹ | `f30_alerts.py:47` | `meta` lấy từ bản ghi của shop khác khi rỗng | `computed_at` sai | Lấy từ `anomaly_run` của chính shop |
| 13 | Nặng | `NotificationSettingsTab.tsx:237`, `nav.ts:60` | Lệch BR-184 và giao diện: không email, không toggle, không dropdown chuông | Thiếu màn hình và luật đã đăng ký | Thêm toggle "Cảnh báo hiệu suất", đưa thẻ vào `HeaderNotificationDropdown` |

Lệch bản đăng ký trong bảng này là #3, #6, #7 và #13. Chi tiết từng điểm ở bảng "Lệch bản đăng ký" của mục 1.

## 3. Tính năng này nên là AI gì

Seller cần được báo sớm khi có chuyện bất thường cần hành động, kèm lý do:

- doanh thu hoặc lượt xem tụt;
- một listing ngừng bán;
- một listing bỗng hút traffic.

Bài toán gồm hai phần:

- **Phát hiện:** với mỗi (listing hoặc shop, metric, ngày t), tính phân phối dự báo của y_t từ dữ liệu **trước t**. Đổi xác suất đuôi p thành z = Φ⁻¹(p), nên vẫn đúng ngôn ngữ z-score của BR-183. Báo khi \|z\| > 2.
- **Giải thích:** cảnh báo shop phải kèm các listing đóng góp nhiều nhất vào chênh lệch, và tách doanh thu = views × CR × AOV để nói "do traffic" hay "do chuyển đổi". SRS đòi thẻ dạng "T-shirt XYZ tăng 300%", nên phần này bắt buộc.
- **Nhãn:** dữ liệu thật không có nhãn. Đánh giá bằng bất thường cấy có đáp án, cộng sự kiện tự nhiên kiểm được. Ví dụ Olist ngày 2017-11-24 (Black Friday) có 1.176 đơn, so với trung vị tháng 11/2017 là 192,5 đơn/ngày (đã đếm). Ở giai đoạn live, nhãn là phản hồi "Hữu ích / Báo nhầm" của seller.
- **Mâu thuẫn với BR-183, nói thẳng:** \|z\| > 2 nghĩa là khoảng 4,6% số phép thử báo giả dưới H0. Một shop 20 listing × 2 metric sẽ nhận khoảng 1,8 cảnh báo giả mỗi ngày. Giữ z > 2 làm điều kiện cần, và thêm điều kiện đủ (mục 4.3). **Cần cập nhật SRS/phụ lục BR-183** cho các điều kiện thêm này. Pub/Sub cũng vậy: nếu thay bằng hàng đợi nội bộ thì cũng cần cập nhật SRS/phụ lục.

## 4. Đường ra: thiết kế AI chính hiệu

### 4.1 Dữ liệu: train / validation / test / thực

| Tập | Nguồn | Cách chia |
|---|---|---|
| Nền thật | Olist: doanh thu và đơn theo seller × ngày và product × ngày, 2017-01 → 2018-08 (script tạm đã dựng ở scratchpad, cần chuyển vào `scripts/f30/`) | Seller-disjoint: dev 50%, test 50% |
| Bất thường cấy | spike (+3/+5/+10 σ), mất bán 3–7 ngày, tụt mức 30–50%, đổi nhịp tuần, tăng traffic mà CR không đổi | Vị trí ngẫu nhiên; một nửa đặt ở **ngày cuối** để đo đúng tình huống cảnh báo |
| Sự kiện tự nhiên | Olist 2017-11-24; lễ VN qua `calendar_vn.py` cho dữ liệu VN sau này | Kiểm "sự kiện lịch không bị báo nhầm" |
| Benchmark ngoài (tuỳ chọn) | NAB: hơn 50 chuỗi có nhãn, chấm theo cửa sổ, thưởng phát hiện sớm. Yahoo S5: 367 chuỗi (A1 thật, A2–A4 tổng hợp). UCR Anomaly Archive: 250 chuỗi, mỗi chuỗi 1 bất thường. Giấy phép và điều khoản tải **cần xác minh**. Đây không phải dữ liệu bán lẻ theo ngày | Chỉ sanity cho detector, không dùng làm bằng chứng chính |
| Thực | `orders`, `product_events` live (hiện có 4 đơn) | Shadow mode + phản hồi seller |

- Seed **không có bất thường cấy** và nhịp tuần là tham số nhập tay, nên không dùng làm bằng chứng.
- Chống rò rỉ: detector online chỉ được dùng dữ liệu đến t-1. Chọn ngưỡng và các cổng phụ trên dev; test đọc một lần.

### 4.2 Làm sạch và sanity

- Cùng định nghĩa doanh thu với F27 và F37 (PAID, không CANCELLED), điền 0 theo ngày GMT+7. Views lọc bot và trùng session trước khi đếm.
- Ranh giới tin cậy: không có input từ UI là đúng SRS. Xoá hoặc khoá `POST /api/v1/anomaly` (`max_length`, xác thực).
- Sanity bắt buộc (pytest):
  - chuỗi Poisson đứng yên → tỉ lệ \|z\| > 2 ≈ 4,6% ± sai số; nếu lệch thì z chưa hiệu chỉnh;
  - shop sạch → `shop_was_analysed: true`, 0 cảnh báo;
  - spike cấy ở ngày cuối → có cảnh báo trong batch kế tiếp;
  - STL hoặc model lỗi → trạng thái lỗi, không im lặng thay bằng trung bình;
  - mỗi cảnh báo có ít nhất 1 listing đóng góp và `expected_vnd`.

### 4.3 Model

| Bước | Phương pháp | Vai trò |
|---|---|---|
| Baseline A | Đúng chữ SRS: z trượt 7 ngày, \|z\| > 2 | Mốc đăng ký |
| Baseline B | Code hiện tại: STL + MAD, \|z\| > 7 | Mốc hiện có |
| Chính | Phân phối dự báo một bước: GLM Negative Binomial với thứ, lễ VN, xu hướng, fit trên 56 ngày trước t. z = Φ⁻¹(P đuôi). Với shop dày, có thể dùng phân vị của model F37 | Phát hiện spike và drop theo ngày |
| Phụ cho tụt hoặc mất bán | CUSUM một phía trên z âm. Hoặc "k ngày liên tiếp bằng 0 khi kỳ vọng ≥ λ", đổi P Poisson thành z | Recall tụt mức ở cuối chuỗi |
| Giải thích | Phân rã Δ shop theo listing; tách log-revenue = log views + log CR + log AOV | Nội dung thẻ cảnh báo |

- **Điều kiện đủ (bổ sung BR-183, cần cập nhật phụ lục):**
  - \|Δ\| ≥ ngưỡng VND hoặc %;
  - ít nhất N sự kiện kỳ vọng;
  - kiểm soát FDR Benjamini–Hochberg trên các listing của shop trong ngày;
  - trần số cảnh báo trên seller mỗi tuần.
  Tất cả ngưỡng chọn trên dev.
- Mọi thứ chạy CPU bằng statsmodels và numpy. Batch hằng đêm cho 79 sản phẩm chỉ mất vài giây.

### 4.4 Học từ dữ liệu thật

- **Luồng theo SRS:** batch Python ghi `anomaly_event` + `anomaly_run`. BE đọc (hoặc nhận webhook nội bộ thay Pub/Sub), tạo `Notification{type: ANALYTICS_ALERT}`, emit `notification_received` qua gateway có sẵn. Email gửi khi seller bật toggle "Cảnh báo hiệu suất" mới (BR-184).
- **Phản hồi:** thẻ cảnh báo có nút "Hữu ích / Báo nhầm". Ghi lại để có precision live và **chi phí báo nhầm**: số cảnh báo giả trên seller mỗi tuần, tỉ lệ tắt thông báo.
- **Hiệu chỉnh:** mỗi tháng chỉnh lại ngưỡng phụ để precision live ≥ mức đạt ở test. Đây là học từ dữ liệu thật mà không cần train mạng nơ-ron.
- **Cold start:** chuỗi dưới 28 ngày dùng prior theo danh mục (tỉ lệ bán trung bình của các listing cùng loại). Ghi `confidence: low`.
- **Drift:** tỉ lệ \|z\| > 2 trên dữ liệu không có phản hồi lệch xa 4,6% thì model kỳ vọng đã lệch, cần fit lại.

### 4.5 Bảo mật và chống gian lận

- Đối thủ bơm view hoặc đơn ảo để tạo cảnh báo giả, hoặc che một cú tụt thật: lọc bot và buyer trùng ở BE. Cảnh báo dựa trên đơn PAID.
- Seller tự tạo spike để "khoe": không ảnh hưởng người khác, nhưng loại các ngày này khỏi dữ liệu hiệu chỉnh ngưỡng.
- `GET` chỉ trả cảnh báo của `shop_id` lấy từ JWT, như hiện có. Email không chứa dữ liệu buyer (PII).
- Xoá hoặc khoá `POST /api/v1/anomaly`. Webhook BE ↔ AI dùng `X-Gateway-Secret` đã có (`_template.py:211-219`).
- Không có LLM. Nếu sau này dùng LLM viết lời thẻ cảnh báo, chỉ đưa vào số liệu có cấu trúc, không đưa tiêu đề listing thô (chống prompt injection qua tên sản phẩm).

### 4.6 Benchmark và kiểm chứng

- **Metric:**
  - precision, recall, F1 theo sự kiện, với dung sai: spike ±1 ngày, tụt mức ≤ 7 ngày;
  - **độ trễ phát hiện** (ngày) cho tụt mức và mất bán;
  - **báo giả trên seller mỗi tuần** trên chuỗi không cấy;
  - tỉ lệ cảnh báo có giải thích đúng listing cấy.
- **Baseline:** A (SRS literal) và B (code hiện tại), cùng tập cấy.
- **CI:** bootstrap theo cụm seller. So với baseline bằng bootstrap ghép cặp.
- **Cổng "đạt khi":**
  - recall tụt mức 50% ở cuối chuỗi ≥ 70%, độ trễ trung vị ≤ 3 ngày;
  - báo giả ≤ 1 trên seller mỗi tuần;
  - F1 hơn cả A và B với CI ghép cặp không chứa 0;
  - ≥ 80% cảnh báo chỉ đúng listing gây ra.
- **Sanity xáo nhãn:** đổi vị trí nhãn cấy ngẫu nhiên → F1 phải rơi về mức ngẫu nhiên. Ghi số lần đọc test.
- **Nếu không thắng:** công bố bảng recall và báo giả như mục 1, giữ detector đơn giản hơn, ghi Hạn chế. Không in câu "0,6% báo động giả" khi chưa đo.

## 5. Lộ trình

| Giai đoạn | Việc | Kết quả kiểm chứng |
|---|---|---|
| Ngay 1–2 ngày | Xoá câu 7,38%/0,6% ở API, FE, `API_CONTRACT.md`; sửa `shop_was_analysed` bằng `anomaly_run`; sửa thứ tự kiểm tra trạng thái; khoá `POST /api/v1/anomaly` | Pytest: shop sạch → analysed true; grep không còn "7,38" |
| 1–2 tuần | `scripts/f30/bench_inject.py` trên Olist; GLM NB + z hiệu chỉnh + CUSUM + cổng phụ; phân rã theo listing; producer `ANALYTICS_ALERT` + WebSocket + email + toggle | Bảng P/R/F1, độ trễ, báo giả/tuần kèm CI so với A và B |
| Khi có dữ liệu thật | Shadow mode; nút phản hồi; hiệu chỉnh ngưỡng hằng tháng | Precision live ≥ precision test; báo giả ≤ 1/seller/tuần |

**Xong khi:**
- trên tập test Olist cấy nhãn, detector đạt cổng ở mục 4.6, có CI theo seller;
- mỗi cảnh báo trên FE có listing nguyên nhân và Δ VND;
- khớp các BR và endpoint của mục SRS 3.8.5:
  - `GET /api/notifications/alerts` cho FE và sự kiện WebSocket `notification_received`;
  - batch hằng ngày trên views và revenue của mọi listing;
  - BR-183: |z| > 2 trên z hiệu chỉnh, các cổng phụ ghi trong phụ lục;
  - BR-184: email chỉ khi bật "Cảnh báo hiệu suất";
  - MSG134;
  - fallback REST khi WebSocket rớt.

## 6. Hội đồng sẽ hỏi

1. **"Sao ngưỡng là 7 trong khi SRS ghi 2?"** Bản cũ vặn tay lên 7 và trích một nguồn không tồn tại; bọn em đã gỡ. Bản mới giữ |z| > 2 trên z đã hiệu chỉnh. Phần chống spam là các cổng phụ đo trên dev, và phụ lục SRS sẽ ghi lại.
2. **"Không có nhãn thì đánh giá kiểu gì?"** Cấy bất thường có đáp án vào chuỗi bán thật của Olist, chia theo seller, đo P/R/F1 và độ trễ. Trên bộ đó, bản cũ chỉ bắt được 2% cú tụt 50% ở cuối chuỗi.
3. **"Seller bị báo nhầm nhiều thì sao?"** Đo báo giả trên seller mỗi tuần, đặt trần, có nút "Báo nhầm" và hiệu chỉnh ngưỡng hằng tháng.
4. **"Cảnh báo có nói được vì sao không?"** Có. Thẻ ghi listing đóng góp nhiều nhất và tách traffic với chuyển đổi, đúng dạng "T-shirt XYZ tăng 300%" của SRS.
5. **"Có Pub/Sub như đăng ký không?"** Chưa. Đề xuất dùng webhook nội bộ có chữ ký và gateway Socket.IO sẵn có. Đổi kênh truyền cần cập nhật SRS/phụ lục. Trải nghiệm của seller vẫn giữ nguyên.
