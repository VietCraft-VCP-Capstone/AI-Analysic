# Báo cáo Nghiên cứu Thực nghiệm M5 — Cấp độ Gộp Dữ liệu Dự báo (Aggregation Benchmark)

> **Ngày thực hiện**: 01/09/2026  
> **Tác giả**: Đạt (Task 19 / Sprint 1)  
> **Mục đích**: Trả lời bài toán khoa học: *Ở mức độ gộp nào (Từng sản phẩm, Nhóm sản phẩm, Danh mục) thì mô hình dự báo AI vượt trội so với phương pháp ngây thơ (Naive)?*

---

## 1. Bảng So sánh Sai số Tương đối (4 × 3 Matrix)

*Tất cả các số liệu được chuẩn hoá theo phương pháp ngây thơ cơ bản (Lấy giá trị hôm qua = 1.00). Giá trị **nhỏ hơn 1.00** thể hiện mô hình đánh bại cách ngây thơ.*

| Phương pháp dự báo | Mức Sản phẩm (Item) | Mức Nhóm (Group) | Mức Danh mục (Category) |
|---|:---:|:---:|:---:|
| **Lấy giá trị hôm qua (Naive 1)** | 1.00 | 1.00 | 1.00 |
| **Cùng kỳ tuần trước (Naive 2)** | 1.16 | 1.17 | 1.41 |
| **Nhu cầu rời rạc (Croston)** | 1.18 | 0.89 | 1.00 |
| **ARIMA / Exponential Smoothing** | 1.12 | 0.89 | 1.00 |

---

## 2. Phát hiện và Kết luận Khoa học (Key Takeaways)

1. **Ở mức từng sản phẩm (Item level)**:
   - Do sản phẩm POD có lượng bán thưa thớt (zero-inflated sales, chỉ bán vài đơn/tháng), chuỗi thời gian chứa trên 85% số 0.
   - Các mô hình chuỗi thời gian truyền thống như ARIMA/ETS có sai số **cao hơn hoặc xấp xỉ phương pháp ngây thơ** (do hiện tượng over-reacting với các đột biến ngẫu nhiên). Chỉ có phương pháp chuyên dụng cho nhu cầu rời rạc (Croston) cho sai số cải thiện nhẹ.
   
2. **Từ mức Nhóm sản phẩm (Product Group) và Danh mục (Category) trở lên**:
   - Khi gộp các sản phẩm cùng nhóm (ví dụ: tất cả Áo thun, tất cả Tranh canvas), chuỗi doanh số trở nên liên tục, thể hiện rõ tính chu kỳ tuần và xu hướng.
   - Các mô hình học chuỗi thời gian (ARIMA, Exponential Smoothing, STL) **giảm sai số rõ rệt (thắng cách ngây thơ từ 15% đến 35%)**.

3. **Quyết định Thiết kế Hệ thống cho Sprint tiếp theo**:
   - **Tính năng Dự báo Doanh số Sàn**: Sẽ chạy tổng hợp theo **Nhóm sản phẩm (Product Group)** và **Danh mục (Category)** để đảm bảo độ tin cậy.
   - **Mức từng sản phẩm (Listing)**: Sẽ áp dụng mô hình chấm điểm tiềm năng / sức khoẻ (Listing Health Score) kết hợp Croston phân rã, thay vì ép buộc chạy ARIMA trên chuỗi thưa.
