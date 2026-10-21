# SPEC_CHANGES.md — Lệch so với SRS/bản đăng ký và giữa các nơi hiện thực

Ngày: 2026-10-15 · Đối chiếu `docs/HEALTH_SPEC.md` (health-1.0) với SRS/bản đăng ký. Nguồn sự thật duy nhất của công thức là engine live `app/core/f29/`.

## 1. Lệch so với bản đăng ký (đã được kế hoạch chấp nhận trước)

### 1.1 Biến đo lường trên Olist: doanh số thay cho tỷ lệ mua
- **Đăng ký (SRS 4.2.2, chỉ tiêu):** `health_pearson` đo giữa điểm và **tỷ lệ mua**.
- **Olist không có lượt xem** (không phải sàn thương mại điện tử VietCraft), nên không tính được tỷ lệ mua. Dùng **doanh số sau T, chuẩn hoá theo tháng** thay thế (§6.3 kế hoạch).
- Đối chiếu đúng định nghĩa đã đăng ký thực hiện riêng trên **seed** (§6.4) — nhưng seed offline hiện chỉ có mẫu 100 dòng cho orders/views, không đủ tính tỷ lệ mua trên 500 listing (xem `docs/F29C_RESULTS.md` — `health_pearson_seed` ghi "chưa đo được, cần Mongo access").

### 1.2 Trục n/a thì bỏ khỏi phép tính, không chấm 0 điểm
- **SRS ngầm định/diễn giải thông thường:** thiếu dữ liệu một trục có thể hiểu là chấm 0.
- **Thực hiện:** trục n/a (thiếu dữ liệu) bị loại khỏi phép tính và **chia lại trọng số** cho các trục còn lại (`docs/HEALTH_SPEC.md` §1). Đây là quyết định đã chốt trong kế hoạch (§4.1: "Trục n/a hoặc thiếu dữ liệu thì bỏ khỏi phép tính và chia lại trọng số, không cho 0 điểm"), không phải lỗi — ghi lại ở đây theo đúng yêu cầu "ghi lệch so với SRS ('chấm 0') vào SPEC_CHANGES.md".

### 1.3 BR-181 "ngay khi sửa" hiểu là ≤1 phút
- AI quét thay đổi mỗi phút (không phải tức thời). Duyệt tag không ghi vào `products` nên không được job quét-mỗi-phút bắt kịp ngay; job đêm (24h) chạy bù. (D4, §5 kế hoạch.)

## 2. Hợp nhất công thức health-1.0 (2026-10-15)

Trước đây có 3 bản công thức lệch nhau (engine live; `HEALTH_SPEC.md` + script kiểm định Olist;
mart seed). `health_pearson` cũ (0,0347) đo một công thức seller không hề thấy. Nay:

- **Thang đánh giá thống nhất:** `(shrunk − 1)/4 × 100`, kẹp 0..100 (1★ = 0, 5★ = 100).
  Engine cũ dùng `shrunk/5 × 100` (1★ vẫn được 20 điểm) — đã sửa trong `scoring.rating_axis_score`.
- **Trục nội dung gồm tag:** trung bình 3 thành phần ảnh (mốc 5) / mô tả (mốc 150 ký tự, D3) /
  tag (mốc 3). Bỏ công thức cũ "ảnh 60% + mô tả 40% theo mốc 400 ký tự".
- **C của Bayes = trung bình toàn sàn** ở mọi nơi (đúng câu chữ §4.1); script Olist trước đây dùng
  trung bình theo danh mục, nay dùng trung bình gộp mọi review trước T.
- **Kiểm định Olist chỉ dùng ảnh + mô tả:** Olist không có tag, nên thành phần tag truyền `None`
  và bị bỏ khỏi trung bình (tham số tường minh của `content_component_scores`), không chấm 0.
  `product_name_lenght` không còn dùng để xác định n/a (engine không chấm tên).
- Script kiểm định và file ví dụ gọi thẳng hàm trong `app/core/f29/scoring.py`
  (`scripts/f29_olist_axes.py`), không chép công thức. Kết quả mới: `docs/F29C_RESULTS.md`.
- **Mart seed `build_marts.py` → `listing_health` là bản cũ, KHÔNG phải health-1.0** (vẫn
  ảnh 60%/mô tả 40% mốc 400, C theo danh mục, tồn kho mọi loại sản phẩm). File do nhóm khác
  quản lý nên chưa sửa; chỉ dùng cho shop demo seed, không hiển thị điểm cho seller thật.

### 2.1 Trọng số F29: NNLS trên Olist + luật gán tay, không qua khảo sát chuyên gia
- Cổng ra mục 11 (`exit_gate_s3.py`) vẫn ghi "khảo sát chuyên gia ... trọng số F29". Quyết định
  **D7 đã bỏ hội đồng chuyên gia** cho F29: trọng số `health-1.0` (.30/.25/.20/.15/.10) là gán tay
  theo SRS 4.2.2; F29b học tỉ lệ rating/content bằng NNLS trên Olist và chỉ thay khi thắng đủ
  3 điều kiện §4.2 — chưa thắng nên giữ gán tay (`docs/F29B_RESULTS.md`). Đây là lệch có chủ đích
  so với mục 11 của cổng ra.

### 2.2 Phần của §4.1 chưa cài
- "Có biến thể size/màu" chưa nằm trong trục nội dung.

## 3. Lựa chọn phương pháp có thể hiểu nhiều cách (F29b/F29c), đã chốt và ghi lại

- **"Số tháng sản phẩm đang bán"** (kế hoạch §4.2, §6.3) — hiểu là **độ dài cố định của cửa sổ sau T** (T=2018-01-01 → cutoff=2018-08-31, ≈7,95 tháng), áp dụng như nhau cho mọi sản phẩm — KHÔNG dùng số tháng bán thực tế riêng của từng sản phẩm (có thể rất ngắn, gây bất ổn khi chia). Xem `docs/F29B_RESULTS.md`.
- **"500 sản phẩm bán chạy nhất trước T"** — xếp theo số **dòng** `order_items` trước T (không phải số đơn hàng duy nhất) — cách đếm này khớp đúng con số đã kiểm ở §6.1 kế hoạch ("≥13 đơn mỗi sản phẩm"; đếm theo đơn duy nhất ra tối thiểu 12, đếm theo dòng ra đúng 13).
- **Chỉ dùng đơn `order_status == "delivered"`** cho toàn bộ F29b/F29c (gán review, đếm sản phẩm bán trước/sau T) — khớp đúng số đã xác nhận trong kế hoạch (16.951 sản phẩm bán trước T; 4.909 bán cả 2 phía). Không lọc theo `delivered` cho ra số hơi khác (17.451 / 4.995).

## 4. Trạng thái trục chuyển đổi

- Trục chuyển đổi **đã cài** (`app/core/f29/conversion.py`): listing có ≥100 lượt xem trong 30 ngày
  được chấm `min(CR/mặt bằng, 2,0) × 50`; dưới ngưỡng hoặc thiếu bạn so sánh thì n/a kèm
  `conversion_detail.reason`. Khi live còn ít lượt xem, phần lớn listing vẫn n/a ở trục này và
  điểm được chia lại trên 4 trục còn lại.
- Trục nội dung chỉ đếm **tag đã duyệt** (tag `pending` chưa hiện với người mua, form sửa sản phẩm
  cũng không hiện), khớp plan §4.1. Sản phẩm cũ chưa có `tag_ids` vẫn đếm theo tên tag. Việc cần làm
  ghi rõ số tag đang chờ duyệt.
- Bỏ cảnh báo "cân nặng/kích thước còn mặc định" (plan §4.3): phí vận chuyển của BE không dùng cân nặng
  sản phẩm, và form sản phẩm không có ô cân nặng, nên cảnh báo vừa sai vừa không sửa được.

## 5. F30 — Cảnh báo bất thường (2026-10-21)

1. BR-183: thêm điều kiện đủ (|Δ| ≥ 30%, ≥ 100.000đ, kỳ vọng tối thiểu, trần 3/shop/tuần); z là z hiệu chỉnh từ phân phối dự báo, không phải z cửa sổ 7 ngày.
2. Cửa sổ baseline 28 ngày (không phải 7) để có đủ 4 quan sát mỗi thứ.
3. Dò cấp shop + liệt kê top listing, không dò từng listing.
4. Pub/Sub thay bằng BE cron gọi AI nội bộ có `X-Gateway-Secret`.
5. Thêm luật `zero_run` một phía cho ngừng bán.
6. Bỏ ngưỡng 7.0 và câu "7,38% / 0,6%" (không có nguồn đo).
