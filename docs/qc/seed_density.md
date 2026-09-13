# Báo Cáo Kiểm Định Mật Độ Đơn Hàng Seed Data (Density Verification)

> **Mô tả phép kiểm**: Phép kiểm mật độ đơn hàng theo tầng sản phẩm (`verify_seed.py`)  
> **Khung thời gian 12 tháng**: Từ 29/08/2025 đến 29/08/2026  
> **Tổng số đơn trong 12 tháng**: 22,835 đơn hàng  
> **Tiêu chuẩn nghiệm thu**: Trung vị (Median) tầng `hot` $\ge$ 12 đơn/năm  
> **Kết luận chung**: **ĐẠT (PASS)** (Trung vị hot = 30.0 đơn/năm)

---

## 1. Bảng Thống Kê Mật Độ Đơn Hàng Theo Tầng (In TRUNG VỊ)

| Tầng sản phẩm (Tier) | Số lượng Listing | TRUNG VỊ đơn/năm (Median) | Khoảng phân bố (IQR: Q1 - Q3) | Tỷ lệ không có đơn (0 đơn) | Ngưỡng kiểm tra | Đánh giá |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| **Tầng Hot** | 500 | **30.0 đơn/năm** | 11.0 - 49.0 | 2.0% | $\ge 12$ đơn/năm | **ĐẠT** |
| **Tầng Medium** | 1,500 | **6.0 đơn/năm** | 3.0 - 9.0 | 3.4% | — | — |
| **Tầng Tail** | 3,000 | **2.0 đơn/năm** | 1.0 - 3.0 | 13.6% | — | — |
| **Toàn bộ sàn (Overall)** | 5,000 | **3.0 đơn/năm** | 1.0 - 6.0 | 9.38% | — | — |

---

## 2. Lý Do Khoa Học: Tại Sao Bắt Buộc Dùng TRUNG VỊ Thay Vì TRUNG BÌNH?

1. **Phân bố lệch phải nghiêm trọng (Heavy Right-Skewed Distribution)**:
   - Trong thương mại điện tử thực tế, doanh số tuân theo quy luật Pareto (Power-law): một số ít sản phẩm bán chạy có thể đạt hàng trăm đơn hàng, trong khi phần lớn sản phẩm dài đuôi (tail) bán rất ít hoặc thậm chí 0 đơn.
2. **Nguy cơ sai lệch của số trung bình (Mean Fallacy)**:
   - Nếu chỉ đo lường bằng **trung bình**, vài listing bán chạy cá biệt sẽ kéo số trung bình của toàn tầng lên cao, che lấp hoàn toàn thực tế rằng đa số listing trong tầng có thể bị rỗng.
   - Ví dụ: Ở tầng `hot`, số trung bình là **32.57 đơn/năm**, cao hơn trung vị (**30.0 đơn/năm**).
3. **Ý nghĩa của tiêu chuẩn Trung vị $\ge$ 12 đơn/năm**:
   - Tiêu chuẩn trung vị $\ge 12$ đơn/năm bảo đảm rằng **ít nhất 50% sản phẩm trong tầng hot bán được tối thiểu 1 đơn mỗi tháng**, phản ánh sức sống thực tế và tính liên tục của dữ liệu hành vi người dùng trên sàn VietCraft.
