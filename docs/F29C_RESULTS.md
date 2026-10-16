# F29c — Đo `health_pearson` trên Olist thật (chỉ tiêu đăng ký)

Ngày: 2026-10-15 · Theo `PLAN_SELLER_AI_LISTING_HEALTH.md` §6.3, §6.4 · Script: `scripts/f29c_report.py`

Chỉ tiêu đăng ký (SRS 4.2.2): `health_pearson ≥ 0,65` giữa điểm và tỷ lệ mua, đo trên 500 listing. **Cổng ra chỉ cần có số thật; đạt ngưỡng không bắt buộc** (§2 bản đăng ký).

## Công thức áp dụng

Chính engine health-1.0 (`app/core/f29/scoring.py`, qua `scripts/f29_olist_axes.py`), bộ trọng số **gán tay** (giữ sau F29b). Olist chỉ có 2/5 trục: đánh giá (Bayes m=50, C toàn sàn, 1★=0…5★=100) và nội dung (ảnh/5 + mô tả/150, không có tag). Ba trục còn lại n/a nên `total_score` chia lại trọng số 0,25/0,45 và 0,20/0,45 (một trục thì 100%).

Điểm chỉ dùng dữ liệu **trước** T=2018-01-01; biến so sánh là doanh số **sau** T (cắt 2018-08-31), chuẩn hoá theo cửa sổ cố định 7,95 tháng — như F29b.

## Kết quả — 500 sản phẩm bán chạy nhất trước T

| | Trước hợp nhất (công thức cũ) | **Sau hợp nhất (health-1.0 live)** |
|---|---|---|
| Pearson (n=500) | 0,0347 (p=0,439) | **0,0305 (p=0,497)** |
| Spearman | −0,0843 (p=0,060) | **−0,0823 (p=0,066)** |
| Toàn bộ 16.909 sản phẩm có điểm — Pearson | 0,0263 (p=0,0006) | 0,0222 (p=0,0039) |
| Toàn bộ — Spearman | 0,0186 (p=0,016) | 0,0304 (p=7,7e-5) |

- Top 500 xếp theo số dòng `order_items` trước T (nhỏ nhất 13). Cả 500 có điểm (499 có rating, 493 có content).
- **Chưa đạt ngưỡng 0,65**; trên top 500 không có ý nghĩa thống kê. Pearson giảm nhẹ sau hợp nhất — báo đúng như đo, không tinh chỉnh.
- Biểu đồ: `docs/HEALTH_SCATTER_OLIST.png`. Chi tiết từng dòng: `scripts/health_score_olist_top500.csv`.

## Diễn giải

Tương quan rất thấp là dự kiến (§15, §6.1 kế hoạch): chỉ 2/5 trục đo được (thiếu chuyển đổi — trục nặng nhất), so với doanh số thay vì tỷ lệ mua (Olist không có lượt xem), và Olist là sàn đa ngành hàng Brazil. Trên Olist, trục nội dung chủ yếu phân biệt theo số ảnh (trung vị 1 ảnh, 93% mô tả đã ≥150 ký tự); trục đánh giá sau co ngót m=50 rất hẹp (top 500: 67–86 điểm). Trong nhóm bán chạy, khác biệt còn lại giải thích được rất ít phương sai doanh số.

`docs/RESULTS.json → metrics.health_pearson` ghi số mới kèm `explanation` (lý do chưa đạt và cam kết đo lại trên live ở S2) — đúng yêu cầu của `exit_gate_s3.py`.

## Đối chiếu với seed (§6.4)

**Chưa đo được, cần Mongo access.** `vc-ai/vc-data/` chỉ có:
- `master/listings.parquet` (5.000 listing) và `master/listing_variants.parquet` (39.920 biến thể) — đủ để chấm 4 trục (trừ chuyển đổi) — dùng cho `docs/health_score_example.csv`,
- nhưng `samples/orders.csv`, `samples/order_items.csv`, `samples/listing_daily.csv`, `samples/reviews.csv` mỗi file chỉ có **100 dòng mẫu** (schema sample, không phải toàn bộ dữ liệu seed) — không đủ để tính tỷ lệ mua (views→orders) trên 500 listing như §6.4 yêu cầu.

Đã ghi `metrics.health_pearson_seed = {"value": null, "reason": "chưa đo được, cần Mongo access"}` vào `RESULTS.json`, nêu rõ phần nào có offline (parquet 5.000 listing) và phần nào thiếu (lượt xem/đơn hàng đầy đủ).

## File liên quan

- `scripts/f29c_report.py` — script chạy lại được, tất định.
- `scripts/health_score_olist_top500.csv` — điểm chi tiết từng sản phẩm trong top 500 (để soát tay).
- `docs/HEALTH_SCATTER_OLIST.png` — biểu đồ phân tán.
- `docs/RESULTS.json` — `metrics.health_pearson`, `metrics.health_pearson_seed`.
