# Đối chiếu tầng dữ liệu với 47 feature trong report

Trả lời thẳng câu hỏi trước: **0 / 47 feature đã hoàn thành.**

Cái đang có là **nền dữ liệu**, không phải feature. Feature cần: dữ liệu + mô hình + API + giao diện. Hiện mới xong mắt xích đầu.

Nhưng con số đó không nói lên nhiều. Câu hỏi hữu ích hơn: *feature nào đã có đủ dữ liệu để bắt tay dựng ngay, và feature nào còn bị chặn?*

---

## Tổng quan

| Nhóm | Số feature | Tầng dữ liệu đóng góp |
|---|---|---|
| Sàn TMĐT (1–25, 42–47) | 31 | Không — đây là backend/frontend thuần |
| AI Product Analytics (26–41) | 16 | Có, một phần |

Tầng dữ liệu này chỉ nhắm vào 16 feature AI. 31 feature còn lại là công việc hoàn toàn khác.

---

## Chi tiết 16 feature AI

### Đã có đủ dữ liệu, chỉ chờ dựng mô hình — 3 feature

| # | Feature | Dữ liệu đang có | Còn thiếu |
|---|---|---|---|
| 37 | Revenue Forecasting | ~4.000 điểm daily *(sau khi chạy backfill daily)* | `auto_arima`, CI 95% |
| 38 | Seasonal Trend Forecasting | **11.790 điểm weekly, 5 năm** | STL period=52, content calendar |
| 30 | Anomaly Detection | Chuỗi daily | Z-score cửa sổ 7 ngày |

Feature 38 là mạnh nhất. Đã đo được biên độ mùa vụ thật: `quà 20/10` và `quà 20/11` có tỷ lệ đỉnh/trung bình **44×**, `quà 8/3` là 43×. STL sẽ tách rất sạch.

**Lưu ý cho 37:** feature này trong report là dự báo *doanh thu*, không phải dự báo *cường độ tìm kiếm*. Hai biến mục tiêu khác nhau — xem mục "Hai bài toán dự báo" bên dưới.

### Có một nửa dữ liệu — 3 feature

| # | Feature | Đã có | Còn thiếu |
|---|---|---|---|
| 35 | Competitive Pricing | Giá vốn Printify (sàn giá) | Giá bán thị trường → Etsy hoặc Amazon Reviews 2023 |
| 39 | Niche Gap Score | Vế demand (tốc độ tăng Trends) | Vế supply (mật độ cạnh tranh) → Etsy |
| 40 | Emerging Niche Radar | — | `trend_related` **đang rỗng**, chưa chạy `--related` |

Feature 39 đúng là định nghĩa Gap: demand cao + supply thấp. Không có vế supply thì chỉ còn "growth ranking", không phải "gap".

### Bị chặn vì chờ Etsy duyệt — 4 feature

| # | Feature | Cần |
|---|---|---|
| 32 | In-Category Competitor Analysis | Listing đối thủ |
| 33 | Shop Comparison Radar | Dữ liệu shop |
| 34 | Tag Gap Analysis | **13 tag mỗi listing Etsy** |
| 36 | Competitor Tracking | Listing theo shop |

Feature 34 phụ thuộc hoàn toàn vào Etsy tag — không có nguồn thay thế. Ba cái còn lại có thể lùi về Amazon Reviews 2023 (Clothing) với chất lượng thấp hơn.

### Bị chặn vì chưa có dữ liệu nội bộ — 6 feature

| # | Feature | Cần |
|---|---|---|
| 26 | Shop Performance Overview | Sự kiện VietCraft |
| 27 | Per-Listing Performance | Sự kiện VietCraft |
| 28 | Conversion Rate Analysis | views → orders |
| 29 | Listing Health Score | Conversion thật |
| 31 | Category Revenue Reports | Đơn hàng |
| 41 | Investment Recommendations | Tổng hợp 37 + 39 + hiệu suất |

VietCraft chưa có buyer nên chưa có sự kiện nào. Sáu feature này **bắt buộc dùng dữ liệu mô phỏng** — nhưng phải hiệu chỉnh từ phân phối thật (mùa vụ ← Trends đã thu, giá ← Printify/Etsy, tỷ lệ chuyển đổi ← Olist), không được bịa số.

---

## Trạng thái so với chỉ số đánh giá trong report

| Chỉ số | Yêu cầu | Trạng thái |
|---|---|---|
| Forecasting MAE ≤10%, RMSE ≤15% | Feature 37 | Có dữ liệu, chưa có mô hình. **Cần sửa giao thức đánh giá** |
| Niche Gap Spearman ≥0.70 | Feature 39 + 2 chuyên gia | Thiếu vế supply. Chưa liên hệ chuyên gia |
| Health Score Pearson ≥0.65 | Feature 29 | Chưa có conversion thật. **Rủi ro vòng tròn** |
| API p95 <2s | Toàn hệ thống | Chưa có API |
| SUS ≥70 | UAT | Chưa có giao diện |
| 47 use case, coverage 80% | Toàn hệ thống | 0/47 |

### Hai bài toán dự báo đang bị gộp làm một

Report viết `MAE ≤ 10%` cho "30-day revenue/views forecasting". Nhưng trong pipeline hiện tại có **hai chuỗi thời gian khác loại**:

| | Bài toán A | Bài toán B |
|---|---|---|
| Feature | 38, 39, 40 | **37** |
| Biến mục tiêu | Chỉ số quan tâm tìm kiếm (0–100) | Doanh thu, lượt xem, đơn |
| Nguồn | Google Trends | Sự kiện VietCraft |
| Kiểm định trên | Holdout thời gian trên chính chuỗi Trends | Olist / M5 (giao dịch thật) |
| Chỉ số phù hợp | **MASE**, sMAPE | MAE, RMSE |

`MAE ≤ 10%` trên chỉ số Trends không có nghĩa — nó là chỉ số tương đối không đơn vị, 10% của cái gì? Dùng **MASE** (MAE ÷ MAE của naive baseline). Report đã có sẵn naive baseline nên khớp luôn, và MASE < 1 nghĩa là mô hình thắng baseline.

**Và không được đánh giá forecasting trên keyword discover được.** Bạn chọn chúng *vì* chúng đang tăng — đó là chọn mẫu theo kết quả. Chỉ báo cáo trên seed set, tập được chọn trước khi quan sát kết quả.

---

## Ba mâu thuẫn trong report nên sửa trước khi nộp

**1. Mục 3.3.3 tick sai.** Đang tick `Computer Vision ✓` và `Software Engineering ✓`, để trống `Machine Learning ☐` và `Data Analytics ☐`. Nhưng cả 16 feature nghiên cứu đều là forecasting và analytics, còn trong 47 use case **không có feature computer vision nào**. Phản biện sẽ hỏi "CV nằm ở đâu?".

**2. LSTM không khả thi trong thời gian còn lại.** Report ghi PyTorch LSTM 2 lớp hidden=128 dropout=0.2 cho dữ liệu ≥90 ngày. Bạn chỉ có đúng 90 điểm daily — không đủ để train một mạng 2 lớp mà không overfit. Ghi lại là **quyết định có chủ đích do ràng buộc dữ liệu**, kèm số liệu chứng minh, mạnh hơn là im lặng bỏ qua.

**3. Dataset synthetic là lỗ hổng lớn nhất.** Report ghi *"Synthetic listing and order data... used for training and evaluating forecasting models"*. Tự sinh dữ liệu rồi tự đánh giá trên đó thì MAE ≤10% là chắc chắn đạt và không chứng minh gì. Sửa: thu hẹp phạm vi synthetic xuống chỉ **hành vi mua của buyer**, còn sản phẩm/tag/giá/nhu cầu đều là dữ liệu thật đã thu qua API.

---

## Tóm tắt

| | Số feature |
|---|---|
| Hoàn thành | **0** |
| Đủ dữ liệu, dựng mô hình được ngay | 3 (30, 37, 38) |
| Có một nửa dữ liệu | 3 (35, 39, 40) |
| Chờ Etsy | 4 (32, 33, 34, 36) |
| Chờ dữ liệu nội bộ/mô phỏng | 6 (26–29, 31, 41) |
| Ngoài phạm vi tầng dữ liệu | 31 |

**6/16 feature AI đã có nền dữ liệu thật.** Đó là kết quả của một ngày làm việc và nó không tệ — nhưng đừng nhầm nền dữ liệu với feature đã xong.

Việc tiếp theo có đòn bẩy cao nhất là **STL cho feature 38**: dữ liệu đã đủ, biên độ mùa vụ đã đo được 43–44×, không tốn thêm request nào, và ra biểu đồ demo được ngay cho thầy hướng dẫn.
