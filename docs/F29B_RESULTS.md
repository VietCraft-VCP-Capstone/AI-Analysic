# F29b — Học trọng số rating/content trên Olist

Ngày: 2026-10-15 · Theo `PLAN_SELLER_AI_LISTING_HEALTH.md` §4.2 · Script: `scripts/f29b_learn_weights.py`

## Nhắc lại phạm vi (bản đăng ký KHÔNG đòi học trọng số — D7/§2)

Đây là quyết định nội bộ (E25), không phải yêu cầu đăng ký. Cái được học **chỉ** là tỉ lệ chia giữa 2 trục **đánh giá** (.25) và **đầy đủ nội dung** (.20) — hai trục này chia nhau phần trọng số cố định **0,45**. Ba trục còn lại (chuyển đổi .30, tồn kho .15, độ mới .10) **giữ gán tay** vì:
- chuyển đổi: đưa vào làm biến học là rò rỉ dữ liệu (doanh số sau T lại là chính biến mục tiêu);
- tồn kho, độ mới: Olist không có dữ liệu tương ứng.

## Dữ liệu

- Nguồn: `preparied-olist-data/` (4 file), chỉ dùng đơn `order_status == "delivered"`.
- Mốc T = 2018-01-01, cửa sổ sau T cắt ở 2018-08-31 (≈7,95 tháng).
- Sản phẩm bán trước T: **16.951**. Sau T (đến cutoff): 20.174. Bán **cả hai phía**: **4.909** — khớp đúng số đã kiểm ở §6.1 kế hoạch.
- Trong 4.909 sản phẩm đó, **4.427** có đủ cả 2 trục (content không n/a **và** có ≥1 review trước T) — đây là tập dùng để học tỉ lệ, vì sản phẩm thiếu 1 trục không mang thông tin về tỉ lệ chia giữa 2 trục.

## Cách tính 2 trục trên Olist

Gọi thẳng hàm engine health-1.0 (`app/core/f29/scoring.py`, qua `scripts/f29_olist_axes.py`) — số kiểm định là đúng công thức seller thấy.

| Trục | Công thức (engine) | Nguồn cột |
|---|---|---|
| Đầy đủ nội dung | trung bình của `ảnh/5` và `mô tả/150 ký tự` (mỗi phần trần 100). Thành phần tag n/a vì Olist không có tag — bị bỏ khỏi trung bình, không chấm 0 | `product_photos_qty`, `product_description_lenght`; thiếu cả hai → n/a |
| Đánh giá | Bayes `(Σ★+m·C)/(n+m)`, m=50, C = trung bình gộp mọi review trước T (toàn sàn, như engine), rồi `(shrunk−1)/4×100` (1★=0, 5★=100) | Review của **đơn một sản phẩm**, `review_creation_date < T`. n=0 → n/a |

## Biến mục tiêu

`y = Σ(price của order_items, đơn delivered, order_purchase_timestamp ∈ (T, cutoff]) / 7,95 tháng`

Chuẩn hoá theo **độ dài cố định của cửa sổ sau T** (không phải số tháng bán riêng của từng sản phẩm) — chọn cách này vì câu chữ kế hoạch "số tháng sản phẩm đang bán" có thể hiểu nhiều cách; chia theo số tháng bán thực tế của từng sản phẩm (có thể chỉ 1 ngày) sẽ gây bất ổn định (chia cho số rất nhỏ). Ghi rõ lựa chọn này vào `SPEC_CHANGES.md`.

Không dùng tỷ lệ chuyển đổi (CR) làm biến — đúng lưu ý chống rò rỉ ở §4.2.

## Cách học

NNLS (`scipy.optimize.nnls`) trên `X=[rating, content]` (cả hai đã quy 0-100), hệ số không âm `b_rating, b_content`. Quy về tỉ lệ rồi nhân 0,45: `w = 0,45 × b/(Σb)`, kẹp mỗi trục trong **[0,05 ; 0,40]** (ràng buộc ≥0,05 mỗi trục, tổng =0,45).

Lặp **200 lần chia ngẫu nhiên 70/30 (train/test)** trên tập 4.427 sản phẩm để đo ổn định và so Pearson trên tập test, cộng thêm paired t-test và Wilcoxon signed-rank trên 200 cặp Pearson (học được vs gán tay).

## Kết quả (chạy lại 2026-10-15 với công thức hợp nhất)

| | Bộ GÁN TAY (0,25/0,20) | Bộ HỌC ĐƯỢC (NNLS) |
|---|---|---|
| Tỉ lệ rating/content | 0,25 / 0,20 | trung bình **0,284 / 0,166** qua 200 lần chia (std tỉ lệ rating 0,081; min 0,063 – max 0,400, có chạm biên kẹp) |
| Pearson trên tập **test** (trung bình 200 lần) | **0,0230** (std 0,0282) | 0,0191 (std 0,0249) |
| Số lần thắng / 200 lần chia | — | **77/200**; chênh lệch trung bình từng cặp = **−0,0039** |
| Paired t-test (học − tay) | | t = −6,285, p = 2,0e-9 (nghiêng về gán tay) |
| Wilcoxon signed-rank | | W = 5734, p = 1,4e-7 (nghiêng về gán tay) |
| Fit trên toàn bộ 4.427 (chỉ tham khảo) | Pearson 0,0223 | w=(0,2769; 0,1731), Pearson 0,0221 |

So với lần chạy trước (công thức nội dung cũ ảnh 60%/mô tả 40% mốc 400, C theo danh mục): Pearson test gán tay giảm 0,0323 → 0,0230, bộ học được 0,0297 → 0,0191. Số thấp hơn được báo đúng như đo, không chỉnh công thức để kéo lên. Pearson ở cả hai bộ đều rất thấp (~0,02): Olist đa ngành hàng, chỉ 2/5 trục, doanh số từng SKU rất nhiễu (`LIMITATIONS.md`).

## Kết luận theo 3 điều kiện (§4.2)

1. **Pearson test cao hơn gán tay:** **KHÔNG đạt** (0,0191 < 0,0230; t-test và Wilcoxon đều có ý nghĩa, nghiêng về gán tay).
2. **Ổn định:** yếu — tỉ lệ dao động 0,063–0,400, chạm biên kẹp.
3. **Dấu và độ lớn hợp lý:** đạt — cả hai hệ số dương.

**→ Giữ bộ gán tay 0,25 / 0,20.** `docs/HEALTH_SPEC.md` giữ `health-1.0`.

## Tái lập

```
.venv/bin/python scripts/f29b_learn_weights.py
```
Script tất định (đã sort tập hợp sản phẩm trước khi lặp — tránh phụ thuộc `PYTHONHASHSEED` ngẫu nhiên của Python).
