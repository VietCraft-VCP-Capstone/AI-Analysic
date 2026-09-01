# Báo cáo Thẩm định Tính Toàn vẹn Dữ liệu Tích hợp Toàn sàn (Integration QC)

> **Thời điểm thẩm định**: 01/09/2026 23:22:12  
> **Người thực hiện**: Đạt (Task 27 / Sprint 1)  
> **Phạm vi thẩm định**: Liên kết dữ liệu chéo giữa 5 thành viên (Nhi, Hưng, Hạt, Hiếu, Đạt).

---

## 1. Kết quả 6 Phép Kiểm Toàn vẹn (Cross-Member Integrity Checks)

| # | Phép kiểm tra | Chi tiết kết quả thực tế | Trạng thái |
|:---:|---|---|:---:|
| 1 | Mọi sản phẩm thuộc shop có thật (Shops <-> Listings) | 0 sản phẩm mồ côi / 5000 listings | **ĐẠT** |
| 2 | Mọi biến thể thuộc sản phẩm có thật (Listings <-> Variants) | 0 biến thể mồ côi / 39920 variants | **ĐẠT** |
| 3 | Mọi đơn hàng gắn với người mua và sản phẩm có thật (Orders) | Chưa có file orders.csv / order_items.csv | `PENDING (CHỜ HIẾU TASK 58)` |
| 4 | Mọi đánh giá gắn với đơn đã nhận thành công (Reviews) | Chưa có file reviews.csv | `PENDING (CHỜ HIẾU TASK 59)` |
| 5 | Mọi dòng thống kê ngày có sản phẩm tương ứng (Listing Daily) | Chưa có file listing_daily.csv | `PENDING (CHỜ HIẾU TASK 60)` |
| 6 | Mọi tag trên sản phẩm có trong danh sách chuẩn (Tags <-> Listings) | 0 tag lạ không nằm trong tags.csv của Nhi | **ĐẠT** |

---

## 2. Đánh giá Tiến độ & Hành động tiếp theo

- **Dữ liệu Master Data (Nhi, Hưng, Hạt)**: Đã vượt qua 100% các phép kiểm tra số **1, 2 và 6** (0 sản phẩm mồ côi, 0 biến thể mồ côi, 100% tags chuẩn hoá).
- **Dữ liệu Hành vi (Hiếu)**: Các phép kiểm tra số **3, 4, 5** đang ở trạng thái **PENDING** chờ Hiếu hoàn tất nộp các file CSV tương ứng (`orders.csv`, `reviews.csv`, `listing_daily.csv`).
- **Thử nghiệm trích xuất chuỗi thời gian cho Model AI**: Đã kiểm tra thành công với hàm `get_trend_series` và `get_listing_daily` trong `app/core/loader.py`.
