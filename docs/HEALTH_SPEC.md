# HEALTH_SPEC — Điểm sức khoẻ listing (`health-1.0`)

Ngày chốt: 2026-10-15 · Theo `PLAN_SELLER_AI_LISTING_HEALTH.md` §3.5, §4 (v7) · SRS 4.2.2

**Một công thức duy nhất** = engine live `app/core/f29/` (`scoring.py`, `calculator.py`,
`conversion.py`, `todos.py`, hằng số ở `constants.py`). Kiểm định Olist (F29b/F29c) và file
ví dụ gọi thẳng các hàm thuần trong `scoring.py`, không chép lại công thức. Mart seed
`build_marts.py` là bản cũ, không phải `health-1.0` (xem `SPEC_CHANGES.md`).

Luồng live: scheduler (`app/core/f29_scheduler.py`, quét thay đổi mỗi 60 giây + quét toàn bộ
lúc 0h UTC) chấm listing thật (bộ lọc `LOC_SP_THAT`/`LOC_DON_THAT` của `_live.py`) → upsert
`vietcraft.listing_health_scores` theo `{product_id, date}` kèm `model_version`,
`inputs_hash` → BE đọc → FE trang Insights.

## 1. Năm trục, trọng số và gộp điểm

| Trục | Trọng số |
|---|---|
| `conversion` chuyển đổi | 0,30 |
| `rating` đánh giá | 0,25 |
| `content` đầy đủ nội dung | 0,20 |
| `inventory` tồn kho | 0,15 |
| `freshness` độ mới | 0,10 |

```
score = Σ(điểm_trục × w_trục) / Σ(w_trục)      chỉ lấy các trục KHÁC None, làm tròn 0,1
```
Trục thiếu dữ liệu (n/a) bị bỏ và **chia lại trọng số** — không bao giờ cho 0 điểm vì thiếu
dữ liệu. Không trục nào có → `score = None`. Tên trục bị bỏ nằm trong `axes_missing`.
Mỗi trục được làm tròn 0,1 trước khi gộp (`scoring.total_score`).

## 2. Công thức từng trục

**Đánh giá (.25)** — `bayes_shrunk_rating`, `rating_axis_score`
```
shrunk = (Σ★ + m·C) / (n + m)        m = 50 (docs/BAYES_M_SELECTION.md)
rating = clip((shrunk − 1) / 4 × 100, 0, 100)      1★ = 0 · 3★ = 50 · 5★ = 100
```
`n`, `Σ★`: review của listing trên đơn thật. `C` = trung bình gộp mọi review thật toàn sàn
(chưa có review nào → 3,0). `n = 0` → n/a.

**Đầy đủ nội dung (.20)** — `content_component_scores`, `content_axis_score`
```
thành_phần(x, mốc) = 0 nếu x ≤ 0 · 100 nếu x ≥ mốc · x/mốc×100 còn lại
images      = thành_phần(số ảnh, 5)
description = thành_phần(độ dài mô tả đã strip, 150 ký tự)
tags        = thành_phần(số tag đã duyệt, 3)   # có tag_ids: bỏ tag status=pending; sản phẩm cũ không có tag_ids: đếm theo tên
content     = trung bình cộng các thành phần CÓ dữ liệu
```
Thành phần mà nguồn dữ liệu không có cột (vd. Olist không có tag) truyền `None` và bị bỏ
khỏi trung bình — không tính 0. Live luôn có đủ 3 thành phần.
Cảnh báo phụ (không đổi điểm, `type: "info"`): không ảnh/mô tả/tag, tiêu đề ngoài 20–120 ký
tự, mô tả trùng tiêu đề, ảnh trùng nhau.

**Tồn kho (.15)** — `inventory_score`
Chỉ `product_type == READY_TO_SHIP`: `% biến thể đang bán (is_active) có stock_quantity > 0`.
Loại khác hoặc không có biến thể đang bán → n/a.

**Độ mới (.10)** — `freshness_score`
```
tuổi = số ngày từ content_changed_at
100 nếu tuổi ≤ 90 · 0 nếu tuổi ≥ 365 · 100×(1 − (tuổi−90)/275) ở giữa
```
`content_changed_at` chỉ nhảy về "bây giờ" khi `content_hash` (MD5 tiêu đề + mô tả + tag +
ảnh) đổi so với lần chấm trước; lần chấm đầu dùng `updated_at`. Sửa giá/tồn kho không làm
listing "mới" lại. Không có mốc nào → 100.

**Chuyển đổi (.30)** — `conversion.py`
```
cửa sổ 30 ngày · lượt xem = product_events view · mua = đơn thật, không huỷ, chứa sản phẩm
chỉ chấm khi lượt xem ≥ 100                       (dưới → n/a, reason not_enough_views)
CR = mua / xem
mặt bằng = CR gộp (Σmua/Σxem) của listing cùng danh mục có ≥100 lượt xem, cần ≥5 listing
          → không đủ thì lấy mặt bằng toàn sàn (cũng cần ≥5) → không đủ: n/a (not_enough_peers)
          → mặt bằng = 0: n/a (no_orders_in_baseline)
conversion = min(CR / mặt_bằng, 2,0) × 50          (bằng mặt bằng = 50, gấp đôi trở lên = 100)
```
`conversion_detail` lưu lượt xem, số mua, mặt bằng và phạm vi để giao diện giải thích.

## 3. Ba mức (BR-182)

`≥ 80` good · `50–79` needs_improvement · `< 50` poor.

## 4. Việc cần sửa (todo) — `todos.build_todos`

- Chỉ cho thứ seller sửa trực tiếp: ảnh, mô tả, tag, tồn kho. Chuyển đổi không sinh todo.
- **Mốc nội dung** = `max(trung vị listing cùng danh mục, mức sàn)`; mức sàn 5 ảnh / 150 ký tự
  / 3 tag. Danh mục (phần tử đầu `category_ids`) có < 8 listing → dùng trung vị toàn sàn.
- **Mốc tồn kho** = 80% biến thể còn hàng.
- `impact` = điểm tổng **chấm lại thật** khi kéo đúng chỉ số đó lên mốc, trừ điểm hiện tại
  (cùng hàm `content_axis_score`/`total_score`). `impact ≤ 0` thì không sinh todo.
- Sắp theo `impact / công_sức`, công sức: ảnh 1, tag 1, mô tả 2, tồn kho 3.

## 5. Cảnh báo ưu tiên 0 — `todos.build_warnings`

Đứng đầu danh sách, `impact = 0`, không đổi điểm: 0 ảnh · giá bán < giá vốn ở ít nhất một
biến thể · bị từ chối kiểm duyệt (kèm lý do).

Cảnh báo bán hàng (`todos.build_sales_warnings`, cũng không đổi điểm): listing đăng từ 14 ngày mà dưới
100 lượt xem/30 ngày (`field: title`); trục chuyển đổi ≤ 40 (tỉ lệ mua thấp hơn mặt bằng ≥ 20%, BR-179), gợi ý
theo bước rơi rụng — ít thêm giỏ (`variants.retail_price`) hay thêm giỏ mà ít mua (`shipping`).

## 6. Version

`health-1.0`: trọng số trên (gán tay, F29b không thay — `docs/F29B_RESULTS.md`), m = 50,
thang đánh giá 1★ = 0. Đổi version khi đổi trọng số, mốc, hoặc công thức trục; `model_version`
lưu kèm từng bản ghi điểm.

## 7. Kiểm định và ví dụ

- Olist (`scripts/f29_olist_axes.py`, F29b/F29c): chỉ đo được đánh giá + nội dung (ảnh, mô tả).
  Kết quả: `docs/F29B_RESULTS.md`, `docs/F29C_RESULTS.md`, `docs/RESULTS.json`.
- `docs/health_score_example.csv` (`scripts/build_health_score_example.py`): 20 listing seed
  chấm bằng hàm engine, kèm input thô để cộng tay. Ví dụ `lst_000030`: 1 review 4★,
  C = 4,08 → shrunk = (4 + 50×4,08)/51 = 4,078 → rating 77,0; content 100, tồn kho 100,
  độ mới 100, chuyển đổi n/a → (77×0,25 + 100×0,20 + 100×0,15 + 100×0,10)/0,70 = **91,8**.
