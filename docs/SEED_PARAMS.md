# Cấu Hình & Tham Số Seed Dữ Liệu Hành Vi VietCraft

Tài liệu chi tiết toàn bộ các tham số phân bố, nguồn tham chiếu, tỷ lệ đo lường và cấu hình được sử dụng trong chuỗi tác vụ Seed Dữ Liệu Hành Vi Người Dùng (Task 1 đến Task 10).

---

## 1. Phân Bố Thời Gian & Mùa Vụ (Tasks 1 & 5)

### A. Phân Bố Thứ Trong Tuần & Giờ Trong Ngày (Task 1)
- **Nguồn**: Tập dữ liệu thương mại điện tử Brazil Olist (`olist_orders_dataset.csv`).
- **Thứ trong tuần**: Chuẩn hóa quanh mức trung bình 1.0 (nhân 7).
- **Giờ trong ngày**: Tập trung cao điểm vào các khung giờ:
  - Trưa: 10h - 14h (~25%)
  - Tối: 19h - 22h (~35%)
  - Khung giờ thấp điểm: 1h - 6h (<5%)

### B. Hệ Số Mùa Vụ Theo Chủ Đề (Task 5)
- **Nguồn**: Google Trends Việt Nam 5 năm (2021 - 2026) được lưu trữ tại MongoDB `data-collection.trend_interest`.
- **21 Chủ đề chính**: `tet`, `valentine`, `womens_day_8_3`, `reunification_30_4`, `mid_autumn`, `vietnamese_womens_day_20_10`, `teachers_day_20_11`, `black_friday`, `christmas`, `couple`, `family`, `travel`, `gift`, `decor`, `vintage`, `streetwear`, `minimalism`, `anime`, `sports`, `music`, `evergreen`.
- **Đặc tính**: Chuẩn hóa trung bình toàn chuỗi $\overline{x} = 1.0$, thể hiện rõ các đỉnh nhọn vào các dịp lễ lớn tại Việt Nam.

---

## 2. Phân Bố Phễu Chuyển Đổi E-commerce (Task 3)

- **Nguồn**: Kết hợp dữ liệu thực tế Olist và Retailrocket (`data/seed_out/v1/dist_funnel.json`).
- **Lượt xem sang thêm giỏ (`view -> add_to_cart`)**: **6.45%** (thực tế đo được: **6.42%**).
- **Thêm giỏ sang đặt hàng (`add_to_cart -> order`)**: **32.40%** (thực tế đo được: **32.24%**).

---

## 3. Phân Bố Người Mua & Thiết Bị (Task 4)

- **Quy mô**: **6.000 buyers** (`buyers.csv`).
- **Phân khúc người mua (Segment)**:
  - `one_time` (Người mua 1 lần): **60%** (thực tế: 3.557 buyers)
  - `seasonal` (Người mua theo mùa/dịp lễ): **30%** (thực tế: 1.860 buyers)
  - `frequent` (Khách hàng thân thiết): **10%** (thực tế: 583 buyers)
- **Thiết bị truy cập (Device Type)**:
  - `mobile`: **70%** (thực tế: 4.198)
  - `desktop`: **25%** (thực tế: 1.475)
  - `tablet`: **5%** (thực tế: 327)
- **Phân bố địa lý**: 63 tỉnh thành Việt Nam phân bổ theo tỷ lệ dân số thực tế (`provinces.csv`), tập trung lớn nhất tại Hà Nội (~9.5%) và TP. Hồ Chí Minh (~10.5%).

---

## 4. Tham Số Sinh Lượt Xem & Thêm Giỏ (Task 6)

- **Quy mô đầu ra**: **1.271.298 dòng sự kiện** (`events.csv`).
  - Lượt xem (`view`): **1.194.583 dòng** (chuẩn dải 1.0 - 1.3 triệu).
  - Thêm giỏ (`add_to_cart`): **76.715 dòng**.
- **Mức nền lượt xem mỗi ngày theo Tier sản phẩm**:
  - `hot` (500 SP): **6.45 lượt/ngày**
  - `medium` (1.500 SP): **1.02 lượt/ngày**
  - `tail` (3.000 SP): **0.17 lượt/ngày**
- **Hệ số tuổi sản phẩm (Độ mới ra mắt)**:
  - Dưới 7 ngày: $\times 1.8$
  - Từ 7 đến 14 ngày: $\times 1.4$
  - Từ 14 đến 28 ngày: $\times 1.1$
  - Trên 28 ngày: $\times 1.0$
- **Ràng buộc nhân quả**: $100\%$ sự kiện diễn ra sau ngày tạo Listing và sau ngày Buyer đăng ký tài khoản; `occurred_at_cart` trễ hơn `occurred_at_view` từ 1 - 30 phút.

---

## 5. Tham Số Đơn Hàng & Vận Chuyển (Task 7)

- **Quy mô**: **24.736 đơn hàng** (`orders.csv`) và **34.710 mặt hàng** (`order_items.csv`).
- **Phương thức thanh toán**:
  - `cod` (Tiền mặt khi nhận hàng): **45%** (thực tế: 45.53%)
  - `vnpay`: **25%** (thực tế: 24.73%)
  - `momo`: **20%** (thực tế: 19.83%)
  - `bank_transfer`: **10%** (thực tế: 9.91%)
- **Trạng thái vòng đời đơn hàng**:
  - `delivered` (Giao thành công): **~93%** (thực tế: 92.97%)
  - `cancelled` (Huỷ đơn): **~5%** (thực tế: 5.17%)
  - `returned` (Trả hàng/hoàn tiền): **~2%** (thực tế: 1.87%)
- **Số sản phẩm khác nhau trong 1 đơn**:
  - 1 sản phẩm: **70%**
  - 2 sản phẩm: **20%**
  - 3 sản phẩm: **10%**
- **Số lượng mua của mỗi sản phẩm**:
  - 1 cái: **85%**
  - 2 cái: **10%**
  - 3 cái: **5%**
- **Phí vận chuyển**: Ngẫu nhiên từ **15.000 đ** đến **45.000 đ**.
- **Thời gian giao hàng**: Giao trong vòng **2 - 7 ngày** kể từ ngày đặt đối với đơn `delivered`/`returned`.

---

## 6. Tham Số Đánh Giá Sản Phẩm (Task 8)

- **Quy mô**: **6.882 đánh giá** (`reviews.csv`).
- **Tỷ lệ được đánh giá**: **30%** trên tổng số đơn hàng đã giao thành công (`delivered`).
- **Tỷ lệ đính kèm hình ảnh**: **20%** (thực tế: 20.3%).
- **Phân bố điểm sao** (Nguồn Olist `olist_order_reviews_dataset.csv`):
  - 5 sao: **57.8%** (thực tế: 57.6%)
  - 4 sao: **19.3%** (thực tế: 20.2%)
  - 3 sao: **8.2%** (thực tế: 8.0%)
  - 2 sao: **3.2%** (thực tế: 3.1%)
  - 1 sao: **11.5%** (thực tế: 11.1%)
- **Độ trễ viết đánh giá**: Phân bố Olist cộng thêm độ lệch giờ ngẫu nhiên (1 - 24 giờ) để bảo đảm $100\%$ thời điểm đánh giá luôn nghiêm ngặt sau thời điểm nhận hàng.

---

## 7. Bảng Thống Kê Tổng Hợp Theo Ngày (Task 9)

- **Quy mô**: **796.025 dòng** (`listing_daily.csv`, nạp vào MongoDB `vietcraft-seed.listing_daily`).
- **Chiến lược bù ngày**:
  - Nhóm `hot` & `medium` (2.000 sản phẩm): Bù đủ chuỗi thời gian 365 ngày (điền 0 cho ngày trống).
  - Nhóm `tail` (3.000 sản phẩm): Chỉ lưu các ngày có hoạt động thực tế (31.213 dòng).
- **Ràng buộc phễu chặt chẽ**: $100\%$ các dòng thỏa mãn $\text{orders} \le \text{add\_to\_carts} \le \text{views}$.
- **Doanh thu**: Khớp chính xác $100\%$ từng đồng với `order_items.csv` (**7.553.463.000,00 đ**).

---

## 8. Lưu Trữ & Nộp Bài (Task 10)

- **MongoDB Atlas (`vietcraft-seed`)**:
  - `buyers`: 6.000 docs
  - `orders`: 24.736 docs
  - `order_items`: 34.710 docs
  - `reviews`: 6.882 docs
  - `listing_daily`: 796.025 docs (Compound Unique Index `[listing_id, date]`)
  - *Lưu ý*: `events` (1.2M dòng) không nạp lên MongoDB để bảo vệ dung lượng miễn phí 512MB của MongoDB Atlas.
- **Git Repository**: Nộp đầy đủ mã nguồn Tasks 1..10 tại `app/seed/behavior/`, ảnh QC tại `docs/qc/luot_xem_theo_ngay.png`, và các file mẫu 100 dòng tại `data/seed_out/samples/`.
- **Google Drive Lưu Trữ Bản Đầy Đủ**:
  - Thư mục lưu trữ: `VietCraft_Seed_Data_Full_v1/`
  - Các file đầy đủ: `buyers.csv`, `events.csv` (74.5MB), `orders.csv`, `order_items.csv`, `reviews.csv`, `listing_daily.csv` (37.7MB).
