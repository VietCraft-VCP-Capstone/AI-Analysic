# F26 Tổng quan shop: roast và đường ra

> Endpoint `GET /api/analytics/shop/overview?timeRange=` (BE proxy `GET /api/seller/analytics/overview`) · Trang FE "Tổng quan shop" `/seller/insights/overview` (`FE/src/modules/analytics/pages/OverviewPage.tsx`) · File chính `app/api/v1/f26_shop_overview.py`, `app/api/v1/_live_overview.py` · Ngày 2026-10-21 · Người viết: Claude (subagent)

## 0. Bản đăng ký nói gì

| Hạng mục | SRS 3.8.1 Shop Performance Overview (`report3.txt:4759-4830`) |
|---|---|
| Actor, trigger | Seller đã đăng nhập; bấm tab [Tổng quan] trong menu Analytics, mở `SellerAnalyticsOverviewPage` |
| Endpoint | `GET /api/analytics/shop/overview`, Bearer JWT |
| Input | `timeRange` (`7d`, `30d`, `90d`) |
| Output | Tổng lượt xem, đơn, doanh thu, CR toàn shop; % thay đổi so với kỳ trước; chuỗi để vẽ biểu đồ |
| Xử lý | Gom chuỗi thời gian của mọi listing thuộc `shopId`; tính tổng và PoP; seller đổi khung thời gian (SRS ghi cả "Day/Week/Month" lẫn "7/30/90 ngày") |
| BR-174 | Chỉ gom dữ liệu của shop đang đăng nhập |
| BR-175 | Kỳ so sánh dài đúng bằng kỳ đang xem và nằm liền trước nó |
| BR-176 | CR toàn shop = tổng đơn / tổng lượt xem × 100 |
| Validation | Lỗi tải → trạng thái lỗi có nút thử lại (MSG129); 0 lượt xem → CR mặc định 0% |
| Abnormal | Hết thời gian chờ → toast lỗi và nút thử lại; shop mới chưa có số → trạng thái trống thân thiện, nhắc đăng hoặc quảng bá sản phẩm |
| Màn hình | Header "Tổng quan hiệu suất"; dropdown 7/30/90 ngày; 4 thẻ KPI có mũi tên xanh/đỏ; biểu đồ Recharts; bảng lịch sử đơn, xếp hạng sản phẩm, phản hồi khách |

SRS không gọi F26 là AI. Đây là dashboard thống kê mô tả, và **nên giữ như vậy**.

## 1. Roast: code hiện tại thực chất là gì

- **Không có AI nào ở đây.** Nhánh seed chỉ là một `$facet` cộng tổng và lấy top 5 theo doanh thu (`f26_shop_overview.py:43-60`). Như vậy là đúng việc, nhưng đừng ai trình bày cái này là "AI phân tích hiệu suất".
- **`confidence` thực chất là đếm số ngày có dòng dữ liệu:** `"high" if co_ngay >= 30` (`f26:118`). Đây không phải độ tin cậy thống kê. Ba mươi ngày toàn 0–1 đơn vẫn được "high". Meta còn ghi `model_version="live-read-1.0"` ngay cạnh `mode="seed_demo"` (`f26:112-115`). Đặt tên kiểu này thì người đọc meta cũng ngáo theo.
- **Lệch múi giờ ngay trong một response.**
  - Đơn được xếp ngày theo UTC: `_ngay` gọi `d.date()` trên datetime UTC (`_live_overview.py:19-24`, dùng ở `:75`, `:88`).
  - Lượt xem lại được xếp theo giờ Việt Nam qua `ngay_vn` (`:48`, `_live_data.py:33-38`).
  - Hậu quả: đơn đặt từ 00:00 đến 06:59 giờ VN bị đẩy sang hôm trước. Chuỗi ngày, ranh giới kỳ và CR theo ngày đều lệch nhau 7 tiếng. Một response mà hai múi giờ, đm.
- **Tự vả chính docstring của mình.** `ty_le_chuyen_doi` ghi rõ "Trả 0 là sai" (`_mart.py:80-88`). Nhưng nhánh live lại viết `ty_le_chuyen_doi(...) or 0` khi tính PoP của CR (`_live_overview.py:117-118`). Kỳ này 0 lượt xem, kỳ trước có CR, thì `value: None` nhưng `pop_pct: -100.0`. Seller thấy "CR giảm 100%" trong khi thực tế là chưa ai xem. Vcl.
- **Top sản phẩm đếm dòng hàng chứ không đếm đơn:** `o["orders"] += 1` chạy cho mỗi item (`:102`). Doanh thu của top lấy `retail_price × quantity` (`:103`), còn KPI doanh thu lại lấy `financial_breakdown.subtotal` (`_live_data.py:13-23`). Hai số dùng hai định nghĩa, nên cộng top 5 không khớp được với tổng.
- **Ba tính năng, ba định nghĩa "đơn".**
  - F26 chỉ tính `payment_status: PAID` (`_live_overview.py:15`, `:35`).
  - F28 tính mọi đơn không huỷ, kể cả đơn chưa trả tiền và đơn đã hoàn (`_live_data.py:10`, `:66-73`).
  - Đơn COD mặc định `PENDING` (`BE/.../order.model.ts:152`), nên shop bán COD bị F26 bỏ doanh thu cho tới khi đơn được đánh dấu đã trả.
  - Kết quả: CR toàn shop ở F26 và CR từng listing ở F28 không bao giờ đối chiếu được với nhau.
- **`confidence` của live** là `"high"` khi tổng đơn **từ trước tới nay** ≥ 20 (`:59`), không xét số đơn trong kỳ đang xem. Nhánh live cũng bỏ luật tối thiểu 7 ngày mà nhánh seed có (`f26:21`, `:73-76`).
- **Phần "Phản hồi khách" là hàng giả.** `"recent_feedback": []` bị ghi cứng ở cả hai nhánh (`f26:106`, `_live_overview.py:123`). FE chỉ vẽ mục này khi mảng khác rỗng (`OverviewPage.tsx:277`), nên mục SRS đã đăng ký đéo bao giờ hiện ra.
- **Ghi nhận điểm tốt.**
  - BR-175 làm đúng: `cua_so_truoc` lấy kỳ dài bằng kỳ đang xem, liền trước nó (`_mart.py:67-71`).
  - BR-174 được bảo vệ ở gateway, có test secret sai thì 401 (`tests/test_api_contract.py:102-141`).
  - Lượt xem live đã lọc bot, lọc chủ shop, chống trùng và rate-limit theo IP (`BE/.../event.service.ts:44-95`).
  - FE nói rõ khi cửa sổ thời gian được neo theo ngày có dữ liệu mới nhất (`OverviewPage.tsx:161-164`).
  - Shop không có cả đơn lẫn lượt xem thì trả trạng thái trống, không bịa số 0 (`_live_overview.py:61-64`).
- **Test:** chỉ có một test chức năng, kiểm `views == 40` và `CR == 5.0` (`tests/test_live_paths.py:113-116`). Không test nào kiểm múi giờ, PoP hay top sản phẩm.

### Lệch bản đăng ký

| Điểm | SRS 3.8.1 | Code | Mức |
|---|---|---|---|
| Phản hồi khách, lịch sử đơn | Có trong layout | `recent_feedback` luôn `[]`; không trả lịch sử đơn | Nặng |
| Độ chi tiết ngày/tuần/tháng | "by day/week/month" | Chuỗi chỉ theo ngày (`f26:101-102`, `_live_overview.py:120-121`). Chính SRS cũng tự mâu thuẫn (dropdown Day/Week/Month so với 7/30/90 ngày) | Nặng, cần cập nhật SRS cho rõ |
| 0 lượt xem → CR 0% | CR mặc định 0% | Trả `None` (`_mart.py:80-88`), cố ý làm vậy để trung thực | Nặng, cần cập nhật SRS/phụ lục |
| Tên trang, header | `SellerAnalyticsOverviewPage`, "Tổng quan hiệu suất" | `OverviewPage`, "Tổng quan shop" (`OverviewPage.tsx:73`, `nav.ts:58`) | Nặng |
| MSG129 | Trạng thái lỗi có mã MSG129 | FE có nút thử lại (`OverviewPage.tsx:99`), nhưng không gắn mã hay nội dung MSG129 (grep = 0 kết quả) | Nặng |
| Kỳ "đã chọn" | 7/30/90 ngày tính tới hiện tại | Live neo theo ngày có hoạt động cuối (`_live_overview.py:66-71`); shop ngừng bán 3 tháng vẫn thấy "30 ngày" đầy số | Nặng |
| `timeRange` | 7d, 30d, 90d | Nhận thêm 180d, 365d, 1y (`_mart.py:40`) | Không tính là lệch (chỉ nhận rộng hơn) |

## 2. Mổ xẻ lỗi

Dòng có nhãn **[Lệch SRS]** là phần lệch bản đăng ký, xếp mức Chết người hoặc Nặng.

| # | Mức | Chỗ | Lỗi | Hậu quả | Sửa nhanh |
|---|---|---|---|---|---|
| 1 | Chết người | `_live_overview.py:117-118` | `or 0` biến "chưa ai xem" thành CR 0 | Hiện "CR −100%" sai sự thật | Bỏ `or 0`; CR kỳ nào là `None` thì `pop_pct = None` |
| 2 | Chết người | `f26:106`, `_live_overview.py:123` | [Lệch SRS] Phản hồi khách bị ghi cứng `[]` | Mục SRS biến mất, giả như có làm | Đọc collection `reviews` của shop (lọc như `calculator.py:89-97`) |
| 3 | Nặng | `_live_overview.py:19-24`, `:75`, `:88` | Đơn xếp ngày theo UTC, lượt xem theo giờ VN | Lệch chuỗi ngày và kỳ so sánh | Dùng `ngay_vn` cho cả hai |
| 4 | Nặng | `_live_overview.py:15` và `_live_data.py:10` | F26 tính PAID, F28 tính mọi đơn không huỷ | Hai CR không đối chiếu được | Một hàm `don_tinh_doanh_thu` dùng chung cho F26, F28, F31 |
| 5 | Nặng | `_live_overview.py:66-71` | [Lệch SRS] Neo kỳ theo ngày hoạt động cuối | Che việc shop đã chết | Live neo theo hôm nay (vì tracking có thật nên 0 là 0 thật); seed giữ cách neo hiện tại |
| 6 | Nặng | layout SRS | [Lệch SRS] Không có lịch sử đơn; chỉ có chuỗi theo ngày | Lệch màn hình đã đăng ký | Thêm `recent_orders`; gom tuần cho 90d |
| 7 | Vừa | `:102-103` | Top sản phẩm đếm dòng hàng, doanh thu theo giá niêm yết | Top không khớp tổng | Đếm đơn duy nhất; phân bổ subtotal theo dòng |
| 8 | Vừa | `:59`, `f26:118` | `confidence` = số đơn từ trước tới nay, hoặc số ngày có dữ liệu | Nhãn tin cậy vô nghĩa | Dựa trên số đơn và lượt xem **trong kỳ**, thêm CI (mục 4.3) |
| 9 | Vừa | `_live_overview.py` | Thiếu luật tối thiểu 7 ngày mà seed có | Hai nhánh xử lý khác nhau | Thống nhất ngưỡng, chuyển thành nhãn thay vì chặn |
| 10 | Nhẹ | `:34-37`, `:47` | Mỗi request tải toàn bộ đơn từ trước tới nay và 400 ngày event | Chậm khi shop lớn | Lọc `created_at ≥ tu_truoc` ngay trong query |
| 11 | Nhẹ | `f26:112` | `model_version="live-read-1.0"` cho dữ liệu seed | Nhầm nguồn khi đọc meta | Đổi thành `seed-read-1.0` |
| 12 | Nặng | `_mart.py:80-88`, FE | [Lệch SRS] 0 lượt xem trả `None`, SRS đòi CR 0% | Lệch Validation (cố ý, để trung thực) | API giữ `null`; FE hiện "0% (chưa có lượt xem)"; cần cập nhật SRS/phụ lục |
| 13 | Nặng | `OverviewPage.tsx:73`, `:99` | [Lệch SRS] Sai tên trang và header; lỗi không gắn MSG129 | Lệch màn hình đã đăng ký | Đổi header thành "Tổng quan hiệu suất"; gắn mã và nội dung MSG129 |

## 3. Tính năng này nên là AI gì

**Kết luận: giữ F26 là thống kê mô tả.** Ngừng gọi nó là AI. Tổng, PoP và CR theo BR-176 là phép cộng và phép chia; không có gì để train.

Có ba lớp thêm vào đáng làm. Cả ba đều trả lời câu seller thật sự hỏi: "tháng này doanh thu giảm vì sao, và giảm vậy có bất thường không?" Hợp đồng SRS giữ nguyên; chỉ thêm trường phụ.

| Lớp | Bản chất | Output thêm | Kiểm chứng |
|---|---|---|---|
| Phân rã nguyên nhân | Thống kê (một đẳng thức), không phải ML | `explain.drivers`: Δlog doanh thu = Δlog lượt xem + Δlog CR + Δlog AOV; kèm đóng góp của từng sản phẩm vào ΔR | Đẳng thức cộng đúng tới sai số làm tròn |
| PoP có ý nghĩa không | Kiểm định tỉ số tần suất Poisson (đơn, lượt xem) | `pop_significant`, `pop_ci` cho từng KPI | Mô phỏng null: tỉ lệ cờ giả ≈ α |
| Bình thường hay bất thường | Dự báo có khoảng (dùng lại F37) | `expected_range` cho doanh thu kỳ này, phân vị của số thực tế | Độ phủ khoảng trên Olist theo `rolling_origin` |

- Phần "bất thường" phải dùng chung logic với F30 (BR-183, z > 2) để hai trang không nói ngược nhau.
- Với shop dưới 90 ngày lịch sử (đúng ngưỡng mở khoá của F37 trong test `tests/test_live_paths.py:108-110`), trả `expected_range: null` và ghi "chưa đủ lịch sử". Không vẽ khoảng.

## 4. Đường ra: thiết kế AI chính hiệu

### 4.1 Dữ liệu: train / validation / test / thực

| Nguồn | Dùng cho | Chia |
|---|---|---|
| Olist: 99,441 đơn (2016-09 đến 2018-10), 3,095 seller; 818 seller có ≥ 20 đơn, 210 seller có ≥ 100 đơn (tao đếm) | Độ phủ khoảng dự báo doanh thu theo seller | Mốc cắt hằng tháng từ 2017-06; train trước mốc, test 30 ngày sau mốc; CI bootstrap theo cụm seller |
| Chuỗi Poisson mô phỏng có đáp án | Hiệu chỉnh kiểm định PoP | 10,000 chuỗi dừng, tần suất 0.1–10 đơn/ngày |
| VietCraft live | Chạy thật, theo dõi độ phủ | Theo thời gian; chỉ shop live |

- Olist không có lượt xem. Vì vậy chỉ dùng Olist cho phần doanh thu và đơn; phần lượt xem kiểm bằng mô phỏng.
- Seed không được dùng làm bằng chứng, vì phân phối của nó do chính người viết đặt.

### 4.2 Làm sạch và sanity

- **Múi giờ:** mọi mốc ngày quy về `Asia/Ho_Chi_Minh` ở một chỗ duy nhất (`ngay_vn`).
- **Định nghĩa "đơn tính doanh thu" dùng chung** cho F26, F28 và F31: PAID, không REFUNDED, không CANCELLED, bỏ `is_simulated`. Đơn COD đã giao nhưng chưa PAID thì phải quyết định một lần và ghi vào phụ lục.
- **Sanity bắt buộc (test):**
  - Σ `series.orders` = `kpi.orders.value`.
  - Σ top 5 ≤ tổng doanh thu.
  - Δlog của ba nhân tố cộng lại bằng Δlog doanh thu (sai số ≤ 1e-9).
  - Đơn nhiều hơn lượt xem thì gắn cờ `tracking_gap`, không trả CR > 100% như số thật.
  - Kỳ có 0 lượt xem → `conversion_pct.value = None` và `pop_pct = None`.
- **Ranh giới tin cậy:** `timeRange` đã được kiểm (`_mart.py:43-46`); `shop_id` chỉ lấy từ gateway.

### 4.3 Model

1. **Baseline:**
   - Seasonal naive: doanh thu cùng kỳ trước.
   - Khoảng dự báo lấy từ phân vị thực nghiệm của sai số naive.
2. **Kiểm định PoP:** kiểm định chính xác tỉ số hai tần suất Poisson (`statsmodels.stats.rates.test_poisson_2indep`; venv có statsmodels 0.15.0 và scipy 1.18.1). Thay ngưỡng đọc bằng mắt kiểu "+50% là tốt" khi số đơn chỉ đi từ 2 lên 3.
3. **Khoảng kỳ vọng:** dùng lại model của F37 (SRS đăng ký ARIMA). Hiệu chỉnh khoảng bằng split-conformal trên sai số backtest của chính shop khi shop có ≥ 26 tuần lịch sử.
4. **Phân rã:** chỉ là đẳng thức, không có tham số. Khi một nhân tố bằng 0 thì log không xác định; khi đó báo "không phân rã được", không ép ra số.

Tất cả chạy trên CPU, chỉ cần statsmodels và scipy.

### 4.4 Học từ dữ liệu thật

- **Theo dõi độ phủ hằng tháng:** khoảng 80% của tháng trước có chứa doanh thu thật bao nhiêu lần? Lệch quá ±5 điểm thì hiệu chỉnh lại conformal.
- **Cold start:** dưới 90 ngày thì chỉ hiện số mô tả cộng cờ ý nghĩa PoP. Cờ PoP vẫn đúng với chuỗi ngắn.
- **Drift:** khi BE đổi định nghĩa trạng thái đơn hoặc luật lọc event, phải tăng `model_version` và chạy lại test đối chiếu tổng.

### 4.5 Bảo mật và chống gian lận

- **BR-174:** giữ test gateway. Thêm test: shop A gọi với `X-Shop-Id` của shop B qua đường dev thì bị chặn khi đã tắt cờ dev.
- **Demo đè shop thật:** email có trong `aiShopMap` bị ép sang demo kể cả khi đã có shop thật (`ai-gateway.service.ts:41-44`). Phải giữ `demo: true` và `DemoBanner`, và không bao giờ trộn số demo vào số live.
- **Đơn tự mua để thổi doanh thu:** bỏ đơn có người mua là chủ shop, hoặc trùng thiết bị/IP với chủ shop. Gắn cờ shop có tỉ lệ hoàn tiền cao bất thường.
- **Lượt xem ảo làm méo CR:** `session_id` do client tự gửi (`analytics.router.ts:9`), nên đổi session là lách được chống trùng; chỉ còn giới hạn 10 view/phút/IP (`event.service.ts:65-76`). Khi CR tụt mạnh do lượt xem tăng vọt từ ít IP, gắn cờ.
- **PII khi bật phản hồi khách:** che số điện thoại và email trong nội dung review; FE render dạng text, không render HTML.
- F26 không có LLM, nên không có rủi ro prompt injection.

### 4.6 Benchmark và kiểm chứng

| Kiểm chứng | Metric | Baseline | Đạt khi |
|---|---|---|---|
| Phân rã | Sai số đẳng thức | Không áp dụng | ≤ 1e-9 trên 1,000 cặp kỳ ngẫu nhiên lấy từ Olist |
| PoP có ý nghĩa | Tỉ lệ cờ giả trên chuỗi null | Luật "|PoP| > 20%" | Kiểm định cho tỉ lệ ≤ 5% ± 1 điểm; báo kèm tỉ lệ cờ giả của luật 20% để so |
| Khoảng kỳ vọng | Độ phủ 80%, pinball loss | Phân vị sai số seasonal naive | Độ phủ nằm trong [75%; 85%] (CI theo seller); Δpinball < 0 với CI không chứa 0 |
| Đối chiếu số | Σ series = KPI; top ≤ tổng | Không áp dụng | 100% test pass |

Nếu khoảng dự báo không thắng naive: chỉ hiện khoảng naive và ghi rõ là naive. Không gọi nó là AI.

## 5. Lộ trình

| Giai đoạn | Việc | Kết quả kiểm chứng |
|---|---|---|
| Ngay 1–2 ngày | Bỏ `or 0` ở PoP CR; thống nhất múi giờ; đọc `reviews` thật cho phản hồi khách; sửa đếm top | Test mới: 0 lượt xem → `pop_pct None`; đơn 01:00 giờ VN rơi đúng ngày |
| Ngay 1–2 ngày | Live neo kỳ theo hôm nay; `confidence` theo số liệu trong kỳ | Test shop ngừng bán 60 ngày → KPI 0, không còn số cũ |
| 1–2 tuần | Hàm "đơn tính doanh thu" dùng chung; phân rã driver; kiểm định PoP | Test đẳng thức; mô phỏng null 10,000 chuỗi |
| 1–2 tuần | Khoảng kỳ vọng dùng F37 + conformal; backtest trên Olist | Bảng độ phủ và pinball kèm CI theo seller |
| Khi có dữ liệu thật | Theo dõi độ phủ hằng tháng trên shop live | Dashboard nội bộ độ phủ, hiệu chỉnh lại khi lệch |

**Xong khi:**
- Khớp các BR và endpoint của mục SRS 3.8.1:
  - `GET /api/analytics/shop/overview` với `timeRange` 7d/30d/90d;
  - BR-174 chỉ dữ liệu shop đăng nhập;
  - BR-175 kỳ so sánh liền trước, dài bằng kỳ đang xem;
  - BR-176 CR = đơn / lượt xem × 100;
  - MSG129 khi lỗi;
  - trạng thái trống cho shop mới;
  - có phản hồi khách và lịch sử đơn.
- Mục "0 lượt xem → 0%" được ghi vào phụ lục SRS như sau: API trả `null`, FE hiện "0% (chưa có lượt xem)".
- Mọi PoP có cờ ý nghĩa thống kê; khoảng kỳ vọng có độ phủ đo được.

## 6. Hội đồng sẽ hỏi

- **"AI ở đâu trong trang tổng quan?"** Không có, và cũng không nên có. Đây là thống kê mô tả đúng như SRS. Phần thêm vào là kiểm định ý nghĩa và khoảng kỳ vọng, đều có số đo kiểm chứng.
- **"Sao CR không về 0% khi chưa có lượt xem như SRS ghi?"** Vì 0% nghĩa là "có người xem mà không ai mua", sai với sự thật. Đề xuất ghi vào phụ lục: API trả `null`, FE hiện "0% (chưa có lượt xem)".
- **"Doanh thu tăng 50% có đáng tin không?"** Với 2 lên 3 đơn thì không. Bản mới gắn cờ "không có ý nghĩa thống kê" kèm khoảng tin cậy.
- **"Số F26 có khớp số F28 không?"** Hiện tại thì không, vì hai bên định nghĩa "đơn" khác nhau. Sửa bằng một hàm dùng chung và một test đối chiếu.
