# F31 Doanh thu theo loại: roast và đường ra

> Endpoint `GET /api/analytics/shop/categories/revenue?timeRange=` (BE proxy `GET /api/seller/analytics/categories`) · Trang FE "Doanh thu theo loại" `/seller/insights/categories` (`FE/src/modules/analytics/pages/CategoriesPage.tsx`) · File chính `app/api/v1/f31_category_revenue.py`, `app/api/v1/_live_category_revenue.py` · Ngày 2026-10-21 · Người viết: Claude (subagent)

## 0. Bản đăng ký nói gì

| Hạng mục | SRS 3.8.6 Category Revenue Reports (`report3.txt:5044-5095`) |
|---|---|
| Actor, trigger | Seller đã đăng nhập; bấm [Báo cáo danh mục] trong menu Analytics |
| Endpoint | `GET /api/analytics/shop/categories/revenue`, Bearer JWT |
| Input | `timeRange` (string, bắt buộc) |
| Output | Doanh thu chia theo loại sản phẩm (ví dụ T-shirt, Mug, Poster) kèm %; ma trận tần suất đơn theo thứ (Thứ Hai đến Chủ Nhật) × giờ (0–23) |
| Xử lý | Gom doanh thu theo loại trong khoảng đã chọn; lấy giờ và thứ của mọi đơn thành công **trong khoảng đó**; dựng ma trận |
| BR-185 | Giờ trên heatmap phải quy về giờ Việt Nam (GMT+7) |
| Validation | Không có đơn trong khoảng → trạng thái trống "Chưa có đơn hàng để phân tích" (MSG135) |
| Abnormal | Lỗi gọi API → trạng thái lỗi (MSG131) |
| Màn hình | `CategoryRevenueReportPage.tsx`: biểu đồ tròn có tooltip %; lưới heatmap (trục Y Thứ Hai–Chủ Nhật, trục X 00:00–23:00, đậm nhạt theo số đơn) |
| Post-condition | Seller biết loại nào lãi nhất và khung giờ tốt để chạy khuyến mãi hoặc quảng cáo |

SRS không gọi F31 là AI. Đây là group-by cộng một ma trận đếm. Đó là thống kê mô tả, và **nên giữ như vậy**.

## 1. Roast: code hiện tại thực chất là gì

- **Không có AI.** Nhánh seed là một `$group` theo `product_type_id` và một `find` trên `mart_shop_hour` (`f31_category_revenue.py:32-37`, `:50-51`). Nhánh live là hai vòng for. Làm vậy đúng việc. Chỉ cần đừng ai gọi nó là "AI tìm giờ vàng".
- **Seed: giờ Brazil dán nhãn giờ Việt Nam.**
  - Code tự thú: nhịp giờ/thứ kế thừa từ Olist Brazil (`f31:74-75`). Docstring của mart còn nói rõ `ordered_at` "đã là giờ địa phương, nên không cộng trừ thêm" (`build_marts.py:685-686`). Giờ địa phương ở đây là giờ Brazil.
  - Thế mà response vẫn ghi `"heatmap_tz": "Asia/Ho_Chi_Minh"` (`f31:67`), và `peak_window.note` trình bày như hiểu biết về chính shop (`f31:68-72`). Phần limitation thì thật thà, nhưng cái nhãn múi giờ thì nói dối, vl.
- **Live: BR-185 chỉ đúng nếu server tình cờ chạy giờ VN.**
  - `order_hour_of_week` được BE tính bằng `now.getDay() * 24 + now.getHours()`, tức theo đồng hồ local của server (`order.service.ts:347`, `replacement-order.service.ts:120`).
  - Image `node:22-alpine` không đặt `TZ` (`BE/Dockerfile`), và `.env` của BE cũng không có `TZ`. Vậy nếu môi trường deploy không tự đặt thì đó là giờ UTC (cần xác minh biến môi trường lúc deploy).
  - AI service nhận số đó rồi dán nhãn `Asia/Ho_Chi_Minh` (`_live_category_revenue.py:146`). Giờ vàng có thể lệch 7 tiếng. Đơn 20:00 tối ở VN hiện thành 13:00 chiều. Vcl.
- **Live cần ≥ 20 đơn PAID từ trước tới nay** (`_live_category_revenue.py:14`, `:73-78`). Atlas có 4 đơn cho cả sàn, nên mọi shop thật đều nhận `insufficient`. Tính năng live hiện chưa bao giờ trả được số.
- **Giờ vàng từ 20 đơn là xổ số, đéo phải insight.**
  - 20 đơn rải trên 168 ô, trung bình 0.12 đơn mỗi ô.
  - Kể cả khi đơn rải **ngẫu nhiên đều**, xác suất có một ô chứa ≥ 2 đơn là 69% (tao tính bằng công thức bài toán ngày sinh). Khi đó code sẽ tuyên bố "10% đơn của shop rơi vào khung này" (`:147-151`).
  - Nếu hai ô bằng nhau thì ô nào thắng là do thứ tự trả về từ DB (`:90-91`).
- **Danh mục là chữ tự do, và field thì mang tên lừa.**
  - `product_type_id` và `name_vi` thực ra chứa chuỗi `categories` do seller tự gõ (`:136-137`).
  - Một sản phẩm có nhiều danh mục thì doanh thu được cộng vào **mỗi** danh mục (`:125-129`). `share_pct` lại chia cho tổng đã bị cộng trùng (`:131`, `:141`), còn `total_revenue_vnd` là tổng subtotal thật (`:118`, `:143`).
  - Kết quả: cộng `by_product_type` lớn hơn tổng doanh thu. Code có thú nhận trong limitation (`:153-155`), nhưng thú nhận rồi vẫn để field tên `product_type_id`.
- **Hàm `_tien_don` bị copy y nguyên** (`_live_category_revenue.py:35-46`, giống hệt `_live_data.py:13-23`). Mai sửa một bản là hai trang lệch nhau.
- **Cửa sổ neo theo đơn cuối, tính ngày theo UTC** (`:49-53`, `:95-103`). Đơn lúc 00:00–06:59 giờ VN rơi vào ngày hôm trước. Shop ngừng bán 3 tháng vẫn thấy "30 ngày" đầy số.
- **Ghi nhận điểm tốt.**
  - Limitation nói thẳng chuyện Olist và chữ tự do (`f31:74-75`, `_live:153-155`).
  - FE đặt cảnh báo ngay cạnh heatmap, và nói rõ heatmap tính trên toàn lịch sử (`CategoriesPage.tsx:8-12`, `:171`).
  - `_gio_tuan` đổi đúng từ dow kiểu JS sang ISO (`:56-61`).
  - Live chỉ đọc đơn PAID của shop thật.
- **Test:** không có test nào cho F31 trong `tests/`.

### Lệch bản đăng ký

| Điểm | SRS 3.8.6 | Code | Mức |
|---|---|---|---|
| BR-185 GMT+7 | Bắt buộc | Seed: giờ Brazil; live: giờ theo đồng hồ server; cả hai đều dán nhãn `Asia/Ho_Chi_Minh` | Chết người |
| Cửa sổ heatmap | Đơn thành công **trong khoảng đã chọn** | Toàn bộ lịch sử (`f31:73`, `_live:152`) | Nặng |
| Phân theo loại sản phẩm | T-shirt, Mug, Poster | Live dùng chữ tự do, cộng trùng khi sản phẩm có nhiều danh mục | Nặng |
| Validation MSG135 | 0 đơn trong khoảng → trạng thái trống | Dưới 20 đơn từ trước tới nay → `insufficient` với câu khác. Đủ 20 nhưng 0 đơn trong khoảng → trả `ok` với mảng rỗng. Grep MSG135 = 0 kết quả | Nặng |
| Ngưỡng 20 đơn | Không đăng ký | Chặn cứng (`_live:73-78`) | Nặng, chuyển thành nhãn tin cậy |
| Biểu đồ tròn | Pie chart có tooltip % | Bảng có thanh ngang (`CategoriesPage.tsx:86-114`) | Nặng |
| Tên trang, MSG131 | `CategoryRevenueReportPage`, [Báo cáo danh mục], MSG131 | `CategoriesPage`, "Doanh thu theo loại" (`nav.ts:59`); không có mã MSG131 | Nặng |

## 2. Mổ xẻ lỗi

Dòng có nhãn **[Lệch SRS]** là phần lệch bản đăng ký, xếp mức Chết người hoặc Nặng.

| # | Mức | Chỗ | Lỗi | Hậu quả | Sửa nhanh |
|---|---|---|---|---|---|
| 1 | Chết người | `f31:67`, `_live:146`, `order.service.ts:347` | [Lệch SRS] Nhãn GMT+7 không đúng với dữ liệu | Giờ vàng sai, có thể lệch 7 tiếng | Live tự tính thứ/giờ từ `created_at` theo `Asia/Ho_Chi_Minh`; seed ghi `heatmap_tz: "America/Sao_Paulo (Olist)"` |
| 2 | Chết người | `_live:147-151` | Tuyên bố giờ vàng từ ô có 2 đơn | Khoảng 69% shop 20 đơn rải đều vẫn bị báo có "giờ vàng" | Chỉ báo giờ vàng khi qua kiểm định (mục 4.3) |
| 3 | Nặng | `f31:73`, `_live:152` | [Lệch SRS] Heatmap tính trên toàn lịch sử | Lệch SRS; bấm đổi khoảng thời gian cũng không đổi | Tính trong khoảng, co về toàn lịch sử của shop (mục 4.3) |
| 4 | Nặng | `_live:125-141` | [Lệch SRS] Chữ tự do, cộng trùng, field tên sai | Số loại sản phẩm không cộng ra tổng | Quy về loại chuẩn, mỗi dòng hàng chỉ một loại |
| 5 | Nặng | `_live:73-78` | [Lệch SRS] Gate cứng 20 đơn từ trước tới nay | Mọi shop live đều trống; lệch MSG135 | 0 đơn trong khoảng → MSG135; 1–19 đơn → trả số kèm `confidence: low` |
| 6 | Nặng | `_live:95-103`, `:49-53` | Neo theo đơn cuối, ngày tính theo UTC | Kỳ sai | Neo theo hôm nay, ngày theo giờ VN |
| 7 | Nặng | `CategoriesPage.tsx:86-114` | [Lệch SRS] Không có pie chart, không có MSG131 | Lệch màn hình | Thêm Recharts `PieChart`; gắn mã lỗi |
| 8 | Vừa | `_live:29` | Chỉ lọc `payment_status: PAID`, không loại `order_status: CANCELLED` hay đơn đã hoàn | Đơn đã trả rồi huỷ vẫn được tính | Dùng hàm định nghĩa đơn dùng chung với F26 và F28 |
| 9 | Vừa | `_live:35-46` | Copy `_tien_don` | Hai bản dễ lệch nhau | Import từ `_live_data` |
| 10 | Vừa | `_live:90-91` | Hai ô bằng nhau phân thắng thua theo thứ tự DB | Giờ vàng không ổn định | Báo hoà, hoặc dùng ước lượng đã làm trơn |

## 3. Tính năng này nên là AI gì

**Kết luận:**
- Phần "doanh thu theo loại" **giữ là thống kê**. Không có gì để học ngoài việc quy chữ tự do về loại chuẩn.
- Phần heatmap cũng giữ đúng hợp đồng SRS: ma trận đếm. Thêm một lớp ước lượng có kiểm chứng, vì với vài chục đơn thì ma trận thô gần như toàn nhiễu, mà Post-condition của SRS lại hứa "khung giờ tốt để chạy khuyến mãi".

| Lớp | Bản chất | Output thêm, giữ nguyên field cũ | Kiểm chứng |
|---|---|---|---|
| Quy loại sản phẩm | Luật cộng embedding đã có | `product_type` chuẩn cho mỗi dòng hàng, kèm `type_source` | Accuracy trên 79 sản phẩm live gán nhãn tay |
| Heatmap đã làm trơn | Mô hình đếm Poisson: log λ(thứ, giờ) = a_thứ + b_giờ, co theo cấp bậc về nhịp toàn sàn | `heatmap_smoothed` kèm khoảng; `heatmap` thô vẫn trả đúng như SRS | Log-likelihood của đơn kỳ sau trên Olist |
| Giờ vàng có điều kiện | Xác suất hậu nghiệm ô (hoặc khối 3 giờ) cao hơn trung bình | `peak_window` chỉ khi P > 0.9; nếu không thì `null` kèm "chưa đủ đơn" | Tỉ lệ trúng (hit rate) đơn kỳ sau |

- **Dự báo cầu theo ngày** để chọn ngày chạy khuyến mãi đã có ở F37 (doanh thu) và F38 (mùa vụ). F31 không làm lại; chỉ link sang.
- **Nhịp giờ VN thật chỉ học được từ đơn VietCraft.** Olist chỉ dùng để chứng minh phương pháp làm trơn tốt hơn ma trận thô, không dùng để nói "người Việt mua lúc 20:00".

## 4. Đường ra: thiết kế AI chính hiệu

### 4.1 Dữ liệu: train / validation / test / thực

| Nguồn | Dùng cho | Chia |
|---|---|---|
| Olist: 99,441 đơn, 3,095 seller; 818 seller có ≥ 20 đơn (tao đếm) | Benchmark làm trơn heatmap và giờ vàng | Theo thời gian: fit trên đơn trước 2018-01-01, test trên đơn từ 2018-01-01. Có 323 seller đủ ≥ 20 đơn trước mốc và ≥ 10 đơn sau mốc (tao đếm). Giữ 20% seller làm validation để chọn độ co. CI bootstrap theo seller |
| Mô phỏng: đơn rải đều trên 168 ô | Null test cho giờ vàng | 10,000 shop giả, mỗi shop 20–200 đơn |
| 79 sản phẩm Atlas (chỉ đọc tên, danh mục, ảnh) | Đo độ đúng của việc quy loại | Gán nhãn tay 1 lần; không dùng để tune |
| Đơn VietCraft live | Nhịp giờ VN thật | Khi sàn có ≥ 500 đơn PAID thì thay prior toàn sàn Olist bằng prior VietCraft |

Giờ Olist là giờ địa phương Brazil. Mọi báo cáo về Olist phải ghi rõ: kết quả chỉ chứng minh phương pháp, không phải nhịp mua của người Việt.

### 4.2 Làm sạch và sanity

- **BR-185:** AI service tự tính thứ và giờ từ `created_at` theo `Asia/Ho_Chi_Minh`, không tin `order_hour_of_week` do BE ghi.
  - Thêm test: đơn lúc 2026-10-20T13:30Z phải rơi vào Thứ Ba lúc 20 giờ.
  - Seed không được ghi `Asia/Ho_Chi_Minh`.
- **Định nghĩa đơn thành công dùng chung với F26 và F28:** PAID, không huỷ, không hoàn, bỏ `is_simulated`.
- **Quy loại:**
  - Thứ tự ưu tiên: `doan_loai_phoi` theo tên (`_live.py:79-101`, có self-check ở `:216-252`) → `category_map.json` của Listing Intel (TECH_REPORT ghi 79/79 sản phẩm Atlas ánh xạ được) → nhóm `(chưa phân loại)`.
  - Mỗi dòng hàng chỉ thuộc **một** loại.
- **Sanity bắt buộc:**
  - Σ doanh thu theo loại = `total_revenue_vnd`.
  - Σ `share_pct` = 100 ± 0.1.
  - Σ ô heatmap = số đơn trong khoảng.
  - 0 đơn trong khoảng → MSG135.
- **Ranh giới tin cậy:** `timeRange` qua `doc_khoang` (`_mart.py:43-46`); `shop_id` chỉ lấy từ gateway.

### 4.3 Model

1. **Baseline:**
   - B0: ma trận thô của shop, cộng 0.5 vào mỗi ô.
   - B1: nhịp toàn sàn, giống nhau cho mọi shop.
   - B2: phân bố đều.
2. **Model chính:** Poisson GLM với hiệu ứng thứ + giờ (31 tham số thay vì 168), fit bằng `statsmodels`.
   - Co về nhịp toàn sàn bằng cách dùng nhịp toàn sàn làm offset, rồi phạt L2 phần lệch của shop. Độ phạt chọn trên seller validation.
   - Khi shop có đủ đơn (chọn ngưỡng trên validation), thêm tương tác thứ × giờ theo khối 3 giờ.
3. **Giờ vàng:** mô phỏng hậu nghiệm bằng bootstrap tham số. Chỉ báo khối 3 giờ có P(λ_khối > trung bình) > 0.9.
4. **Quy loại:** luật trước. Phần `unknown` dùng zero-shot SigLIP2 đã có (`listing_intel/embedder.py`, ONNX, CPU) trên tên và ảnh, so với nhãn loại.

Cả ba đều chạy trên CPU, không cần torch.

### 4.4 Học từ dữ liệu thật

- **Prior nhịp toàn sàn** chuyển từ Olist sang VietCraft khi có ≥ 500 đơn PAID, kèm `prior_source` trong meta.
- **Cold start:** shop dưới khoảng 50 đơn thì heatmap làm trơn gần như bằng nhịp toàn sàn. Khi đó ghi rõ "phần lớn là nhịp chung của sàn".
- **Retrain:** fit lại prior hằng tuần trong batch. Theo dõi drift bằng khoảng cách giữa nhịp tuần này và prior (Jensen–Shannon). Lệch nhiều thì gắn cờ và xem lại. Mùa Tết hay Black Friday sẽ làm nhịp đổi.
- **Phản hồi:** nếu seller chạy khuyến mãi theo giờ vàng, log khung đã chọn và đơn trong khung đó. Đây chỉ là dữ liệu quan sát; muốn nhân quả thì phải A/B khung giờ khuyến mãi khi có đủ shop.

### 4.5 Bảo mật và chống gian lận

- **Đơn tự mua dồn vào một khung giờ** để làm đẹp báo cáo: bỏ đơn có người mua là chủ shop hoặc trùng thiết bị/IP. Gắn cờ khung giờ có nhiều đơn từ cùng một người mua.
- **Lộ dữ liệu giữa các shop:** prior toàn sàn chỉ công bố khi có ≥ 5 shop đóng góp, để không suy ngược ra đơn của một shop nhỏ.
- **Zero-shot quy loại:** tên sản phẩm do seller nhập nên chỉ là dữ liệu. SigLIP không phải LLM sinh text, nên không có prompt injection. Tải ảnh phải qua allowlist host đã có ở Listing Intel (`listing_intel/image_fetch.py:10`, `:38-41`) để chống SSRF.
- F31 không có LLM.

### 4.6 Benchmark và kiểm chứng

| Kiểm chứng | Metric | Baseline | Đạt khi |
|---|---|---|---|
| Làm trơn heatmap (Olist, mốc 2018-01-01) | Log-likelihood trung bình mỗi đơn của kỳ test | B0, B1, B2 | GLM thắng baseline tốt nhất; CI 95% bootstrap theo seller của chênh lệch không chứa 0 |
| Giờ vàng | Hit rate: tỉ lệ đơn kỳ sau rơi vào khối được báo | B0 top khối, B1 top khối; ngẫu nhiên = 3/24 | Hit rate cao hơn B0 có CI; độ phủ (tỉ lệ shop được báo giờ vàng) công bố kèm |
| Null giờ vàng | Tỉ lệ shop giả rải đều bị báo có giờ vàng | Luật hiện tại (khoảng 69% ở 20 đơn) | ≤ 10% |
| Quy loại | Accuracy và độ phủ trên 79 sản phẩm gán tay | Chữ tự do `categories[0]` | Công bố số đếm; không đặt cổng vì n quá nhỏ |
| Đối chiếu số | Σ theo loại = tổng; Σ ô = số đơn | Không áp dụng | 100% test pass |

Nếu GLM không thắng B1 (nhịp toàn sàn): kết luận thẳng là với lượng đơn hiện tại, nhịp chung của sàn là dự báo tốt nhất. Khi đó hiển thị nhịp chung, ghi rõ, và không bịa giờ vàng riêng cho shop.

## 5. Lộ trình

| Giai đoạn | Việc | Kết quả kiểm chứng |
|---|---|---|
| Ngay 1–2 ngày | Tính thứ/giờ theo `Asia/Ho_Chi_Minh` ở AI; sửa nhãn tz của seed; heatmap theo khoảng; bỏ gate 20 đơn, thêm MSG135 | Test đơn 13:30Z → Thứ Ba 20 giờ; 0 đơn trong khoảng → MSG135 |
| Ngay 1–2 ngày | Mỗi dòng hàng một loại; Σ theo loại = tổng; import `_tien_don` | Test đối chiếu tổng |
| 1–2 tuần | Pipeline Olist: B0/B1/B2 so với GLM; null test giờ vàng; gán tay 79 sản phẩm | Bảng log-likelihood, hit rate kèm CI; tỉ lệ báo nhầm trên null |
| 1–2 tuần | FE: pie chart, `heatmap_smoothed`, giờ vàng có điều kiện | Ảnh chụp E2E |
| Khi có dữ liệu thật | Prior VietCraft khi có ≥ 500 đơn; theo dõi drift theo tuần | Báo cáo prior VN so với Olist |

**Xong khi:**
- Khớp các BR và endpoint của mục SRS 3.8.6:
  - `GET /api/analytics/shop/categories/revenue` với `timeRange` bắt buộc;
  - doanh thu theo loại sản phẩm trong khoảng;
  - heatmap thứ × giờ từ đơn thành công trong khoảng;
  - BR-185 giờ GMT+7 có test;
  - MSG135 khi 0 đơn;
  - MSG131 khi lỗi;
  - pie chart.
- Giờ vàng chỉ hiện khi qua kiểm định, và có số null test kèm theo.
- Không còn chỗ nào gọi F31 là AI, trừ lớp làm trơn đã có benchmark.

## 6. Hội đồng sẽ hỏi

- **"Giờ vàng này là AI dự đoán à?"** Bản hiện tại chỉ là đếm thô, và trên seed còn là giờ Brazil. Bản mới là mô hình đếm có co Bayes, kiểm bằng log-likelihood của đơn kỳ sau. Giờ vàng chỉ được báo khi xác suất đủ cao.
- **"Sao không vẽ heatmap theo khoảng như SRS?"** Bản mới làm đúng SRS: heatmap thô theo khoảng. Lớp làm trơn là thêm vào để giải quyết chuyện vài chục đơn không đủ cho 168 ô.
- **"Nhịp giờ này có phải của người Việt không?"** Chưa. Olist chỉ chứng minh phương pháp. Nhịp VN cần đơn VietCraft thật, và sàn mới có 4 đơn.
- **"Doanh thu theo loại có cộng đúng tổng không?"** Hiện tại thì không, vì sản phẩm nhiều danh mục bị cộng trùng. Bản mới gán mỗi dòng hàng vào đúng một loại, có test đối chiếu tổng.
