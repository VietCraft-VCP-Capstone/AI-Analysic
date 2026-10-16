# DATA_LICENSES.md — Nguồn dữ liệu ngoài của F29 (Olist)

Ngày: 2026-10-15

## Olist Brazilian E-Commerce Public Dataset

- **Nguồn:** Kaggle, bộ dữ liệu `olistbr/brazilian-ecommerce` — https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce
- **Chủ sở hữu:** Olist (Olist Store), công bố công khai qua Kaggle.
- **Giấy phép:** CC BY-NC-SA 4.0 (Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International) — xem https://creativecommons.org/licenses/by-nc-sa/4.0/
  - Được phép: sao chép, chia sẻ, biến đổi dữ liệu.
  - Điều kiện: ghi công nguồn (Attribution); **không dùng cho mục đích thương mại** (NonCommercial); nếu phân phối lại bản biến đổi phải giữ cùng giấy phép (ShareAlike).
- **Mục đích sử dụng tại VietCraft:** kiểm chứng ngoại bộ (F29b, F29c) cho công thức chấm điểm sức khoẻ listing (health-1.0) — mục đích nghiên cứu/kiểm thử nội bộ, phi thương mại, không bán lại dữ liệu.

## Vị trí lưu trữ và quy tắc dùng

- Lưu **offline only** tại `preparied-olist-data/` (gốc repo `vietcraft/`, ngoài `vc-ai/AI-Analysic/`), **không đẩy lên Atlas** hay bất kỳ hệ thống dùng chung nào của nhóm (§6.1 kế hoạch).
- 4 file đã xác minh tại chỗ (15/10/2026):

| File | Số dòng |
|---|---|
| `olist_products_dataset.csv` | 32.951 |
| `olist_order_items_dataset.csv` | 112.650 |
| `olist_orders_dataset.csv` | 99.441 |
| `olist_order_reviews_dataset.csv` | 99.224 (pandas đọc đúng; `wc -l` ra số khác vì bình luận chứa ký tự xuống dòng) |

- Các script trong `vc-ai/AI-Analysic/scripts/` (`f29_bayes_m_selection.py`, `f29b_learn_weights.py`, `f29c_report.py`) đọc trực tiếp từ đường dẫn tuyệt đối `preparied-olist-data/`, không copy dữ liệu gốc vào trong `vc-ai/`.
- Kết quả tính toán (CSV/JSON/Markdown/PNG trong `docs/`, `scripts/`) **không chứa dữ liệu thô** của Olist — chỉ số tổng hợp (Pearson, bảng điểm theo `product_id` ẩn danh của Olist, không phải thông tin cá nhân).

## Ghi chú giấy phép khi công bố kết quả

Khi trình bày `health_pearson` (nguồn `olist_real`) trước hội đồng/báo cáo, cần ghi công nguồn: *"Dữ liệu kiểm chứng: Olist Brazilian E-Commerce Public Dataset (Kaggle, CC BY-NC-SA 4.0)"* — đã thực hiện trong `docs/RESULTS.json → metrics.health_pearson.scope` và `docs/F29C_RESULTS.md`.
