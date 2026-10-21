# F37 Dự báo doanh thu: roast và đường ra

> Endpoint `GET /api/analytics/forecast/revenue` (BE proxy `GET /api/seller/analytics/forecast/revenue`) · Trang FE "Dự báo doanh thu" (`FE/src/modules/analytics/pages/ForecastPage.tsx`) · File chính `app/api/v1/f37_forecast_revenue.py`, `app/core/build_marts.py:734-855`, `app/api/v1/_live_shop.py`, `app/core/benchmark_m5.py`, `docs/ADR-002.md` · Ngày 2026-10-21 · Người viết: Claude (subagent)

## 0. Bản đăng ký nói gì

| Hạng mục | SRS 3.10.1 Revenue Forecasting |
|---|---|
| Actor, trigger | Seller đã đăng nhập, bấm tab [Dự báo doanh thu] trong menu Demand Forecasting, mở `SellerRevenueForecastPage` |
| Endpoint | `GET /api/analytics/forecast/revenue`, Bearer JWT |
| Input | `targetId` (shop **hoặc listing**), `window` 30/60/90 |
| Output | Dự báo **views, orders, revenue** theo ngày, kèm cận dưới và cận trên CI 95% |
| Xử lý | AI service đọc chuỗi lịch sử từ MongoDB, tự chọn model, sinh dự báo và CI, Recharts vẽ |
| BR-205 | Bắt buộc dùng ARIMA khi lịch sử dưới 90 ngày, PyTorch LSTM khi từ 90 ngày |
| BR-206 | CI 95% luôn được trả về và vẽ ra |
| BR-207 | Không dự báo số âm; cận dưới CI kẹp ở 0 |
| Validation | Lịch sử dưới 7 ngày → empty state "Không đủ dữ liệu lịch sử…" |
| Lỗi | AI chậm quá 5 giây → MSG132 + [Thử lại]. Dự báo ra vô cực → bắt lỗi, ghi log, MSG149 |
| Màn hình | Đường liền cho lịch sử, đường đứt cho dự báo, vùng xanh nhạt cho CI 95%. Normal flow bước 5: đổi sang một listing với cửa sổ 90 ngày |

## 1. Roast: code hiện tại thực chất là gì

- Model là `SARIMAX(1,1,1)(1,0,1,7)` với bậc cứng, không dò bậc, không kiểm phần dư, `enforce_stationarity=False` (`build_marts.py:769-771`). Lỗi gì cũng nuốt vào `except Exception: return None`, không log (`:779-780`). Gọi đây là "auto-select model" thì hơi ngáo.
- Chọn model và báo điểm trên **cùng một** holdout 30 ngày (`:796-800`, rồi `:829`). Tao chạy đúng `du_bao_chuoi` trên Olist thật, cắt ngày 2018-07-01, rồi chấm 30 ngày tiếp theo:
  - 55 seller dày nhất (≥40% ngày có bán): MASE tự báo trung vị **0,659**, MASE thật về sau **0,719**;
  - tỉ lệ seller có MASE < 1 tụt từ 84% xuống 75%;
  - con số in lên FE là số đã được chọn lọc, nên lạc quan hơn thực tế.
- Trên MASE theo ngày, dự báo **luôn bằng 0** thắng model được chọn ở 64% seller (model chỉ thắng 36%). Với sai số tổng 30 ngày, model lệch trung vị 34,8%, còn "lấy trung bình 28 ngày qua" lệch 35,1%. Model thua phép trung bình đó ở 51% seller. SARIMA cấu hình cứng thì làm được đến vậy thôi.
- Bằng chứng duy nhất mà team trích là `ADR-002.md:46-52` (80 shop, ARIMA trung vị 0,9357). Số đó đo trên seed mà lượt xem được sinh bằng `nền × mùa vụ × hệ số thứ × tuổi` (`app/seed/behavior/task6_events.py:184-187`). Nhịp tuần do chính mình cài, rồi SARIMA tuần học lại được nhịp đó: vòng tròn vcl.
- `benchmark_m5.py` tên "M5" nhưng đéo có dòng M5 nào:
  - dữ liệu là `np.random.seed(42)` + Bernoulli × Poisson độc lập (`:43`, `:59-64`), không có nhịp tuần, không có xu hướng;
  - "ARIMA" thực ra là EWMA span 14 (`:123-127`);
  - metric là MAE chia cho naive "hôm qua" (`:110-112`, `:135-157`), không phải MASE;
  - kết luận "thể hiện rõ chu kỳ tuần", "thắng 15–35%" được viết cứng trong template (`:185-197`), trong khi bảng sinh ra là 0,89 và 1,00 (`docs/qc/m5_aggregation.md:18`).
- Rồi "ARIMA cấp listing MASE 1,12" từ cái benchmark giả đó được in thẳng cho seller đọc (`f37_forecast_revenue.py:98-101`) và ghi vào ADR (`docs/ADR-002.md:28-33`). Đây là bịa số. Câu "trung vị 41 ngày, 7,3% ngày có bán" (`:99`) cũng không có script nào trong repo tái lập. Seed hiện tại còn điền đủ 365 ngày cho listing hot và medium (`task9_listing_daily.py:119-129`).
- LSTM: route cũ trả 410 vì "trọng số ngẫu nhiên" (`app/api/v1/forecasting.py:7-14`), còn `lstm_mase` luôn `None` (`build_marts.py:819`). ADR-002 vẫn ghi "ĐANG MỞ" (`docs/ADR-002.md:3`) dù hạn chốt 29/09 (`:113`) đã qua gần một tháng.
- Lỗi nói sai tên model:
  ```python
  du = _arima(y, HORIZON_MAX) if dung_arima else None
  if du: ...
  else: tb = _seasonal_naive(y, HORIZON_MAX)   # nhưng ten_mo_hinh vẫn là "arima"
  ```
  Nếu refit ARIMA trên toàn chuỗi lỗi (`:802-806`), FE vẫn ghi "ARIMA" và in MASE của ARIMA (`:826`, `:829`), trong khi đường vẽ ra là seasonal naive.
- Test có 2 cái, chỉ kiểm "có 30 điểm" và "ít lịch sử thì insufficient" (`tests/test_live_paths.py:98-110`). Không test nào kiểm độ chính xác hay độ phủ CI.

### Lệch bản đăng ký

| Điểm | SRS | Code | Mức |
|---|---|---|---|
| BR-205, nhánh dưới 90 ngày | Chạy ARIMA | **Từ chối dự báo** khi dưới 90 ngày; thực tế cần ≥97 vì holdout phải ≥7 (`build_marts.py:788-794`) | Nặng |
| BR-205, nhánh từ 90 ngày | LSTM | SARIMA hoặc seasonal naive; LSTM null (`:819`), route LSTM trả 410 | Nặng |
| Validation dưới 7 ngày | Empty state chỉ khi dưới 7 ngày | Empty state khi dưới 90 ngày (`f37_forecast_revenue.py:54-56`, `_live_shop.py:39-42`) | Nặng |
| `targetId` listing | Shop hoặc listing | Listing bị `forbidden()` (`f37_forecast_revenue.py:39-41`); BE còn không chuyển `targetId` (`BE/src/modules/analytics/presentation/seller-analytics.router.ts:46`) | Nặng |
| Output | views, orders, revenue | Chỉ revenue | Nặng |
| Màn hình | Có đường lịch sử | API không trả lịch sử, FE không vẽ | Nặng |
| MSG149 | Bắt vô cực hoặc lỗi, báo seller | `mase()` ném `ValueError` khi có NaN (`metrics.py:11-12`), không ai bắt (`build_marts.py:798`); MASE = inf (`metrics.py:49-50`) làm `JSONResponse` ném lỗi (đã thử) | Nặng |
| BR-206 | Luôn có CI | Có `lo95`/`hi95` | Đạt |
| BR-207 | Cận dưới kẹp ở 0 | `max(0.0, …)` (`build_marts.py:823-824`) | Đạt |
| MSG132 | Phản hồi dưới 5 giây | Đo 0,3–1,3 giây/shop trên máy dev (5 seller Olist lớn nhất) | Đạt |

## 2. Mổ xẻ lỗi

| # | Mức | Chỗ | Lỗi | Hậu quả | Sửa nhanh |
|---|---|---|---|---|---|
| 1 | Chết người | `f37_forecast_revenue.py:98-101`, `ADR-002.md:28-33`, `build_marts.py:737-739` | Trích "MASE 1,12 / 0,89" từ benchmark mô phỏng, EWMA, MAE tương đối | Nói sai với seller và hội đồng | Xoá câu đó; chỉ trích số từ backtest thật (mục 4.6) |
| 2 | Chết người | `docs/qc/m5_aggregation.md:30`, `benchmark_m5.py:185-197` | Kết luận viết cứng, trái với bảng | Báo cáo khoa học giả | Đổi tên thành "mô phỏng", xoá kết luận hoặc chạy M5 thật |
| 3 | Nặng | `build_marts.py:788-794` | Lệch BR-205 nhánh dưới 90 ngày; ngưỡng thật là 97 | Shop mới không bao giờ có dự báo | Nhánh ARIMA cho 7–89 ngày (mục 4.3) |
| 4 | Nặng | `build_marts.py:819`, `forecasting.py:7-14` | Lệch BR-205 nhánh LSTM | Vi phạm cam kết đã đăng ký | LSTM global train offline, xuất ONNX (mục 4.3) |
| 5 | Nặng | `f37_forecast_revenue.py:39-41`, BE router `:46` | Chặn target listing | Mất normal flow bước 5 | Nhận `targetId` listing, kiểm sở hữu như BR-177 |
| 6 | Nặng | `build_marts.py:796-800,829` | Chọn và chấm trên cùng holdout | MASE lạc quan (0,659 so với 0,719 đo thật) | Rolling-origin; báo điểm trên origin không dùng để chọn |
| 7 | Nặng | `build_marts.py:802-806,826` | Refit lỗi thì vẽ naive nhưng ghi "arima" | Nhãn model sai | Đặt `ten_mo_hinh` theo dự báo thực sự dùng |
| 8 | Nặng | `docs/ADR-002.md:46-52` | Bằng chứng đo trên seed có nhịp tuần cài sẵn | Kết luận vòng tròn | Đo lại trên Olist (mục 4.6) |
| 9 | Vừa | `build_marts.py:807-810` | CI của naive rộng cố định cho mọi horizon, lấy sd toàn lịch sử | CI không phản ánh độ bất định tăng theo horizon | Conformal theo từng horizon (mục 4.3) |
| 10 | Nặng | `metrics.py:49-50`, `build_marts.py:798` | Lệch MSG149: không có lưới bắt lỗi | inf hoặc NaN thành HTTP 500 | Kiểm `isfinite`, trả insufficient kèm MSG149 |
| 11 | Vừa | `f37_forecast_revenue.py:59-60`, `_live_shop.py:18` | `confidence` gán cứng `medium` (seed) hoặc chỉ theo số ngày (live) | Nhãn tin cậy không gắn với số đo | Suy từ coverage backtest của shop |
| 12 | Vừa | `ForecastPage.tsx:41-52,130-137` | Không có CI cho tổng kỳ, chỉ cộng dồn dải từng ngày | Seller không có khoảng tin cậy cho con số họ cần | Trả `total_lo95`/`total_hi95` từ mô phỏng đường đi |
| 13 | Nhẹ | `f37_forecast_revenue.py:55`, `_live_shop.py:41` | Thông báo nói "90 ngày", thực tế cần 97 | Seller có 92 ngày vẫn bị từ chối | Sửa cùng #3 |
| 14 | Nặng | `f37_forecast_revenue.py:64-102` | Lệch output SRS: không có views, orders, không có chuỗi lịch sử cho chart | Thiếu output và màn hình đã đăng ký | Trả thêm `views`, `orders`, `history` |

Lệch bản đăng ký trong bảng này là #3, #4, #5, #10 và #14. Chi tiết từng điểm ở bảng "Lệch bản đăng ký" của mục 1.

## 3. Tính năng này nên là AI gì

Seller cần biết 30/60/90 ngày tới sẽ có bao nhiêu doanh thu, đơn và lượt xem, và chắc chắn đến đâu, để nhập hàng và chi quảng cáo. Bài toán ML:

- **Đầu vào:** chuỗi ngày của target (shop hoặc listing) gồm revenue, orders, views; lịch VN (thứ, lễ, Tết âm lịch qua `app/core/calendar_vn.py`, ngày đôi 9/9, 10/10, 11/11…); đặc trưng tĩnh (danh mục, tuổi shop).
- **Đầu ra:** với mỗi h = 1..window, các phân vị 2,5%, 50%, 97,5% (đúng CI 95% của BR-206, kẹp 0 theo BR-207), kèm CI cho tổng kỳ.
- **Nhãn:** chính giá trị tương lai. Không cần gán nhãn tay, nhưng bắt buộc chia theo thời gian.
- **Sự thật khó nghe:** 98% seller Olist bán dưới 40% số ngày (trung vị 3,5% ngày có bán, đo trên 3.029 seller). Ở cấp listing và shop nhỏ, dự báo trung thực là một khoảng rộng quanh mức trung bình. Giá trị AI thật nằm ở **khoảng tin cậy được hiệu chỉnh**, không nằm ở đường dự báo.

## 4. Đường ra: thiết kế AI chính hiệu

### 4.1 Dữ liệu: train / validation / test / thực

| Tập | Nguồn | Cách chia |
|---|---|---|
| Train | Olist: doanh thu và số đơn theo `seller_id` × ngày, và theo `product_id` × ngày cho cấp listing, 2017-01-01 → 2018-03-31 | Seller-disjoint 70% (GroupShuffleSplit theo `seller_id`) |
| Validation | Origin 2018-04 → 2018-05, seller nhóm train | Chọn siêu tham số, chọn model |
| Test | Origin 2018-06 → 2018-07 (horizon kết thúc trước 2018-08-31), 30% seller chưa thấy | Đọc một lần, ghi số lần đọc |
| Ngoài miền (tuỳ chọn) | M5 (Walmart): 30.490 chuỗi item × store, 1.941 ngày, horizon gốc 28 ngày. Giấy phép theo luật cuộc thi Kaggle **cần xác minh** trước khi dùng | Chỉ đánh giá, không train chung với Olist |
| Thực | `orders` PAID trên Atlas (hiện có 4 đơn) | Shadow mode (mục 4.4) |

- **Chống rò rỉ:**
  - đặc trưng lag và rolling chỉ tính từ dữ liệu trước origin;
  - chuẩn hoá theo từng chuỗi bằng thống kê của phần train;
  - không để seller test xuất hiện trong train của model global.
- **Không dùng seed làm bằng chứng:** nhịp tuần và mùa vụ của seed là tham số nhập tay (`docs/SEED_PARAMS.md:9-20`). Seed chỉ dùng để demo giao diện.
- Views không có trong Olist. Dự báo views chỉ chấm được trên `product_events` live khi đủ dữ liệu. Trước lúc đó, trả views kèm `confidence: low` và nói rõ chưa kiểm chứng.

### 4.2 Làm sạch và sanity

- Một định nghĩa doanh thu chung với F27 và F30: PAID, không CANCELLED, trừ hoàn tiền. Điền 0 theo lưới ngày GMT+7, như `_live_data.py:114-125`.
- Winsorize đơn lớn bất thường ở phân vị 99,5% của từng chuỗi train. Giữ cờ để F30 vẫn thấy chúng.
- Ranh giới tin cậy:
  - `window` chỉ nhận 30/60/90 (đã có, `f37_forecast_revenue.py:35-36`);
  - `targetId` phải là ObjectId thuộc shop của JWT;
  - mọi `yhat`, `lo95`, `hi95` phải hữu hạn, nếu không thì trả MSG149.
- Sanity bắt buộc (pytest):
  - khung đo: seasonal naive qua `rolling_origin` ra MASE ≈ 1 (đã có ở `backtest.py:113-118`);
  - mô hình biết trước tương lai ra MASE ≈ 0;
  - chuỗi toàn 0 → dự báo 0, CI [0, 0];
  - nhãn `model` khớp với dự báo thực sự trả về;
  - `lo95 ≤ yhat ≤ hi95`, `lo95 ≥ 0`.

### 4.3 Model

Giữ BR-205 làm luật định tuyến, và luôn chạy mốc song song để báo cáo:

| Lịch sử | Model theo SRS | Cách làm trung thực |
|---|---|---|
| < 7 ngày | Không | Empty state đúng câu SRS |
| 7–89 ngày | ARIMA | ARIMA bậc nhỏ chọn theo AICc trên lưới (p,d,q) ≤ (2,1,2); thêm mùa tuần chỉ khi ≥ 4 tuần. CI là CI của model, sau đó hiệu chỉnh conformal |
| ≥ 90 ngày | LSTM | **LSTM global** train offline bằng PyTorch trên máy dev, xuất **ONNX**, chạy bằng `onnxruntime` trên CPU. Server không cần torch. Đầu ra là 3 phân vị (pinball loss) |

- **Mốc bắt buộc, chạy cùng mọi target:**
  - seasonal naive 7 ngày;
  - trung bình 28 ngày qua;
  - ETS (statsmodels);
  - với chuỗi thưa: Croston-SBA. Phân loại thưa theo ADI/CV² với ngưỡng 1,32 và 0,49, theo Syntetos, Boylan và Croston 2005 (**cần xác minh** với bài gốc).
- **Ứng viên mạnh nhất về kỹ thuật:** model global kiểu LightGBM bằng `sklearn.ensemble.HistGradientBoostingRegressor(loss="quantile")`. Đặc trưng: lag 7/14/28, rolling mean, thứ, ngày lễ VN, khoảng cách tới Tết. Có sẵn trong sklearn 1.9.1, chạy CPU.
- **CI 95%:** conformal theo từng horizon trên phần dư của các origin validation. Cách này cho độ phủ gần đúng mà không cần giả định Gauss. Kẹp ở 0 theo BR-207.
- **Nếu LSTM thua mốc:** BR-205 vẫn bắt chạy LSTM, nên seller sẽ nhận dự báo tệ hơn mức có thể. Cách gần nhất mà vẫn trung thực: vẫn chạy và công bố số của LSTM, nhưng trả dự báo của model thắng backtest kèm `model_selection` ghi rõ lý do. **Cần cập nhật SRS/phụ lục BR-205** thành "≥ 90 ngày: LSTM là ứng viên bắt buộc đo; dùng model thắng backtest". Chưa sửa SRS thì giữ đúng chữ SRS và ghi Hạn chế.
- **Cấp listing:** ARIMA và LSTM trên chuỗi 3,5% ngày có bán gần như chắc chắn thua Croston-SBA, nhưng đó là giả thuyết phải đo. Nếu đúng như vậy, **cần cập nhật phụ lục BR-205** để thêm nhánh chuỗi thưa.

### 4.4 Học từ dữ liệu thật

- **Shadow mode:** mỗi ngày job ghi `forecast_point` kèm `origin_date` (hiện khoá không có trường này, `build_marts.py:747-753`). Khi có số thật, job chấm MASE, coverage và pinball cho từng shop. Đây là bằng chứng live duy nhất trung thực.
- **Cold start:** shop dưới 90 ngày dùng ARIMA (BR-205). Model global vẫn cho phân vị nhờ đặc trưng danh mục, và `confidence` suy từ coverage của nhóm danh mục trong backtest.
- **Retrain:**
  - model global retrain hằng tháng, có thể fine-tune trên dữ liệu VietCraft khi có ≥ 30 shop × 90 ngày;
  - ARIMA fit lại mỗi đêm;
  - LSTM xuất ONNX mới có hash và version, rollback được.
- **Drift:** coverage 95% trượt 4 tuần ra ngoài [90%, 98%] → cảnh báo và hiệu chỉnh lại conformal. PSI của phân phối doanh thu ngày lớn hơn 0,2 → xem xét retrain.

### 4.5 Bảo mật và chống gian lận

- **IDOR:** `targetId` listing phải thuộc `shop_id` của JWT. Giữ `forbidden()` (`f37_forecast_revenue.py:40-41`) và mở rộng cho listing.
- **Đơn ảo:** seller tự mua để đẩy dự báo. Chỉ tính đơn PAID, không hoàn, buyer khác shop owner. Nếu dự báo dùng cho quyết định của sàn (xếp hạng, quảng cáo), loại buyer có tỉ lệ hoàn bất thường.
- **Poisoning model global:** chỉ train trên Olist và dữ liệu đã qua lọc. Không để seller đẩy dữ liệu tuỳ ý vào tập train.
- **Chuỗi cung ứng model:** file ONNX được ghim SHA-256 trong config, và từ chối nạp nếu lệch hash.
- Không có LLM, nên không có prompt injection. Không trả dữ liệu của shop khác.

### 4.6 Benchmark và kiểm chứng

- **Giao thức:** `rolling_origin` (`app/core/backtest.py:15`) với `period=7`, `horizon` 30/60/90, `step=7`, 8 origin. Script mới `scripts/f37/backtest_olist.py` ghi `docs/F37_BACKTEST.json`.
- **Metric:**
  - MASE theo ngày;
  - **WAPE của tổng kỳ** (đúng con số `total_forecast_vnd` mà FE hiển thị);
  - pinball loss ở 3 phân vị;
  - **coverage 95%** và độ rộng CI trung bình;
  - sMAPE chỉ báo cho chuỗi cấp shop dày, vì sMAPE vô nghĩa khi có số 0.
  MASE theo ngày thưởng cho dự báo 0 trên chuỗi thưa (đã đo ở mục 1), nên không được dùng một mình.
- **Baseline cụ thể:** dự báo 0, trung bình 28 ngày, seasonal naive, ETS, Croston-SBA.
- **CI:** bootstrap theo cụm seller, 1.000 vòng. So model với mốc bằng bootstrap ghép cặp.
- **Cổng "đạt khi":**
  - WAPE tổng kỳ thấp hơn mốc "trung bình 28 ngày" với CI ghép cặp không chứa 0;
  - coverage 95% nằm trong [92%, 97%] trên tập test;
  - pinball thấp hơn mốc quantile thực nghiệm.
- **Sanity:** xáo thứ tự ngày trong train → model phải mất lợi thế so với seasonal naive. Ghi số lần đọc test.
- **Nếu không thắng:** công bố bảng như hiện có. Model chính là mốc thắng, LSTM ghi "đã đo, thua". Không viết "AI dự báo chính xác".

## 5. Lộ trình

| Giai đoạn | Việc | Kết quả kiểm chứng |
|---|---|---|
| Ngay 1–2 ngày | Xoá câu "MASE 1,12" ở f37/ADR/build_marts; đổi tên `benchmark_m5.py` và báo cáo thành "mô phỏng", bỏ kết luận viết cứng; sửa nhãn model (#7); lưới MSG149; empty state khi dưới 7 ngày | grep không còn "1,12"; pytest sanity mục 4.2 xanh |
| 1–2 tuần | Pipeline Olist + rolling-origin + baseline + HistGB quantile + conformal; ARIMA 7–89 ngày; LSTM ONNX; target listing; views và orders; trả lịch sử cho chart | `docs/F37_BACKTEST.json` có CI; bảng so sánh có số thật cả LSTM |
| Khi có dữ liệu thật | Shadow mode ≥ 30 shop × 90 ngày; fine-tune; theo dõi coverage | Coverage live nằm trong [90%, 98%] |

**Xong khi:**
- trên tập test Olist seller-disjoint, model được chọn thắng "trung bình 28 ngày" về WAPE tổng kỳ có CI, và coverage 95% nằm trong [92%, 97%];
- không còn số nào trên FE hay trong docs mà không có script tái lập;
- khớp các BR và endpoint của mục SRS 3.10.1:
  - `GET /api/analytics/forecast/revenue` nhận `targetId` (shop hoặc listing) và `window` 30/60/90;
  - output có views, orders, revenue;
  - BR-205 có ARIMA khi dưới 90 ngày và LSTM khi từ 90 ngày (hoặc phụ lục đã cập nhật);
  - BR-206 luôn có CI 95%;
  - BR-207 cận dưới kẹp ở 0;
  - empty state khi dưới 7 ngày;
  - MSG132 và MSG149 đúng hành vi.

## 6. Hội đồng sẽ hỏi

1. **"Train ở đâu, đánh giá trên gì?"** Train trên Olist thật, seller-disjoint, rolling-origin. Không dùng seed, vì seed có nhịp tuần nhập tay. Số cũ trên seed (0,9357) bị rút lại vì vòng tròn.
2. **"Sao không có LSTM như BR-205?"** Server không cài torch, nên LSTM train offline rồi chạy bằng ONNX. Nếu LSTM thua mốc, bọn em vẫn công bố số và đề nghị sửa phụ lục BR-205. Bọn em không giấu kết quả.
3. **"Benchmark M5 của nhóm đâu?"** Bản cũ là mô phỏng, và "ARIMA" trong đó là EWMA. Bọn em đã gỡ khỏi lập luận. Nếu dùng M5 thật thì phải xác minh giấy phép Kaggle trước.
4. **"Dự báo có chính xác không?"** Với shop nhỏ, sai số tổng 30 ngày khoảng một phần ba (đo trên Olist). Vì vậy sản phẩm đưa ra khoảng tin cậy đã hiệu chỉnh và nói thẳng độ bất định.
5. **"Listing bán 3% số ngày thì dự báo làm gì?"** Dùng Croston-SBA và khoảng rộng. Nếu ARIMA hoặc LSTM thua thì bọn em báo thẳng và xin sửa phụ lục.
