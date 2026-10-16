# LIMITATIONS.md — Giới hạn của bằng chứng F29 (health-1.0)

Ngày: 2026-10-15 · Theo `PLAN_SELLER_AI_LISTING_HEALTH.md` §6.5, §7, §15

## 1. Olist là sàn Brazil, đa ngành hàng — không phải VietCraft

- `olistbr/brazilian-ecommerce` là dữ liệu một sàn thương mại điện tử Brazil tổng hợp (quần áo, điện tử, nội thất, mỹ phẩm, đồ chơi...), **không phải** sàn đồ thủ công/quà tặng như VietCraft.
- Hành vi mua hàng, độ nhạy với ảnh/mô tả, và cơ cấu đánh giá có thể khác nhau đáng kể giữa 2 thị trường (ngôn ngữ, văn hoá, logistics, mùa vụ).
- Olist chỉ dùng làm **bằng chứng tạm thời tốt nhất hiện có** (dữ liệu thật, quy mô lớn) trong lúc VietCraft chưa đủ dữ liệu live — không phải bằng chứng cuối cùng (§7 kế hoạch: thứ tự ưu tiên Olist > seed > live, sẽ đảo ngược khi live đủ lớn).

## 2. Đo theo doanh số, không theo tỷ lệ mua (như bản đăng ký yêu cầu)

- Olist không có dữ liệu lượt xem/lượt vào trang sản phẩm, nên không tính được tỷ lệ mua (views→orders) như SRS 4.2.2 yêu cầu.
- Dùng **doanh số sau T, chuẩn hoá theo tháng** làm biến thay thế. Doanh số bị ảnh hưởng bởi nhiều yếu tố ngoài health-1.0 đo được (giá, phí ship, vị trí hiển thị tìm kiếm, mùa vụ, độ nổi tiếng người bán) — tương quan thấp đo được ở Olist (Pearson = 0,0305 trên top 500, xem `docs/F29C_RESULTS.md`) phản ánh một phần giới hạn này, không chỉ giới hạn của công thức.

## 3. Olist chỉ cho đo được 2/5 trục

- Chuyển đổi (trọng số nặng nhất, 0,30), tồn kho, độ mới đều **n/a** trên Olist. Health score đo trên Olist chỉ còn đánh giá (0,25) + nội dung (0,20), chia lại thành ~56%/44%; trong trục nội dung chỉ có ảnh + mô tả (Olist không có tag) — không đại diện đầy đủ sức mạnh dự báo của công thức 5 trục đầy đủ khi live có event thật.
- Vì vậy con số `health_pearson` đo trên Olist **không nên được hiểu là ước lượng cuối cùng** của hiệu năng công thức health-1.0 đầy đủ trên VietCraft — nó chỉ kiểm chứng được phần "đánh giá + nội dung" dự báo doanh số tốt tới đâu trên một sàn khác ngành hàng.

## 4. Review Olist thưa với từng sản phẩm

- Chỉ gán được review cho đơn **một sản phẩm** (96,7% tổng đơn) để tránh mơ hồ — bỏ qua review của 3,3% đơn nhiều sản phẩm.
- Phần lớn sản phẩm Olist có rất ít ảnh (trung vị 1 ảnh) — với mức sàn 5 ảnh của VietCraft (D3), hầu hết sản phẩm Olist có thành phần ảnh thấp (1 ảnh = 20 điểm), trong khi 93% sản phẩm có mô tả ≥150 ký tự — trục nội dung trên Olist chủ yếu phân biệt theo số ảnh, dù đây là hành vi bình thường của sàn đó (không phải lỗi dữ liệu).

## 5. Đối chiếu seed chưa đầy đủ

- `vc-ai/vc-data/samples/*.csv` (orders, order_items, reviews, listing_daily) mỗi file chỉ có **100 dòng mẫu schema**, không phải toàn bộ dữ liệu seed thật nằm trong Mongo Atlas. Không đủ để tính tỷ lệ mua trên 500 listing seed như §6.4 yêu cầu.
- `health_pearson_seed` hiện ghi `null` với lý do "chưa đo được, cần Mongo access" (xem `docs/RESULTS.json`, `docs/F29C_RESULTS.md`).

## 6. Sẽ đo lại trên live ở S2

- Khi live đạt S2 (≥500 listing đủ lượt xem, ≥8 tuần snapshot — §8 kế hoạch), F29b/F29c sẽ chạy lại **trên dữ liệu live thật của VietCraft**, với cùng luật 3 điều kiện (§4.2), và **thay thế** Olist làm bằng chứng chính. Olist khi đó chỉ còn vai trò tham khảo lịch sử.
- Cho tới khi đó, mọi kết luận rút ra từ Olist (bao gồm quyết định giữ bộ trọng số gán tay ở F29b) nên được coi là **tạm thời**, có thể đảo ngược khi có dữ liệu VietCraft thật.

## 7. Mart seed còn công thức cũ

- Engine live `app/core/f29/` là công thức duy nhất của health-1.0, dùng chung cho live, kiểm định Olist và file ví dụ. `build_marts.py` (mart seed, chỉ cho shop demo) vẫn giữ công thức cũ — xem `docs/SPEC_CHANGES.md` mục 2. Điểm `listing_health` của mart seed không so sánh trực tiếp được với điểm live.
