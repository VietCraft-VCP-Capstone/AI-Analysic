# Cơ chế train AI của VietCraft: dùng model gì, thuật toán gì, học máy hay LLM

Ngày viết: 2026-10-21 · Model đang chạy: Listing Intelligence `li-1.6`, Health ML `health-ml-1.1`.

Tài liệu này giải thích cách hệ thống học và cách nhóm đã làm, viết cho người chưa quen ML. Số liệu chi tiết và nguồn của từng con số nằm ở `docs/LISTING_INTEL_TECH_REPORT.md` (báo cáo kỹ thuật) và `docs/LISTING_INTEL_REPORT.md` (báo cáo đánh giá tự sinh).

---

## 1. Trả lời nhanh

**Hệ thống dùng học máy cổ điển (classical machine learning), không dùng LLM.**

| Thành phần | Loại | Thuật toán / model | Có tự train không |
|---|---|---|---|
| Model chấm tổng (fusion) | Học máy có giám sát | `HistGradientBoostingClassifier` (scikit-learn) | **Có**, train trên 30,402 sản phẩm Tiki |
| Trục thị hiếu và cạnh tranh | Học máy có giám sát + tìm láng giềng | Gradient boosting trên 3 feature kNN | **Có** |
| Biến ảnh và chữ thành vector | Model học sâu đã huấn luyện sẵn (pretrained) | SigLIP2 base, bản ONNX int8, chạy trên CPU | **Không**, dùng nguyên, không fine-tune |
| Đo chất lượng ảnh | Xử lý ảnh truyền thống | OpenCV: độ nét, phơi sáng, tương phản, viền, chữ đè | Không cần train |
| Từ khoá "bán chạy" | Thống kê | Log-lift n-gram có làm trơn Laplace | Đếm trên tập train |
| Mùa vụ, trend | Thống kê chuỗi thời gian | STL decomposition (statsmodels), đà tăng 4 tuần | Tính từ chuỗi Google Trends |
| Trục ảnh, trục chữ, trục tag | Công thức có trọng số | Tổng có trọng số, quy ra phân vị | Trọng số chọn trên tập validation |
| Lời khuyên | Mẫu câu viết sẵn trong code | `advice.py` + ước lượng counterfactual trên model | Không |

Điểm sức khoẻ (Health ML) là một pipeline riêng, train trên Olist (mục 9).

## 2. Vì sao học máy mà không phải LLM

| Câu hỏi | Học máy (đang dùng) | LLM |
|---|---|---|
| Có đo được đúng sai không? | Có: so với số bán thật, ra AUC và khoảng tin cậy | Khó: LLM "nhận xét" nghe hợp lý nhưng không có nhãn để kiểm |
| Chạy lại có ra cùng kết quả? | Có: học lại 2 lần giống hệt từng byte | Không chắc chắn |
| Chi phí mỗi lần chấm | Khoảng 0.2–0.3 giây trên CPU, miễn phí | Gọi API trả tiền, chậm hơn |
| Giải thích được không? | Có: biết feature nào làm điểm tăng hoặc giảm | Khó |
| Server | Không cần GPU, không cần torch | Cần API ngoài hoặc GPU |

Spec của tính năng ghi rõ "LLM chấm điểm" nằm ngoài phạm vi.

**SigLIP2 không phải LLM.** Nó là model đối chiếu ảnh–chữ (contrastive image–text encoder) của Google, giấy phép Apache-2.0. Nó chỉ biến một ảnh hoặc một câu thành một dãy 768 con số (vector), sao cho ảnh và câu mô tả cùng một thứ có vector gần nhau. Nó không sinh chữ, không trả lời câu hỏi. Hệ thống dùng các vector này làm nguyên liệu đầu vào cho model học máy.

## 3. Bài toán được đặt như thế nào

Câu hỏi model trả lời: **"Listing này có thuộc nhóm 25% bán chạy nhất trong cùng danh mục không?"**

- Đây là bài toán phân loại nhị phân (binary classification). Nhãn `top25` = 1 nếu số bán (`quantity_sold`) nằm trong 25% cao nhất của cùng (nguồn dữ liệu, nhóm danh mục), ngược lại là 0.
- Với tiki23, số bán được chia cho tuổi listing (`sold / max(tuổi_ngày, 30)`) để sản phẩm cũ không được lợi. Tuổi listing không bao giờ được dùng làm feature.
- Model trả ra xác suất 0–1. Xác suất được đổi thành **phân vị** so với các listing Tiki cùng nhóm. Ví dụ điểm 93 nghĩa là listing này được model chấm cao hơn 93% listing tham chiếu.
- Điểm hiển thị = phân vị × hệ số nhu cầu theo ngày `h(d)` (mục 5.6), nên điểm thay đổi theo mùa.

## 4. Dữ liệu

| Bộ dữ liệu | Dùng để | Kích thước |
|---|---|---|
| `tiki23` (Kaggle, Tiki 2023) | Học chữ, giá; túi, giày, phụ kiện; không có ảnh | 41,575 dòng sạch |
| `tiki26` (Kaggle, Tiki crawl 04/2026, Apache-2.0) | Học đủ 5 trục; thời trang, gia dụng, thể thao; tập test chính | 3,998 dòng sạch, 3,997 ảnh |
| `tikifashion` (Kaggle) | Kiểm tra ảnh và chữ có khớp nhau không | 5,000 ảnh mẫu |
| `tikireviews` (Kaggle) | Mùa vụ theo tháng của từng nhóm | 584,005 review |
| Google Trends Việt Nam | Chỉ số mùa và đà tăng của 45 từ khoá | 262 tuần mỗi từ khoá |
| `vietcraft-test` (Mongo local) | Chạy thử trên sản phẩm của sàn | 29 sản phẩm mô phỏng |

Lý do chọn Tiki: dữ liệu thương mại điện tử tiếng Việt, có số bán thật. Các bộ dữ liệu chỉ dùng cho học thuật, không commit CSV hay ảnh vào git.

## 5. Biến một listing thành con số (feature)

Model không đọc được ảnh hay câu chữ, nên mỗi listing được đổi thành **56 con số**.

### 5.1 Ảnh (31 cột)
1. Ảnh được đưa về đúng dạng lúc train: cạnh dài 256 px, nén JPEG chất lượng 85.
2. **OpenCV** đo 9 chỉ số: độ nét (phương sai Laplacian), phơi sáng, tương phản, viền, có chữ đè hay không, kích thước…
3. **SigLIP2** biến ảnh thành vector 768 số. Vector này được nén còn 16 số bằng **PCA** (fit trên tập train).
4. **Phân loại kiểu ảnh không cần train (zero-shot):** so vector ảnh với vector của 4 câu tiếng Việt như "ảnh sản phẩm trên nền trắng", "ảnh người mẫu mặc sản phẩm ngoài đời". Độ gần với từng câu được đổi thành xác suất (softmax) cho 4 kiểu.
5. Độ khớp ảnh với tiêu đề và với danh mục: cosine giữa vector ảnh và vector chữ.

### 5.2 Chữ (15 cột)
- Độ dài tiêu đề, tỉ lệ viết hoa, tỉ lệ lặp từ, số từ cấm (87 cụm), có nêu chất liệu, màu, size hay không.
- **Log-lift từ khoá:** từ nào xuất hiện ở nhóm bán chạy nhiều hơn mặt bằng chung thì có lift dương:

  `lift(từ) = log[ (số lần ở top25 + 1) / (tổng từ top25 + V) ÷ (số lần ở tất cả + 1) / (tổng từ tất cả + V) ]`

  Cộng 1 (làm trơn Laplace) để từ hiếm không có lift ảo. Từ phải xuất hiện ít nhất 20 lần mới được tính.

### 5.3 Thị hiếu và cạnh tranh (3 cột), thuật toán kNN
Tìm **20 listing Tiki giống nhất** (k-nearest neighbors, đo bằng cosine trên vector ảnh + tiêu đề):
- `knn_price_pct`: giá của mình cao hơn bao nhiêu % trong 20 listing đó.
- `knn_dup_count`: bao nhiêu listing gần như trùng (cosine > 0.92), tức mức độ cạnh tranh.
- `top_centroid_margin`: listing gần "tâm" nhóm bán chạy hơn hay gần tâm nhóm còn lại hơn.

### 5.4 Trend (3 cột)
Từ khoá trend khớp với tiêu đề (đã bỏ dấu, khớp chữ nguyên văn), số từ khoá khớp, đà tăng lớn nhất.

### 5.5 Nhóm danh mục (1 cột)
Thời trang, túi, giày, phụ kiện, gia dụng hoặc thể thao.

### 5.6 Hệ số nhu cầu theo ngày `h(d)`
- **Chỉ số mùa:** tách chuỗi Google Trends 5 năm bằng **STL** (chu kỳ 52 tuần, chế độ robust) để lấy phần lặp lại hằng năm.
- **Đà tăng:** trung bình 4 tuần gần nhất chia cho 4 tuần trước đó, trừ 1, giới hạn trong ±0.5.
- `h(d)` = trung bình theo từ khoá của (chỉ số mùa tuần d × (1 + đà tăng)), giới hạn trong [0.5; 1.5]. Không khớp từ khoá nào thì dùng mùa vụ của nhóm (từ `tikireviews`), không có nữa thì bằng 1.

## 6. Thuật toán chính: Gradient Boosting

**Cách hoạt động:** model gồm nhiều cây quyết định nhỏ ("nếu giá < X và có nêu chất liệu thì…"). Cây đầu đoán thô; mỗi cây sau học cách sửa phần sai của các cây trước. Cộng tất cả lại ra xác suất cuối.

**Vì sao chọn `HistGradientBoostingClassifier`:**
- Mạnh nhất với dữ liệu dạng bảng số (56 cột), loại dữ liệu này deep learning thường không hơn.
- Tự xử lý giá trị thiếu (NaN), ví dụ listing không có ảnh.
- Chạy nhanh trên CPU, file model nhỏ, có sẵn trong scikit-learn, không cần torch hay GPU.

**Tham số:** `learning_rate=0.05`, tối đa 400 vòng, dừng sớm (early stopping) khi không còn cải thiện. Thực tế model gộp dừng ở 171 vòng.

**Thuật toán phụ:** TF-IDF + Logistic Regression (làm baseline để so sánh), kNN, PCA, STL.

## 7. Quy trình train (pipeline)

Chạy lần lượt từ thư mục `vc-ai/AI-Analysic`:

| Bước | Lệnh | Làm gì |
|---|---|---|
| 1 | `python -m scripts.li.ingest` | Làm sạch Tiki: bỏ dòng thiếu tên hoặc giá, bỏ trùng, ánh xạ danh mục, gắn nhãn top25, chia tập |
| 2 | `python -m scripts.li.images` | Tải ảnh tiki26 và tikifashion về máy |
| 3 | `python -m scripts.li.fetch_models` | Tải SigLIP2 ONNX, kiểm tra sha256 |
| 4 | `python -m scripts.li.build_features` | Nhúng ảnh và chữ, fit PCA, bảng lift, chỉ mục kNN (chỉ trên train), dựng bảng 56 cột |
| 5 | `python -m scripts.li.train` | Train model gộp và các model trục, lưu bundle vào `app/core/listing_intel/model/` |
| 6 | `python -m scripts.li.evaluate` | Chấm trên validation và test, baseline, ablation, sanity check, sinh lại báo cáo |

**Chia tập:** 70% train, 15% validation, 15% test, **chia theo shop** (`GroupShuffleSplit`). Một shop chỉ nằm trong một tập, để model không "thuộc bài" của shop đó rồi được chấm lại trên chính shop đó.

## 8. Đánh giá và chống ăn gian

### 8.1 Chống rò rỉ dữ liệu (leakage)
| Nguy cơ | Cách chặn |
|---|---|
| Model nhớ shop | Chia tập theo shop; kiểm tra lại: 0 shop nằm ở 2 tập |
| Feature tính từ đáp án | Bảng lift và tâm nhóm của dòng train tính kiểu out-of-fold (5 fold theo shop) |
| Thông tin test lọt vào train | PCA, giá trung vị, chỉ mục kNN chỉ fit trên train; kNN bỏ láng giềng cùng shop |
| Nhìn trước tương lai | Chuỗi trend cắt tại ngày thu dữ liệu |
| Cột "đáp án trá hình" | Loại mọi cột review, rating, lượt thích, doanh thu |

### 8.2 Cách đo
- **ROC-AUC:** xác suất model xếp một listing bán chạy cao hơn một listing không bán chạy. 0.5 là đoán bừa, 1.0 là hoàn hảo.
- **Khoảng tin cậy 95%:** bootstrap 200 lần, lấy mẫu theo shop.
- **So với baseline:** đoán ngẫu nhiên, luật health-1.0 cũ, chỉ dùng giá, TF-IDF tiêu đề + logistic. Model chỉ được nhận là "đã đo" khi thắng baseline mạnh nhất với khoảng tin cậy không chứa 0.
- **Ablation:** bỏ từng trục rồi train lại, xem AUC giảm bao nhiêu.
- **Sanity check:** xáo trộn nhãn thì AUC phải về khoảng 0.5 (đo được 0.495). Train lại 2 lần phải giống hệt. Ảnh đổi sáng tối hoặc nén thì điểm không được đổi nhiều.

### 8.3 Kết quả (test tiki26, 782 sản phẩm, 234 cụm shop)
| Phương pháp | ROC-AUC [CI95] |
|---|---|
| **Model gộp** | **0.626 [0.539; 0.753]** |
| TF-IDF tiêu đề + logistic (baseline mạnh nhất) | 0.600 [0.518; 0.701] |
| Chỉ giá + nhóm | 0.557 [0.482; 0.654] |
| Luật health-1.0 cũ | 0.500 |
| Ngẫu nhiên | 0.517 |

**Cách đọc trung thực:**
- Model tốt hơn luật cũ và tốt hơn đoán bừa rõ ràng.
- Hơn baseline chọn trên validation có ý nghĩa: +0.068 [0.019; 0.126].
- **Chưa hơn có ý nghĩa** baseline mạnh nhất trên test: +0.026 [−0.071; 0.119]. Vì vậy cả 5 trục chỉ được gắn nhãn "thực hành tốt", không gắn "đã đo".
- Trên tập tiki23 lớn hơn, model gộp đạt 0.712 [0.677; 0.742].
- Tập test đã được đọc 7 lần qua các phiên bản; báo cáo công bố đủ, nên con số có thể hơi lạc quan.

Kết luận: tính năng nên được trình bày là **công cụ gợi ý dựa trên dữ liệu**, không phải dự báo doanh số trên VietCraft.

### 8.4 Vì sao trục ảnh và trục chữ dùng công thức thay model
Quy tắc đặt trước: một trục chỉ dùng model khi cận dưới khoảng tin cậy AUC trên validation lớn hơn 0.5.
- **Model ảnh** không bền: chỉ đổi sáng tối hoặc nén ảnh mà điểm lệch tới 33.8 điểm (p90 trên validation, công thức chỉ 13.3), AUC test 0.486. Nên chuyển sang công thức bền với phơi sáng, lệch trung vị chỉ 2.6–4.3 điểm.
- **Model chữ** đạt AUC validation 0.462 [0.383; 0.589], cận dưới dưới 0.5, không qua quy tắc, nên dùng công thức (validation 0.577).
- **Model thị hiếu** qua quy tắc (0.616 [0.544; 0.703]), nên được dùng.

Đây là kết quả âm tính được báo cáo thẳng, không giấu.

## 9. Pipeline thứ hai: Health ML trên Olist

Làm trước Listing Intelligence, để trả lời nhận xét "điểm sức khoẻ không có dữ liệu, không có train, không có đánh giá".

| Mục | Nội dung |
|---|---|
| Câu hỏi | Sản phẩm có ra ít nhất 1 đơn trong 90 ngày tới không |
| Dữ liệu | Olist (sàn TMĐT thật của Brazil), khoảng 100 nghìn đơn 2017–2018 |
| Chia tập | **Theo thời gian**: train các mốc 07–10/2017, validation 01/2018, test sau đó; mọi feature chỉ dùng dữ liệu trước mốc |
| Thuật toán | Logistic Regression và HistGradientBoosting, chọn trên validation |
| Kết quả test | Model triển khai 0.761 [0.747; 0.774]; baseline mạnh nhất "đơn gần nhất" 0.734; chênh +0.027 [0.016; 0.040], **có ý nghĩa**; luật health-1.0 chỉ 0.517 |
| Phát hiện | Chỉ lịch sử bán thật sự có ích (bỏ đi AUC giảm 0.067); nội dung, giá, đánh giá thêm < 0.005, nên lời khuyên của các nhóm này bị tắt |
| Chạy lại | `python -m scripts.f29_ml.run` → `docs/F29_ML_RESULTS.md` |

## 10. Lúc chạy thật (khi seller mở trang)

1. BE kiểm tra đăng nhập, quyền sở hữu, giới hạn 20 lần/phút cho chấm thử, rồi chuyển cho AI.
2. AI tải ảnh an toàn (chỉ từ Cloudinary, chặn chuyển hướng sang host lạ), đưa về 256 px như lúc train.
3. Tính 56 feature bằng **đúng hàm đã dùng lúc train** (`features.assemble`), để train và chạy thật không lệch nhau.
4. Che các feature mà nhóm đó không có lúc train; listing không ảnh không bao giờ được điểm cao hơn bản có ảnh.
5. Model ra xác suất → phân vị → nhân `h(d)` → điểm 0–100, kèm 8 điểm cho 8 tuần tới.
6. Lời khuyên: thử thay một feature bằng giá trị trung vị của nhóm bán chạy, xem điểm tăng bao nhiêu (ước lượng, không phải nhân quả).

## 11. Quá trình làm

| Giai đoạn | Việc |
|---|---|
| Phân tích | Đọc nhận xét reviewer, roast hiện trạng 3 repo, xác định điểm yếu: chấm theo checklist, không dữ liệu, không đánh giá |
| Pipeline Olist | Dựng train/validation/test, baseline, khoảng tin cậy cho điểm sức khoẻ |
| Brainstorm và spec | Thiết kế 5 trục, chọn dữ liệu Tiki, ràng buộc không torch và không LLM, tiêu chí thành công đo được |
| Plan 12 task | Dữ liệu, xử lý tiếng Việt, embedder, tải ảnh, trend, BE, FE, bảng feature, trục tag/thị hiếu, train, runtime, E2E |
| Thực hiện | Nhiều agent làm song song; mỗi task có 1 người làm và 1 reviewer độc lập, sai thì sửa rồi review lại |
| Vòng cải tiến li-1.0 → li-1.6 | Sửa embedder phụ thuộc lô, tắt khớp trend bằng vector (chỉ 1/100 đúng), chuyển trục ảnh và chữ sang công thức, sửa listing không ảnh bị điểm cao, sửa lời khuyên "thêm ảnh" |
| Kiểm tra go-live | Audit sẵn sàng, chạy đầu cuối có chụp màn hình, sửa lỗi go-live, review toàn nhánh và re-review đều đạt |

## 12. Câu hỏi hội đồng có thể hỏi

| Câu hỏi | Trả lời ngắn |
|---|---|
| Có train model không hay dùng sẵn? | Có train: model gộp và model thị hiếu train trên 30,402 sản phẩm Tiki. SigLIP2 dùng sẵn để biến ảnh thành vector, giống dùng thư viện xử lý ảnh |
| Sao không dùng deep learning hay LLM? | Dữ liệu dạng bảng thì gradient boosting mạnh hơn; LLM không đo được độ chính xác, tốn tiền và không lặp lại được |
| AUC 0.626 có thấp không? | Dự báo bán chạy chỉ từ nội dung listing vốn khó. Model hơn luật cũ (0.500) rõ ràng, nhưng chưa hơn có ý nghĩa baseline TF-IDF; báo cáo nói thẳng điều này |
| Sao chia tập theo shop? | Nếu không, model nhớ phong cách của shop và điểm test bị thổi phồng |
| Dữ liệu thật của VietCraft đâu? | Sàn chưa đủ đơn thật để làm nhãn; mới chạy trên 29 sản phẩm mô phỏng. Khi có đơn thật thì train lại bằng cùng pipeline |
| Điểm thay đổi theo mùa thế nào? | Nhân với `h(d)` lấy từ Google Trends; ví dụ áo khoác lông cừu 93 điểm hôm nay, 86 tuần Halloween, 98 vào tháng 12 |
