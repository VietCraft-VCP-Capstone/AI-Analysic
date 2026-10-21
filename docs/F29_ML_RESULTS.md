# F29: thí nghiệm ML cho sức khoẻ sản phẩm (Olist)

Sinh tự động bởi `python -m scripts.f29_ml.run`. Không sửa tay.

## Cách làm

1. **Câu hỏi:** sản phẩm có ra ít nhất 1 đơn trong 90 ngày tới không. Đây là định nghĩa "khoẻ" đo được bằng kết quả bán thật, thay cho checklist.
2. **Dữ liệu:** Olist, sàn TMĐT thật của Brazil, khoảng 100 nghìn đơn từ 2017 đến 2018. Một sản phẩm của một shop được tính là một listing.
3. **Làm sạch:** bỏ đơn huỷ hoặc không giao được, bỏ giai đoạn quá thưa (trước 2017 và sau 08/2018), mỗi đơn chỉ giữ một đánh giá (bản trả lời sau cùng), dịch danh mục sang tiếng Anh. 610 sản phẩm thiếu thông tin nội dung được giữ lại dưới dạng giá trị trống.
4. **Chống nhìn trước tương lai:** tại mỗi mốc T, mọi feature chỉ dùng dữ liệu trước T: đơn đặt trước T, đánh giá có thời điểm khách trả lời trước T và thuộc đơn trước T, ngày giao trước T. Nhãn chỉ dùng đơn trong [T, T+90 ngày). Chỉ lấy listing có đơn trong 180 ngày trước T.
5. **Chia tập theo thời gian:** train, validation và test có cửa sổ nhãn không chồng lên nhau. Model triển khai được chọn theo AUC validation trong các model chạy được trên VietCraft, học trên train + validation, báo cáo trên test. File model triển khai chính là model được chấm trên test.
6. **Benchmark:** ngẫu nhiên, luật health-1.0 hiện tại (2 trục đo được trên Olist là nội dung và đánh giá, chiếm 45% trọng số của luật), luật "bán nhiều 90 ngày qua" và luật "đơn gần nhất".
7. **Khoảng tin cậy:** bootstrap 200 lần, lấy mẫu theo shop (một shop có nhiều listing nên không coi từng dòng là độc lập). So sánh model với baseline mạnh nhất bằng bootstrap ghép cặp trên cùng mẫu.

## Làm sạch dữ liệu

- `order_items_raw`: 112,650
- `orders_dropped_status`: 1,234
- `orders_dropped_date`: 297
- `sales_rows`: 111,752
- `products_missing_content`: 610
- `reviews_raw`: 99,224
- `reviews_kept`: 98,673

## Chia tập

| Tập | Mốc T | Số listing | Tỉ lệ ra đơn |
|---|---|---|---|
| train | 2017-07-01, 2017-08-01, 2017-09-01, 2017-10-01 | 33,198 | 25.9% |
| validation | 2018-01-01 | 12,905 | 24.9% |
| test | 2018-05-01 | 16,130 | 20.5% |

## Kết quả trên validation

| Phương pháp | ROC-AUC (95% CI) | PR-AUC | AUC trong cùng danh mục | Tỉ lệ ra đơn ở top 20% |
|---|---|---|---|---|
| Ngẫu nhiên | 0.503 (0.492–0.515) | 0.252 | 0.501 | 25.0% |
| health-1.0 (luật hiện tại) | 0.512 (0.485–0.542) | 0.264 | 0.528 | 28.7% |
| Bán nhiều 90 ngày qua | 0.706 (0.692–0.719) | 0.458 | 0.707 | 52.1% |
| Đơn gần nhất | 0.700 (0.686–0.714) | 0.439 | 0.699 | 47.7% |
| Logistic regression | 0.747 (0.732–0.761) | 0.536 | 0.747 | 54.7% |
| Gradient boosting | 0.741 (0.726–0.756) | 0.531 | 0.739 | 54.7% |
| Gradient boosting, bỏ lịch sử bán | 0.700 (0.683–0.718) | 0.466 | 0.692 | 48.3% |
| Gradient boosting, bản chạy trên VietCraft | 0.751 (0.737–0.763) | 0.540 | 0.747 | 54.8% |
| Gradient boosting, chỉ lịch sử bán | 0.734 (0.720–0.746) | 0.540 | 0.734 | 55.3% |

Model triển khai, chọn theo validation trong các bản chạy được trên VietCraft: **Gradient boosting, bản chạy trên VietCraft**.

## Kết quả trên test (chưa từng dùng khi học hay khi chọn model)

| Phương pháp | ROC-AUC (95% CI) | PR-AUC | AUC trong cùng danh mục | Tỉ lệ ra đơn ở top 20% |
|---|---|---|---|---|
| Ngẫu nhiên | 0.507 (0.496–0.516) | 0.210 | 0.509 | 21.0% |
| health-1.0 (luật hiện tại) | 0.517 (0.495–0.545) | 0.224 | 0.536 | 24.3% |
| Bán nhiều 90 ngày qua | 0.730 (0.720–0.741) | 0.426 | 0.726 | 47.3% |
| Đơn gần nhất | 0.734 (0.722–0.744) | 0.418 | 0.731 | 44.6% |
| Logistic regression | 0.766 (0.752–0.778) | 0.500 | 0.765 | 49.1% |
| Gradient boosting | 0.756 (0.742–0.768) | 0.509 | 0.754 | 48.6% |
| Gradient boosting, bỏ lịch sử bán | 0.693 (0.670–0.709) | 0.400 | 0.691 | 40.8% |
| Gradient boosting, bản chạy trên VietCraft | 0.761 (0.747–0.774) | 0.508 | 0.755 | 48.8% |
| Gradient boosting, chỉ lịch sử bán | 0.759 (0.747–0.769) | 0.520 | 0.756 | 49.9% |

Tỉ lệ ra đơn trung bình trên test là 20.5%. Cột "top 20%" cho biết trong 20% listing được chấm cao nhất có bao nhiêu phần trăm thực sự ra đơn.

**So với baseline mạnh nhất (Đơn gần nhất):** AUC chênh +0.027, khoảng tin cậy 95% bootstrap ghép cặp theo shop [+0.016, +0.040].

## Yếu tố quan trọng của model triển khai (Gradient boosting, bản chạy trên VietCraft)

Bảng đầu: bỏ hẳn một nhóm yếu tố, học lại rồi đo AUC trên test. Số gần 0 nghĩa là nhóm đó không thêm thông tin khi đã có các nhóm còn lại. Scorer chỉ đưa lời khuyên cho nhóm có mức giảm từ 0,005 trở lên.

| Nhóm yếu tố | AUC giảm khi bỏ cả nhóm và học lại |
|---|---|
| Lịch sử bán | +0.0671 |
| Kích thước, cân nặng | +0.0028 |
| Đánh giá | +0.0017 |
| Nội dung (ảnh, mô tả, tên) | +0.0011 |
| Shop (uy tín, giao hàng) | +0.0004 |
| Giá và phí ship | -0.0021 |

| Yếu tố | AUC giảm khi xáo trộn riêng yếu tố đó |
|---|---|
| Số ngày từ đơn gần nhất | 0.0969 |
| Số món shop bán (180 ngày) | 0.0276 |
| Số sản phẩm đang bán của shop | 0.0206 |
| Số đánh giá | 0.0155 |
| Số món bán 90 ngày qua | 0.0132 |
| Cân nặng | 0.0063 |
| Thể tích | 0.0026 |
| Độ dài tên | 0.0024 |
| Số món bán 180 ngày qua | 0.0022 |
| Điểm sao (đã co về trung bình) | 0.0012 |

## Giới hạn

- Olist là sàn Brazil, không phải VietCraft. Bản triển khai bỏ giá tuyệt đối (khác tiền tệ), danh mục (khác cây danh mục) và tỉ lệ giao trễ (VietCraft chưa lưu ngày hẹn giao).
- Olist chỉ có sản phẩm đã từng bán được, nên model không chấm sản phẩm chưa có đơn nào trong 180 ngày.
- Nội dung sản phẩm (số ảnh, độ dài mô tả) là ảnh chụp tại thời điểm xuất dữ liệu, không theo từng mốc T.
- Trạng thái đơn là trạng thái lúc xuất dữ liệu: vài trăm đơn đặt trước T nhưng huỷ sau T bị loại khỏi feature.
- Một listing xuất hiện ở nhiều mốc train. Test chỉ có một mốc, nên kết quả phản ánh một giai đoạn.
- Xác suất dự đoán chưa hiệu chỉnh theo tỉ lệ nền (tỉ lệ nền giảm từ train sang test), nên sản phẩm chỉ hiển thị thứ hạng so với nhóm, không hiển thị xác suất.
- Chưa có kiểm chứng trên dữ liệu bán thật của VietCraft. Dữ liệu sàn hiện tại là lưu lượng mô phỏng.
