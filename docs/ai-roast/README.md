# Roast các tính năng AI của VietCraft: mục lục

Ngày 2026-10-21. Mỗi file roast một tính năng theo cùng một khung:
- **Mục 0:** bản đăng ký nói gì.
- **Mục 1:** roast code hiện tại.
- **Mục 2:** mổ xẻ lỗi.
- **Mục 3:** tính năng nên là AI gì.
- **Mục 4:** đường ra, gồm dữ liệu, sanity, model, học từ dữ liệu thật, bảo mật, benchmark.
- **Mục 5:** lộ trình.
- **Mục 6:** câu hội đồng sẽ hỏi.

Nguồn đối chiếu là bản đăng ký SRS Report 3 (`archive/context/report3.pdf`), mục 3.8–3.10, đánh số `3.8.1 = F26` … `3.10.5 = F41`. Lệch bản đăng ký được xếp mức Chết người hoặc Nặng. Listing Health (F29, mục 3.8.4) đã làm lại thành Listing Intelligence, xem `docs/LISTING_INTEL_TECH_REPORT.md`.

## Bảng tổng

| File | Tính năng | SRS | Thực chất hiện tại | Lỗi nặng nhất | Đường ra |
|---|---|---|---|---|---|
| [F26](F26_shop_overview.md) | Tổng quan shop | 3.8.1 | Cộng và nhóm số liệu | Đơn tính theo ngày UTC, lượt xem theo ngày VN; không có view thì hiện "CR −100%"; phần phản hồi khách để cứng `[]` | Giữ là thống kê; thêm phân rã nguyên nhân (view × CR × giá trị đơn) và kiểm định thay đổi |
| [F27](F27_listing_timeseries.md) | Chuỗi thời gian listing | 3.8.2 | Độ dốc OLS, ngưỡng ±5%/ngày | Hiểu sai BR-178 (±5% mỗi ngày thay vì trên cả cửa sổ); FE không hiện badge xu hướng | Giữ là thống kê; GLM Poisson kèm khoảng tin cậy |
| [F28](F28_conversion.md) | Phân tích chuyển đổi | 3.8.3 | Tỉ lệ phễu 90 ngày | UC-58 đòi theo ngày/tuần/tháng; trên seed là vòng tròn; ở mức 30 view, 78% listing trung bình vẫn bị gắn mẹo | Beta-Binomial empirical Bayes, benchmark trên Retailrocket |
| [F30](F30_anomaly_alerts.md) | Cảnh báo bất thường | 3.8.5 | STL + robust z, ngưỡng \|z\| > 7 | Ngưỡng 7.0 thay cho 2.0 của BR-183, lý do trích nguồn không tồn tại; cấy cú tụt 50% chỉ bắt được 2%; không có WebSocket/email | z từ mô hình NB để giữ \|z\| > 2; benchmark bằng bất thường cấy có nhãn |
| [F31](F31_category_revenue.md) | Doanh thu theo loại | 3.8.6 | Nhóm số liệu + heatmap | BR-185 sai múi giờ (seed dùng giờ Brazil, live dùng giờ server, cả hai ghi `Asia/Ho_Chi_Minh`); 20 đơn ngẫu nhiên vẫn ra "giờ cao điểm" 69% số lần | Giữ là thống kê; chỉ báo giờ cao điểm khi qua kiểm định |
| [F32](F32_competitors.md) | Ai đang bán chạy | 3.9.1 | Sắp xếp theo số đếm | Live có 4 đơn nên thứ hạng ra theo ObjectId; lệch BR-187/188/189 | Gamma-Poisson EB, kèm khoảng thứ hạng |
| [F33](F33_shop_comparison.md) | Tôi mạnh, yếu ở đâu | 3.9.2 | Min–max | Lệch BR-192 (min–max trên cả phân khúc thay vì 6 shop); lộ doanh thu đối thủ | Giữ là thống kê; "shop giống bạn" là tuỳ chọn |
| [F34](F34_tag_gap.md) | Từ khoá nên thêm | 3.9.3 | Lift + hằng số tự đặt | Số "% lượt xem" là bịa; danh mục ≤ 20 sản phẩm thì luôn trống mà FE vẫn khen; BR-195–197 cần lượng tìm kiếm và CTR | Lift làm trơn OOF + đọc `search_logs` |
| [F35](F35_pricing.md) | Giá tôi đắt hay rẻ | 3.9.4 | P25–P75 của top 20 | SRS đòi dải giá có conversion cao nhất; lệch BR-198/199/200; bộ ấm chén Bát Tràng bị gán thành cốc in | Model khoảng giá `price_band` (HGB quantile + CQR) dùng chung với F42 |
| [F36](F36_competitor_tracking.md) | Đối thủ đang theo dõi | 3.9.5 | Lọc listing mới trong 7 ngày | Không có job hằng ngày, không gửi Notification; câu "cảnh báo cũ vẫn giữ" sai | Điểm liên quan để xếp cảnh báo, đo precision@5 |
| [F37](F37_revenue_forecast.md) | Dự báo doanh thu | 3.10.1 | SARIMAX đấu seasonal naive | Sai BR-205 ở cả hai nhánh; câu "MASE 1,12" bịa từ một EWMA chạy trên dữ liệu mô phỏng | Rolling-origin, HGB quantile + conformal, ARIMA cho chuỗi < 90 ngày, LSTM train offline rồi chạy bằng ONNX |
| [F38](F38_seasonal.md) | Mùa vụ và lịch ra hàng | 3.10.2 | 6 chiến dịch gõ tay + STL | Fallback bịa phần trăm rồi gắn nhãn "Gemini 3.5" (model không tồn tại); Gemini nằm ngoài SRS; đang trong cửa sổ Tết mà báo còn 354 ngày | Dự báo cầu theo từ khoá có backtest; LLM có schema, grounding, bộ red-team |
| [F39](F39_niches.md) | Ngách tiềm năng | 3.10.3 | Cầu trừ cung theo phân vị | Sai công thức SRS (tăng trưởng × chuyển đổi / mật độ); cung đếm tag seed ngẫu nhiên; ngách đang giảm 70% vẫn lọt top | Công thức SRS, kiểm chứng bằng precision@k |
| [F40](F40_trend_radar.md) | Radar ngách mới nổi | 3.10.4 | 4 tuần so 4 tuần | Không phải so tuần với tuần; momentum không phải gia tốc 3 tuần; top 10 thực ra là 5 chuỗi in hai lần | Phát hiện bùng nổ sớm, đo lead time và precision |
| [F41](F41_recommendations.md) | Việc nên làm / Investment Recommendations | 3.10.5 | Gap seed + health < 50 | Không đọc dự báo F37 như SRS yêu cầu; `personalised: True` để cứng khiến FE giấu cảnh báo | Xếp hành động bằng F29 ML + impact, đo NDCG@5; A/B khi có seller thật |
| [F42](F42_smart_suggestion.md) | Gợi ý thông minh | Ngoài SRS (gần 3.4.2) | Bảng giá cứng + markup | `sample_count` lấy từ `hash()`; mô tả ghi "da thật" cho input "da PU giả da"; "Nến thơm" bị xếp thành áo thun; MdAPE 174.5% | Nắn về F35/F34 hoặc ghi phụ lục; dùng `price_band` (kNN tiêu đề đạt MdAPE 39.1% trên validation) |
| [KYC](KYC_cccd_ocr.md) | OCR CCCD, thật/giả | Ngoài SRS (UC 40/67/68) | EasyOCR + ngưỡng cứng | Endpoint không xác thực; IDOR ở `/scan-cccd` và `/apply`; FE luôn hiện tích xanh; OTP bỏ qua được; ảnh KYC có thể bị đóng vào image Docker | Ghi phụ lục; OCR chỉ hỗ trợ (tự điền, gắn cờ cho admin), không tự quyết duyệt |
| [MOD](MOD_content_moderation.md) | Kiểm duyệt nội dung | 3.11.2 | Danh sách từ cấm cứng | SRS đòi hàng chờ duyệt mà sản phẩm được đăng ngay ở trạng thái APPROVED; review, chat, tìm kiếm không qua bộ lọc; chặn nhầm 7.2% tiêu đề Tiki ("đi" khớp với "đĩ") | Chuyển bộ lọc của AI sang BE, rồi TF-IDF + LR để gắn cờ và xếp hàng chờ duyệt |

## Các vấn đề chung
1. **Không tính năng nào trong số này có model được train hoặc có benchmark.** Chỉ Listing Intelligence và Health ML (Olist) có.
2. **Có số bịa đưa tới người dùng:** F42 `sample_count`, F34 "% lượt xem", F38 phần trăm kèm nhãn "Gemini 3.5", F37 "MASE 1,12", F30 tỉ lệ báo nhầm.
3. **Lệch SRS lặp lại:**
   - thiếu job batch (BR-187, BR-199, BR-210);
   - thiếu kênh thông báo (WebSocket, email, Notification);
   - công thức khác đăng ký (F35, F39, F40, F33).
4. **Dữ liệu thật quá ít.** Sàn có 4 đơn nên mọi phép xếp hạng và phễu đều suy biến. Trên seed thì kết quả là vòng tròn, vì tham số do chính nhóm nhập.
5. **Bảo mật:**
   - endpoint OCR không xác thực;
   - IDOR ở KYC;
   - `BE/query_users_temp.js` đã commit kèm mật khẩu Atlas, cần đổi mật khẩu ngay.

## Thứ tự làm đề xuất
1. **1–2 ngày:**
   - Gỡ số bịa ở F42, F38, F37, F34, F30.
   - Vá bảo mật: đổi mật khẩu Atlas, xác thực OCR, kiểm quyền file KYC.
   - Sửa các lệch SRS rẻ: F33 BR-192, F35 BR-198/200, F31 múi giờ.
2. **1–2 tuần:** dựng 3 khối dùng chung, mỗi khối có benchmark trên dữ liệu thật công khai:
   - `price_band` cho F35 và F42;
   - empirical Bayes cho F28 và F32;
   - rolling-origin backtest cho F37, F30, F39 và F40.
3. **Khi sàn có dữ liệu thật:** train lại bằng đúng các pipeline trên, chạy A/B cho F41.
