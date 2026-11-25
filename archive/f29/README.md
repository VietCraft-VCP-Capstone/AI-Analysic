# F29 · Kết quả đo của các model đã bỏ (25/11/2026)

Thư mục này chỉ giữ **kết quả đo** (`metrics.json`, `card.md`, `meta.json`) của các model F29 đã bỏ. Model, code và test của chúng đã xoá, git vẫn giữ lịch sử. `scripts/f29/results_md.py` đọc các số này để viết mục C, C2, B3 và "Kết quả âm" trong `notes/f29/RESULTS.md`.

| Model | Lý do bỏ |
|---|---|
| `c1_quality/v1` | Đã bị v2 thay |
| `c1_quality/v2` | Chỉ chạy ngầm: trong 30 ảnh bị cờ chỉ đúng 10 (cần ít nhất 60%) |
| `b3_mismatch/v1` | Chỉ chạy ngầm: không thắng baseline; việc này B1 đã làm |
| `listing_intel/v1.6` | Bộ máy chấm thứ hai, train ngày 21/10. Không thắng baseline đơn giản; 2 trong 3 trục đã quay về công thức. F29 chỉ giữ Health 5.0 |
