# Báo cáo Kiểm tra Chất lượng (QC) - Bộ Dữ liệu Tags

Báo cáo kiểm tra tính toàn vẹn của mã tag (`tags.csv`), quan hệ với từ khóa Google Trends (`tag_keyword_map.csv`), danh mục sản phẩm (`categories.csv`) và kiểm tra tự động thuật toán chuẩn hóa tag.

---

## 1. Kết quả kiểm tra chất lượng (5 bài kiểm tra)

| # | Nội dung kiểm tra | Kết quả thực tế | Trạng thái |
|---|---|---|---|
| 1 | 1. Có tag nào trùng mã không | 0 tag bị trùng | **ĐẠT** |
| 2 | 2. Có từ khoá Google nào chưa có tag không | 0 từ khóa bị sót | **ĐẠT** |
| 3 | 3. Tổng số tag | 77 tag (phạm vi: từ 60 tới 80) | **ĐẠT** |
| 4 | 4. Có tag nào không thuộc danh mục nào không | 0 tag mồ côi | **ĐẠT** |
| 5 | 5. Chạy 10 test làm sạch tag | 10/10 bài test thông qua | **ĐẠT** |

---

## 2. Chi tiết kết quả 10 bài test chuẩn hóa làm sạch tag (`clean_tag`)

Hàm `clean_tag` giúp xử lý các tag nhập tự do từ người bán để quy đổi về tag chuẩn trong hệ thống (hoặc giữ nguyên nếu là tag mới lạ).

| Dữ liệu người bán gõ | Kết quả mong đợi | Kết quả thực tế | Trạng thái |
|---|---|---|---|
| `Áo Tết` | `ao-tet` | `ao-tet` | **ĐẠT** |
| `ao tet` | `ao-tet` | `ao-tet` | **ĐẠT** |
| `  áo   tết  ` | `ao-tet` | `ao-tet` | **ĐẠT** |
| `AO TET!!!` | `ao-tet` | `ao-tet` | **ĐẠT** |
| `áo tết 2027` | `ao-tet` | `ao-tet` | **ĐẠT** |
| `aó tết` | `ao-tet` | `ao-tet` | **ĐẠT** |
| `Áo-Tết` | `ao-tet` | `ao-tet` | **ĐẠT** |
| `qua 20/10` | `qua-20-10` | `qua-20-10` | **ĐẠT** |
| `quà tặng mẹ` | `qua-tang-me` | `qua-tang-me` | **ĐẠT** |
| `xyz123` | `xyz123` | `xyz123` | **ĐẠT** |

---
*Báo cáo được chạy và tạo tự động bởi verify_tags.py.*
