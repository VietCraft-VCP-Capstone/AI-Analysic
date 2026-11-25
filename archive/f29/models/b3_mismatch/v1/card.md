# B3 · Bộ kiểm mâu thuẫn ảnh, chữ và danh mục (v1)

- Việc làm: phát hiện tin mà ảnh, chữ hoặc danh mục không khớp nhau (ví dụ ảnh áo, mô tả quần).
- Dữ liệu: emb_tikifashion, 4962 mẫu sạch; chia theo cụm 70/15/15, seed 0; mẫu lệch test sinh với seed 1.
- Mẫu lệch: ① tráo ảnh trong cùng nhóm cha khác loại; ② tráo ảnh sang nhóm khác; ③ đổi danh mục sang loại anh em.
- Đặc trưng: js_div(p_ảnh, p_chữ), khoảng cách cây, cos(ảnh, chữ), p_ảnh[danh mục], p_chữ[danh mục].
- Xác suất B1 cho tập train lấy out-of-fold (GroupKFold 5 theo cụm); val và test dùng B1 đầy đủ.
- Mô hình: LogisticRegression (C=1) → hiệu chỉnh isotonic. Chọn C trên val.
- Ngưỡng conformal (val, mẫu sạch): cảnh báo α=0.02 → 0.9157; chặn α=0.005 → 0.9700.
- Báo nhầm thực tế trên test: cảnh báo đạt (0.0188 ≤ 0.02) (n=744); chặn không đạt (0.0108 > 0.005).
- Chặn không đạt: không chỉnh ngưỡng trên test. Cần tập sạch ≥ 2.000 mẫu để kiểm α = 0,005.
- Kết quả test theo tỉ lệ lệch:
  - lệch 1% (8 lệch / 744 sạch): PR-AUC B3 0.5987; bảng kiểm 0.0106, cosine 0.4072, B1 không train 0.1082; chênh lệch so với cosine CI95 [0.0, 0.4306]; gắn cờ 5%: precision 0.1842, recall 0.875
  - lệch 3% (23 lệch / 744 sạch): PR-AUC B3 0.6462; bảng kiểm 0.03, cosine 0.3392, B1 không train 0.2785; chênh lệch so với cosine CI95 [0.1587, 0.4713]; gắn cờ 5%: precision 0.4615, recall 0.7826
  - lệch 5% (39 lệch / 744 sạch): PR-AUC B3 0.7279; bảng kiểm 0.0498, cosine 0.3529, B1 không train 0.4353; chênh lệch so với b1_untrained CI95 [0.0927, 0.4803]; gắn cờ 5%: precision 0.7, recall 0.7179
- Chế độ: shadow. Quy tắc: live khi PR-AUC B3 > baseline tốt nhất và CI95 cụm của chênh lệch > 0 ở cả 3 tỉ lệ.
- Phạm vi: chỉ 15 loại có dữ liệu train (TRAINED) được cảnh báo hoặc chặn. Loại khác, kể cả Áo dài, Tranh ảnh, Laptop, Điện Thoại, tối đa là info.
- Giới hạn: bảng kiểm là điểm hằng, nên AUC = 0,5 theo định nghĩa.
