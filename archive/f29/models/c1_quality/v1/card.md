# C1 · Chất lượng ảnh v1

- Dữ liệu: KonIQ-10k. Chia ngẫu nhiên seed 0: train 7058, val 1000, test 2015. KonIQ trên OSF không kèm file chia tập chính thức.
- Nhãn: (MOS - 1) / 4, trong khoảng 0..1. Điểm hiển thị = 100 × dự đoán.
- Đặc trưng: hand (SigLIP2 của 5 vùng cắt 224 px, đặc trưng thủ công cột [0, 1, 2, 3, 4, 5, 6, 7, 8, 11]). MLP (256,), alpha 0.01. Chọn cấu hình theo trung vị SRCC val của 3 seed.
- Đã loại cột 9 (cạnh ngắn) và cột 10 (tỉ lệ khung), đếm từ 0, vì KonIQ toàn ảnh 1024x768 nên hai cột này là hằng số khi train.
- Test, median [khoảng percentile 2.5-97.5 qua 10 seed]: SRCC 0.751 [0.742, 0.757]; PLCC 0.759 [0.753, 0.763]; KRCC 0.552 [0.544, 0.557].
- Ablation, SRCC median: vùng cắt gốc 0.755, ảnh thu nhỏ 224 0.778.
- PLCC khớp logistic: logistic: 10. linear_fallback nghĩa là khớp thất bại, dùng PLCC tuyến tính.
- Ngưỡng cảnh báo: 50.0 trên thang 0..100, chọn trên val để F1 bắt ảnh có MOS < 3 lớn nhất.
- Chế độ: shadow (chưa qua cổng: SRCC 0,751 < 0,85; trên VietCraft AUC 0,529 < cờ cũ 0,610).
- model.joblib là seed 7, có SRCC val cao nhất trong 10 seed.
- Model chỉ đáng tin với ảnh gần 1024x768 cho tới khi có dữ liệu nhiều cỡ ảnh.
- Chưa kiểm định trên ảnh sản phẩm thật của sàn.
- Trọng số học từ KonIQ-10k, chỉ dùng cho demo học thuật. Bản thương mại phải train lại trên dữ liệu sạch giấy phép.
