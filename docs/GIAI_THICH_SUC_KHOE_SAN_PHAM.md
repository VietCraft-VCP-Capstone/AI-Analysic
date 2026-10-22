# Điểm sức khoẻ sản phẩm (health-2.0): giải thích cho người mới

Cập nhật 22/10/2026. Viết cho chủ dự án và hội đồng. Đọc từ trên xuống, mỗi phần ngắn.

---

## 1. Điểm này là gì

Điểm sức khoẻ (0 đến 100) chấm **chất lượng tin đăng**: sản phẩm đã có đủ ảnh, mô tả, tag, đánh giá và giá hợp lý để khách dễ chọn chưa. Đây là tiêu chí mục 3.8.4 của SRS.

Điểm này **không phải dự báo doanh số**. Điểm 90 không có nghĩa là sản phẩm sẽ bán được bao nhiêu. Nó chỉ nói tin đăng đã làm đủ việc cơ bản chưa.

Hình dung như bảng điểm nhiều môn: mỗi môn chấm trên 100, các môn có hệ số khác nhau, cộng lại thành một điểm chung.

---

## 2. Năm yếu tố

Mỗi yếu tố cho một **điểm con** từ 0 đến 100. Nhân điểm con với **trọng số** (%) để ra **điểm thành phần**. Cộng các điểm thành phần ra điểm tổng.

Công thức: **điểm thành phần = trọng số × điểm con ÷ 100**.

| Yếu tố | Cách chấm điểm con | Mốc | Trọng số |
|---|---|---|---|
| Ảnh | số ảnh ÷ 6, tối đa 100 | 6 ảnh | 28 |
| Mô tả | số ký tự (bỏ khoảng trắng đầu và cuối) ÷ 570, tối đa 100 | 570 ký tự | 12 |
| Tag | số tag đã duyệt ÷ 3, tối đa 100 | 3 tag | 10 |
| Đánh giá | xem bên dưới | — | 5 |
| Giá | xem bên dưới | — | 45 |

**Đánh giá.** Chưa có đánh giá thì điểm con bằng 0. Có đánh giá thì:

(số đánh giá từ 4 sao + 5 × p0) ÷ (số đánh giá + 5) × 100

p0 là tỉ lệ đánh giá từ 4 sao của cả sàn, tính trên đơn thật. Hình dung 5 đánh giá "đệm" mang đúng tỉ lệ đánh giá tốt của cả sàn. Nhờ vậy một sản phẩm chỉ có 1 đánh giá 5 sao không nhảy lên 100 ngay.

**Giá.** Giá tham chiếu là trung vị giá của sản phẩm cùng danh mục, không tính chính nó, và cần ít nhất 8 sản phẩm khác. Nếu không đủ thì lấy trung vị cùng nhóm hàng, rồi đến trung vị giá Tiki theo nhóm. Tỉ lệ giá = giá bán ÷ giá tham chiếu:
- Tỉ lệ 1 trở xuống: điểm con 100.
- Tỉ lệ 2 trở lên: điểm con 0.
- Ở giữa: giảm đều.

Giá bán của sản phẩm là trung vị giá các biến thể đang bật và có giá trên 0.

**Thiếu dữ liệu thì điểm con bằng 0.** Ví dụ chưa có ảnh thì điểm ảnh bằng 0. Hệ thống không chia lại trọng số cho các yếu tố còn lại. Yếu tố nào thiếu được ghi trong `axes_missing`.

**Màu theo mức điểm** (giống màn hình hiện tại):
- 80 trở lên: **Tốt** (xanh lá).
- 50 đến 79: **Cần cải thiện** (cam).
- Dưới 50: **Kém** (đỏ).

---

## 3. Trọng số học từ đâu

Không ai đặt trọng số bằng tay. Máy học từ dữ liệu, rồi được kiểm tra trên đề thi chưa từng thấy.

**Bước 1: học trên Olist.** Olist là bộ dữ liệu sàn thương mại điện tử ở Brazil, có số bán thật. Lấy 4 mốc thời gian (từ 1/7 đến 1/10/2017). Với mỗi sản phẩm tại mỗi mốc, hỏi: 90 ngày sau, nó có nằm trong 25% bán chạy nhất cùng danh mục không? Máy học từ 33.198 dòng (sản phẩm × mốc) để tìm hệ số cho 4 yếu tố:
- Giá: 0,433.
- Ảnh: 0,267.
- Mô tả: 0,120.
- Đánh giá: âm (-0,076), nên đặt mức sàn 5%.

Olist không có tag, nên tag được cố định 10% theo chính sách.

**Bước 2: thi trên Tiki.** Đề thi là 6.676 sản phẩm Tiki mà máy chưa từng thấy. Đo bằng **AUC**. Hình dung: lấy ngẫu nhiên một sản phẩm bán chạy và một sản phẩm không bán chạy. AUC là xác suất điểm của sản phẩm bán chạy cao hơn. 0,5 là đoán bừa như tung đồng xu. 1 là xếp đúng mọi cặp.

Kết quả trên đề Tiki (khoảng tin cậy 95% trong ngoặc):
- Trọng số học được: **0,567** (0,522 đến 0,602).
- Chia đều 5 yếu tố: **0,566** (0,524 đến 0,599).
- Luật cũ health-1.0: **0,519** (0,485 đến 0,557). Luật cũ chỉ dùng ảnh và mô tả trên Tiki.

**Bước 3: cổng đạt.** Cổng là kiểm định "không thua": đạt khi cận trên của khoảng chênh lệch ≥ 0.
- Học trừ chia đều: khoảng [-0,006; 0,009]. Chứa 0.
- Học trừ luật cũ: khoảng [-0,005; 0,098]. Chứa 0.

**Kết luận thật thà:** trên đề Tiki, trọng số học được và chia đều **ngang nhau về thống kê**. Cổng đạt vì cận trên không âm, nhưng không chứng minh được học tốt hơn chia đều. Ta giữ trọng số học được vì nó đến từ dữ liệu và cho thứ tự yếu tố có cơ sở. Không phải vì nó dự đoán tốt hơn.

---

## 4. Ví dụ tính từng bước

Số đầu vào dưới đây do tôi chọn để minh hoạ, không phải sản phẩm thật. Giả định: giá tham chiếu 120.000đ, tỉ lệ đánh giá từ 4 sao của sàn là 80%.

| Yếu tố | Đầu vào | Điểm con | Điểm thành phần | Việc cần làm | +N |
|---|---|---|---|---|---|
| Ảnh | 4 ảnh | 66,7 | 28 × 66,7 ÷ 100 = 18,7 | Thêm 2 ảnh | 9,3 |
| Mô tả | 285 ký tự | 50,0 | 12 × 50 ÷ 100 = 6,0 | Viết dài thêm 285 ký tự | 6,0 |
| Tag | 2 tag | 66,7 | 10 × 66,7 ÷ 100 = 6,7 | Chọn thêm 1 tag | 3,3 |
| Đánh giá | 3 tốt trên 4 | 77,8 | 5 × 77,8 ÷ 100 = 3,9 | Hỏi khách chưa hài lòng | 1,1 (trần) |
| Giá | 144.000đ, gấp 1,2 lần tham chiếu | 80,0 | 45 × 80 ÷ 100 = 36,0 | Giảm về 120.000đ | 9,0 |

**Tổng:** 18,7 + 6,0 + 6,7 + 3,9 + 36,0 = **71,3**, nằm trong mức **Cần cải thiện**.

**Danh sách việc cần làm** được sắp theo +N giảm dần: ảnh 9,3, giá 9,0, mô tả 6,0, tag 3,3, đánh giá 1,1. Nếu bằng nhau thì việc ít công hơn đứng trước.

---

## 5. Vì sao "+N điểm" đúng

+N là số điểm thành phần sẽ tăng nếu yếu tố đó đạt 100: **trọng số × (100 − điểm con) ÷ 100**, làm tròn một chữ số.

Điểm thành phần đã làm tròn cộng lại đúng bằng điểm tổng, nên cộng tay bảng chi tiết ra đúng điểm tổng. Với ảnh, mô tả, tag và giá, làm đúng việc được gợi ý thì điểm tổng tăng đúng +N. Ví dụ thêm 2 ảnh: điểm ảnh từ 18,7 lên 28,0, tăng đúng 9,3.

Hai điều cần nói rõ:
- **Làm tròn:** +N được tính từ điểm con đã làm tròn một chữ số, nên có thể lệch 0,1 so với điểm tăng thật. Khi thử mọi giá trị điểm con, tỉ lệ lệch khoảng 3% đến 11% tuỳ yếu tố.
- **Đánh giá:** điểm con đánh giá chỉ lên 100 khi cả sàn có 100% đánh giá từ 4 sao. Vì vậy +N của đánh giá là trần, không phải số chắc chắn.

---

## 6. Khi nào điểm thay đổi (BR-181)

Hệ thống tự chấm lại theo 3 cách:

1. **Mỗi 60 giây:** tìm sản phẩm vừa thay đổi (sửa tin, đổi giá hoặc tồn kho biến thể, có lượt xem, có đơn mới) và chấm lại. Ví dụ thêm 1 ảnh, trong khoảng một phút danh sách sẽ tăng đúng +N của việc thêm ảnh.
2. **Mỗi ngày lúc 00:00 UTC** (07:00 giờ Việt Nam): chấm lại toàn bộ sản phẩm.
3. **Khi máy khởi động:** nếu điểm mới nhất trong cơ sở dữ liệu chưa phải health-2.0, chấm lại toàn sàn một lần.

Trang chi tiết tính điểm trực tiếp khi mở.

---

## 7. Giới hạn cần biết

- **Không phải dự báo doanh số.** Trên Olist, yếu tố nội dung và giá chỉ dự đoán yếu: AUC 0,539 trên tập thử. Để so sánh, "đơn gần nhất" đạt 0,735. Lịch sử bán mạnh hơn nhiều.
- **Học không hơn chia đều có ý nghĩa thống kê** (mục 3).
- **Mô hình cây cho kết quả cao hơn.** HistGB trên đúng 4 điểm con đạt 0,653 trên Olist thử, cao hơn trọng số tuyến tính 0,539. Thiết kế chọn cách tuyến tính vì dễ giải thích.
- **Mô tả Tiki bị cắt khoảng 200 ký tự**, nên trên Tiki yếu tố mô tả bị giới hạn. Mốc 570 lấy từ Olist.
- **Giá là yếu tố nặng nhất (45%).** Giá Olist là giá bán thực tế trong 180 ngày, còn giá VietCraft là giá niêm yết. Hai loại giá khác nhau.
- **Giá tham chiếu khi học ít tầng hơn khi chấm thật.** Khi học chỉ có danh mục rồi cả mốc. Khi chấm thật có thêm nhóm và Tiki. Điểm giá có thể lệch vì vậy.
- **Tập học Olist chỉ có sản phẩm đã bán trong 180 ngày trước mốc.** Hệ thống thật chấm mọi tin đăng.
- **Ảnh và mô tả Olist là ảnh chụp hiện tại,** không theo từng mốc thời gian.

---

## 8. Chạy lại việc học

Trong thư mục `vc-ai/AI-Analysic`, chạy:

```
PYTHONPATH=. .venv/bin/python -m scripts.f29_health.run
```

Mất vài chục giây.
- Nếu cổng đạt: ghi `app/core/f29/health_weights.json` và báo cáo `notes/docs-listing/F29_HEALTH_V2.md`.
- Nếu không đạt: thoát với mã 2 và không ghi gì.

Sau khi đổi trọng số, điểm cũ không tự chấm lại khi khởi động nếu vẫn là health-2.0. Điểm sẽ được chấm lại toàn sàn vào 00:00 UTC kế tiếp.

**File liên quan:** `app/core/f29/factors.py` (công thức điểm con), `app/core/f29/calculator.py` (ghép điểm), `app/core/f29/todos.py` (việc cần làm và +N), `app/core/f29_scheduler.py` (BR-181).
