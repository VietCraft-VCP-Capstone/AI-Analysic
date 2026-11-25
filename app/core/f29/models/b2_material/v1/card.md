# B2 · Đoán chất liệu từ tên và mô tả (v1)

- Việc làm: đoán 1 trong 14 lớp chất liệu từ tên và mô tả (đã bỏ dòng Chất liệu).
- Dữ liệu: tiki23, 5353 tin có nhãn; chia theo người bán 70/15/15, seed 0.
- Số mẫu: train 3752, val 797, test 804.
- Mô hình: TF-IDF ký tự (2–5) + TF-IDF từ (1–2) → LogisticRegression C=8 → hiệu chỉnh isotonic.
- Kết quả test (macro-F1 / top-3):
  - Bài A (còn chữ chất liệu): mô hình 0.6112 / 0.9266; cách hiện tại 0.2889; text_vi 0.4167; lớp phổ biến nhất (da_that) 0.0337
  - Bài B (đã xoá mọi từ chất liệu): mô hình 0.5155 / 0.898; cách hiện tại 0.0; text_vi 0.0; lớp phổ biến nhất 0.0337
  - Bản bỏ dấu (cùng mô hình): bài A 0.2664, bài B 0.1894
- Cổng (bài A): mô hình − baseline_text_vi có CI95 [0.0492; 0.2854] → đạt theo khoảng tin cậy. Cổng PROTOCOL còn thiếu baseline regex đã sửa (chưa dựng), nên cổng đầy đủ chưa kiểm được.
- Giới hạn: jean gộp vào khac. Dữ liệu là Tiki Fashion và tiki23, không phải sản phẩm VietCraft.
- Giới hạn: mô hình chỉ học trên chữ có dấu; bản bỏ dấu là đo độ bền, không phải huấn luyện.
