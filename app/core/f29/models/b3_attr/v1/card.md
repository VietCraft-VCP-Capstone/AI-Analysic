# B3 bản 2 · AI kiểm thuộc tính ảnh so với mô tả (v1)

- Việc làm: ảnh không khớp thuộc tính người bán ghi (ví dụ tên ghi 'trơn' nhưng ảnh là 'in hình').
- Dữ liệu: 8997 ảnh có vector (tiki26 + TikiFashion); tiki23 không có vector ảnh. Train/val/test 6320/1373/1304, chia theo người bán và cụm ảnh/chữ gần trùng, seed 0.
- Nhóm train: pattern, color, sleeve, material_vis. Bỏ: set (748 mẫu train có nhãn, 1 lớp đủ 10 mẫu).
- Nhãn yếu từ tiêu đề. Một nhóm chỉ có nhãn khi đúng một giá trị được nhắc.
- Ba phương pháp: probe = LogisticRegression (C theo macro-F1 val), zero-shot = SigLIP với prompt VI+EN, trộn = trung bình probe và zero-shot. Xác suất gốc, không isotonic.
- Phương pháp cố định: trộn (chọn trên val ở fix round 1, không chọn lại). Bảng val dưới đây tính lại theo cặp hiện tại, chỉ để tham khảo:
  - probe: PR-AUC val 3% 0.4029, 5% 0.385, trung bình 0.394
  - zero-shot: PR-AUC val 3% 0.3877, 5% 0.3566, trung bình 0.3721
  - trộn: PR-AUC val 3% 0.5272, 5% 0.4716, trung bình 0.4994
- Cặp tráo: cùng loại (B1), khác đúng một thuộc tính đang xét, hai giá trị trái ngược, không xung đột ở nhóm khác. Tối đa 3 cặp mỗi neo.
- Lệch trên test (seed 1):
  - lệch 3% (20 lệch / 546 sạch): PR-AUC trộn 0.3766; ứng viên khác: probe 0.3095, zero-shot 0.3529; cosine 0.2403, B3 v1 0.0611; chênh lệch với cosine CI95 [-0.1241, 0.3774]
  - lệch 5% (35 lệch / 546 sạch): PR-AUC trộn 0.5112; ứng viên khác: probe 0.4285, zero-shot 0.4894; cosine 0.4706, B3 v1 0.1321; chênh lệch với cosine CI95 [-0.1855, 0.2776]
- Theo từng thuộc tính (điểm chỉ dùng nhóm đó; không bật riêng ở runtime):
  - pattern (n test=70): macro-F1 probe 0.5675 vs zero-shot 0.6329, McNemar p=1.0
      3%: 2 lệch, trộn 0.1944 vs cosine 0.6111; 5%: 4 lệch, trộn 0.5597 vs cosine 0.7159
  - color (n test=132): macro-F1 probe 0.6193 vs zero-shot 0.6414, McNemar p=0.8506
      3%: 4 lệch, trộn 0.217 vs cosine 0.6576; 5%: 7 lệch, trộn 0.3146 vs cosine 0.5991
  - sleeve (n test=54): macro-F1 probe 0.8585 vs zero-shot 0.8942, McNemar p=1.0
      3%: 2 lệch, trộn 1.0 vs cosine 0.75; 5%: 3 lệch, trộn 1.0 vs cosine 0.8667
  - material_vis (n test=353): macro-F1 probe 0.6901 vs zero-shot 0.6877, McNemar p=1.0
      3%: 11 lệch, trộn 0.4001 vs cosine 0.4343; 5%: 19 lệch, trộn 0.5649 vs cosine 0.4915
- Ngưỡng conformal α=0.02 trên val sạch của trộn → 0.5287 (n=455). Báo nhầm trên test sạch: 2.4% (vượt α).
- Chế độ: shadow. Quy tắc: live khi phương pháp đã chọn > baseline tốt nhất (1−cos, B3 v1) ở cả 3% và 5%, CI95 bootstrap theo group_id của chênh lệch > 0.
- Chỉ cảnh báo, không chặn. Điểm = max over nhóm (P(giá trị đối lập) − P(giá trị người bán ghi)).
- Giới hạn: tiki23 chưa có vector ảnh; nhóm set bị bỏ vì chỉ có nhãn một chiều; số mẫu lệch test còn ít.
- Trên VietCraft (124 sản phẩm, 9 lệch theo nhãn AI, nhãn chưa được người dùng kiểm): cờ đúng 2, báo nhầm 3, bỏ sót 7; precision 0,40 (2/5), recall 0,22 (2/9). Cosine precision 0/6, B3 v1 0/7. Cổng live (precision ≥ 0,6): không đạt. Cổng Tiki: không đạt. Chế độ: shadow.
