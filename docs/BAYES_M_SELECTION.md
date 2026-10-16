# Chọn hằng số co ngót Bayes `m` — F29 (bước 1, Track A)

Ngày: 2026-10-15 · Theo D2 (`PLAN_SELLER_AI_LISTING_HEALTH.md` §16) và §6.1-6.2.

## Công thức đang co ngót

```
rating_shrunk(product) = (Σ★ + m·C) / (n + m)
```

- `n`, `Σ★`: số review và tổng điểm sao của **sản phẩm đó**.
- `C`: trung bình điểm sao **toàn sàn** trên review thật — cùng prior với engine (`app/core/f29/calculator.py`) và `HEALTH_SPEC.md`.
- `m`: hằng số co ngót — càng lớn thì càng kéo điểm sản phẩm ít review về gần `C`.

## Dữ liệu và cách gán review cho sản phẩm

Nguồn: `preparied-olist-data/` (4 file, xem §6.1 kế hoạch).

1. Chỉ dùng **đơn một sản phẩm** (`order_items` nhóm theo `order_id`, giữ đơn có đúng 1 `product_id` khác nhau) để review gán đúng 1 sản phẩm, không mơ hồ khi đơn có nhiều mặt hàng.
   - Tổng đơn trong `order_items`: 98.666. Đơn một sản phẩm: **95.430 (96,7%)** — khớp số đã kiểm ở §6.1 của kế hoạch.
2. Nối `order_reviews` ↔ đơn một sản phẩm qua `order_id` ↔ `product_id`.
   - Review gán được: **95.227**, cho **30.801 sản phẩm** — khớp đúng số đã kiểm 15/10.
3. `C` = trung bình toàn bộ review gán được = **4,130**. Điểm co ngót tính bằng đúng hàm `bayes_shrunk_rating` trong `app/core/f29/scoring.py`, không viết lại công thức.

> Bản trước dùng `C` theo danh mục, lệch với engine. Prior danh mục chung cho cả hai nửa làm Pearson bị thổi phồng (chênh lệch giữa các danh mục góp vào tương quan), nên bảng dưới đây đã chạy lại với prior toàn sàn.

## Phương pháp đo độ ổn định

Với mỗi sản phẩm có đủ review để chia đôi, sắp review theo `review_creation_date`, cắt làm 2 nửa bằng nhau (nửa đầu/nửa sau theo thời gian). Tính điểm co ngót Bayes **riêng cho từng nửa** (dùng cùng một `C` toàn sàn cho cả hai nửa). Hai nửa của cùng một sản phẩm đáng lẽ phải cho điểm gần nhau nếu `m` co ngót tốt nhiễu của n nhỏ; đo bằng:

- **Pearson** giữa điểm nửa 1 và điểm nửa 2 trên toàn bộ sản phẩm đủ điều kiện.
- **MAE / RMSE** giữa hai nửa — càng nhỏ càng ổn định.
- **Phương sai điểm nửa 1** (`var_half1`) — đo kèm để thấy cái giá phải trả: `m` càng lớn, điểm càng kéo về `C` chung, càng ổn định nhưng càng **kém phân biệt** giữa các sản phẩm.

Chạy 2 ngưỡng lọc để kiểm tra kết quả không phụ thuộc ngưỡng chọn tuỳ tiện:
- **Ngưỡng chính:** sản phẩm có ≥4 review (mỗi nửa ≥2) — 5.163 sản phẩm.
- **Ngưỡng phụ (kiểm độ nhạy):** sản phẩm có ≥2 review (mỗi nửa ≥1) — 12.518 sản phẩm.

## Kết quả

### Ngưỡng chính (≥4 review/sản phẩm, n=5.163)

| m | Pearson (nửa1 vs nửa2) | MAE | RMSE | Phương sai nửa 1 |
|---|---|---|---|---|
| 10 | 0,260 | 0,191 | 0,253 | 0,0377 |
| 20 | 0,284 | 0,115 | 0,155 | 0,0145 |
| **50** | **0,310** | **0,054** | **0,075** | 0,0035 |

### Ngưỡng phụ, kiểm độ nhạy (≥2 review/sản phẩm, n=12.518)

| m | Pearson | MAE | RMSE | Phương sai nửa 1 |
|---|---|---|---|---|
| 10 | 0,202 | 0,148 | 0,208 | 0,0234 |
| 20 | 0,230 | 0,084 | 0,121 | 0,0081 |
| **50** | **0,263** | **0,037** | **0,056** | 0,0018 |

Kết quả nhất quán ở cả hai ngưỡng: `m` càng lớn, hai nửa thời gian càng khớp nhau (Pearson tăng, MAE/RMSE giảm đều đặn), không có nghịch đảo ở m nào trong 3 giá trị thử. MAE/RMSE giảm theo `m` gần như do cấu trúc công thức (cả hai nửa bị kéo về cùng `C`); Pearson tăng là bằng chứng thật hơn — thứ hạng sản phẩm giữa hai nửa giữ được tốt hơn khi nhiễu n nhỏ bị nén. Pearson tuyệt đối thấp (0,26–0,31) cho thấy điểm sao Olist của một sản phẩm ít review vốn rất nhiễu.

## Đánh đổi cần ghi nhận

`m` lớn ổn định hơn nhưng làm giảm phương sai điểm giữa các sản phẩm (0,038 → 0,0035 khi m: 10→50, ngưỡng chính), tức là bớt phân biệt sản phẩm tốt/kém qua trục đánh giá khi số review còn ít — đúng bản chất của co ngót Bayes (ưu tiên chống nhiễu cho sản phẩm ít dữ liệu hơn là giữ độ phân giải). Vì trục đánh giá chỉ chiếm 0,25 trọng số tổng và 4 trục còn lại vẫn phân biệt được, đánh đổi này chấp nhận được.

## Kết luận (D2)

**Giữ `m = 50`** — sau khi chạy lại với prior toàn sàn và hàm của engine, vẫn ổn định nhất trong 3 giá trị thử (10/20/50) theo cả Pearson lẫn MAE/RMSE, nhất quán ở 2 ngưỡng lọc khác nhau.

Đã cập nhật hằng số:
- `app/core/build_marts.py`: `M_BAYES = 50` (trước đó để tạm `10`, ghi chú "Sẽ thay bằng giá trị chọn từ F29").
- `app/core/f29/constants.py`: `K_BAYESIAN_SHRINKAGE = 50` (trước đó để tạm `10`).

## Script

`vc-ai/AI-Analysic/scripts/f29_bayes_m_selection.py` — import `bayes_shrunk_rating` từ engine, chạy lại được, in đúng bảng trên.
