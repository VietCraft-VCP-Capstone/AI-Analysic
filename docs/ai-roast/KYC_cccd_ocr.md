# KYC Quét CCCD và "Báo cáo kiểm định ảnh thật/giả": roast và đường ra

> Endpoint BE `POST /api/seller/kyc/scan-cccd` → AI `POST /api/v1/ocr/cccd/` · Trang FE `/seller/register` "Đăng ký Trở thành Người bán VietCraft" (`FE/src/modules/seller/pages/SellerRegisterPage.tsx`) · File chính `app/services/cccd_ocr_service.py`, `app/api/v1/cccd_ocr.py`, `BE/src/modules/seller/application/seller-kyc.service.ts`, `BE/src/modules/seller/presentation/seller-kyc.router.ts`, `BE/src/shared/upload/kyc-storage.middleware.ts` · Ngày 2026-10-21 · Người viết: Claude (subagent)

Ký hiệu: `service:` = `cccd_ocr_service.py`, `ocr.py:` = `cccd_ocr.py`, `kyc.svc:` = `seller-kyc.service.ts`, `kyc.router:` = `seller-kyc.router.ts`, `FE:` = `SellerRegisterPage.tsx`.

## 0. Bản đăng ký nói gì

| Hạng mục | SRS Report 3 (tóm tắt) |
|---|---|
| Mục SRS | **Không có mục chức năng chi tiết cho đăng ký seller/KYC.** Chỉ có UC 40 "Register as Seller" trong bảng use case và 3 màn hình: 54, 67, 68. Mục gần nhất có đặc tả đầy đủ: 3.4.1 Create & Setup Shop Profile (phần thông tin shop) |
| OCR CCCD, "thật/giả" | **Không có.** grep `OCR`, `CCCD`, `căn cước` trong `report3.txt`: 0 kết quả. Chữ "KYC" chỉ xuất hiện trong tên popup 68 |
| Actor | UC 40: Buyer đã đăng nhập. Màn 67, 68: Admin |
| Trigger | Buyer nộp hồ sơ nâng cấp lên Seller; Admin mở hàng đợi duyệt |
| API endpoint | UC 40/67/68 không đăng ký endpoint. 3.4.1 đăng ký `PUT /api/seller/settings/brand` (hoặc `POST /api/seller/onboarding/shop`) |
| Input | Thông tin shop; giấy tờ định danh cá nhân hoặc doanh nghiệp (số định danh / mã số thuế); tài khoản ngân hàng |
| Output | Hồ sơ chờ Admin duyệt. Admin từ chối phải kèm lý do cụ thể (popup 68) |
| Xử lý | Hồ sơ "subject to Admin approval": **người quyết là Admin** |
| BR | Không có BR riêng cho KYC. Phần shop chịu BR-150 (tên 3–100 ký tự, không chứa từ dành riêng như admin, system, vietcraft), BR-151 (slug duy nhất, trùng thì thêm hậu tố số). BR-152..154 thuộc màn Shop Settings |
| Màn hình | 54 Register as Seller Page · 67 Seller Onboarding Queue Page · 68 Reject KYC Reason Popup |

**Rủi ro khi bảo vệ:** UI trình bày OCR và "kiểm định thật/giả" như chức năng chính, có huy hiệu "Hợp lệ". Hội đồng hỏi "mục nào?" thì không có câu trả lời, mà số liệu trên huy hiệu lại là giả (mục 1).

**Đề xuất:** nắn OCR về hai chức năng đã đăng ký. (1) UC 40: tự điền form từ ảnh, người dùng xác nhận. (2) Màn 67: bảng đối chiếu và cờ bất nhất giúp Admin duyệt. Không tự duyệt, không tự từ chối. Ghi phụ lục SRS "Hỗ trợ đọc CCCD (bổ sung)" kèm endpoint `/api/seller/kyc/*`.

## 1. Roast: code hiện tại thực chất là gì

**Bốn ô xanh là đồ vẽ.** Card "Báo cáo kiểm định ảnh thật/giả" (`FE:1745`) có 4 ô "✓ Đạt chuẩn", "✓ Chuẩn Quốc huy", "✓ Thẻ vật lý", "✓ Quy chuẩn BCA". Bốn ô đọc `checks.blur_check`, `layout_check`, `screen_capture_check`, `id_number_format` (`FE:1752-1775`). AI đéo trả key nào trong số đó. Nó trả `image_quality_ok`, `layout_detected`, `no_screen_capture`, `id_format_valid` (`service:475-484`). Key không có thì `?? true` lo nốt: ảnh con mèo cũng "✓ Thẻ vật lý". Không dòng code nào nhìn Quốc huy.

**Số "tin cậy" bịa.** `confidence = số check đạt / tổng` (`service:486-488`), là số từ 0 đến 1. FE in `Hợp lệ ({confidence_score}%)` (`FE:1592`), ra "Hợp lệ (0.67%)". Toast thì in `confidence_score || 95` (`FE:1029`): điểm 0 thì khoe "95% tin cậy". Bịa số trước mặt người dùng, vl.

**"Thật/giả" là đếm phiếu.** `is_likely_authentic = confidence >= 0.6 and layout` (`service:499`). Mặt trước có 6 check, đạt 4 là "thật". Ảnh chụp màn hình VÀ bị mờ vẫn "thật" nếu đọc ra số, tên, ngày sinh. Mặt sau có 3 check, chụp màn hình vẫn đạt 2/3.

**Layout giả qua dễ như đùa.** List từ khoá có "CĂN CƯỚC" hai lần (`service:148`, `:154`), so khớp substring (`:179-181`). Tao chạy thật: `["CĂN CƯỚC giả", "Số 1"]` → `is_layout_valid: True`. Mặt sau chỉ cần một dòng "Ngày 12 tháng 3 năm 2024": "Ngày", "tháng", "năm" là 3 từ khoá, ngưỡng là 2 (`:159`, `:183`).

**Chống chụp màn hình bằng một con số không đơn vị.** Lấy trung bình log phổ FFT của cả ảnh, > 5.5 là "chụp màn hình" (`service:125-137`). Phổ không chuẩn hoá nên số này tăng theo độ phân giải. Cùng một ảnh tổng hợp: 800×500 cho 5.27, phóng 2× cho 5.77 → thành "chụp màn hình". Ngưỡng 5.5 đéo được đo trên tập ảnh nào.

**AI chặn người tên Nam.** Parser cắt họ tên theo regex `Nam|Nữ` (`service:327`, `:334`). Chạy thật: "NGUYỄN VĂN NAM" → "NGUYỄN VĂN", "PHẠM HOÀI NAM ANH" → "PHẠM HOÀI". FE tự điền tên và chữ ký từ OCR (`FE:1010-1012`). BE bắt tên chủ tài khoản ngân hàng trùng tên khai (`kyc.svc:272-276`). Kết quả: người tên Nam bị chặn nộp hồ sơ vì "tên không khớp".

**Số CCCD có thể do regex đẻ ra.** Không thấy 12 số liền thì lấy 12 số đầu của chuỗi 9–14 số (`service:249-253`). Chạy thật: "0792000012345" (13 số) → trả "079200001234". Ngày "31/02/1990" vẫn được nhận (`:261-270`).

**Kết quả AI không đi đâu cả.** FE không gửi `verification` khi nộp (`FE:1124-1145`). BE không lưu, không so số CCCD khai với OCR, chỉ kiểm `length < 9` (`kyc.svc:220-223`). Admin mở hồ sơ không thấy kết quả OCR nào (`admin.service.ts:254-303`). Cả lớp "AI" là sân khấu.

**Kiểm tra chân dung là `setTimeout`.** FE hiện "Đang kiểm tra..." đúng 800ms rồi tắt (`FE:1088-1091`), không gọi API nào. BE có route `validate-portrait` gọi `/api/v1/portrait/validate` (`kyc.svc:505`), nhưng AI không có route đó.

**Bảo mật và pháp lý.**
- Endpoint AI không xác thực (`ocr.py:22-26`). BE gọi không kèm `X-Gateway-Secret` (`kyc.svc:465-469`).
- `/scan-cccd` không kiểm file thuộc ai (`kyc.router:134-145`). Biết tên file là lấy được họ tên, số CCCD, ngày sinh của người khác.
- Bỏ qua OTP chỉ cần body có `phone_verified` (`kyc.svc:210`), và FE luôn gửi `phone_verified: true` (`FE:1128`). Bước OTP để trang trí, ngáo thật sự.
- Code còn trích NĐ 13/2023 (`kyc.router:87`, `kyc.svc:283`). Từ 01/01/2026 khung pháp lý là Luật Bảo vệ dữ liệu cá nhân 91/2025/QH15 và NĐ 356/2025/NĐ-CP. NĐ 356 xếp **hình ảnh thẻ căn cước** vào danh mục dữ liệu cá nhân nhạy cảm (theo trang phổ biến pháp luật Cần Thơ; cần xác minh số điều trên văn bản gốc).
- Ảnh đó đang nằm thô trên đĩa, không hạn xoá. `.dockerignore` không loại `storage/`, nên `COPY . .` (`BE/Dockerfile:9`) nhét luôn ảnh KYC trên máy build vào image.

### Lệch bản đăng ký
- OCR và "thật/giả" **không có trong SRS** nhưng được trình bày như chức năng chính (`FE:1745`).
- Màn 67 yêu cầu Admin xem "identity verification information". Admin không thấy kết quả đối chiếu nào, nên OCR không phục vụ chức năng đã đăng ký.
- 9 route `/api/seller/kyc/*` (`kyc.router:13-155`) đều không có trong SRS.
- BR-150 không được áp ở `/apply`: chỉ kiểm tên shop không rỗng (`kyc.svc:250-251`).

## 2. Mổ xẻ lỗi

| # | Mức | Chỗ | Lỗi | Hậu quả | Sửa nhanh |
|---|---|---|---|---|---|
| 1 | Chết người | `FE:1752-1775` | 4 ô kiểm định đọc key không tồn tại, mặc định `true` | Luôn hiện "✓ Thẻ vật lý", "✓ Chuẩn Quốc huy" | Xoá 4 ô hoặc map đúng key; không có dữ liệu thì không hiện |
| 2 | Chết người | `FE:1029`, `:1592`, `:1654` | In số 0–1 thành %, mặc định 95% | "Hợp lệ (0.67%)", "95% tin cậy" bịa | Bỏ hiển thị % |
| 3 | Chết người | `FE:1088-1091` | "Đang kiểm tra" chân dung là `setTimeout` | Nói dối người dùng | Xoá; route AI không tồn tại (`kyc.svc:505`) |
| 4 | Chết người | `kyc.svc:210`, `FE:1128` | Client tự khai `phone_verified` | Bỏ qua OTP hoàn toàn | Chỉ tin `user.is_phone_verified` phía server |
| 5 | Chết người | `kyc.router:134-145`, `kyc.svc:444-447` | `/scan-cccd` không kiểm chủ file | IDOR lộ PII CCCD (UUID khó đoán nhưng vẫn thiếu kiểm quyền) | Lưu `owner_id` cho mỗi upload, kiểm trước khi đọc |
| 6 | Chết người | `kyc.svc:226-228`, `:314-316` | `/apply` nhận tên file bất kỳ | Gắn ảnh CCCD người khác vào hồ sơ mình | Như #5 |
| 7 | Chết người | `ocr.py:22-26`, `kyc.svc:465-469` | AI không xác thực | Ai tới được cổng 8000 cũng gọi được, DoS | Dependency kiểm `X-Gateway-Secret` như `_template.py:204-216` |
| 8 | Nặng (SRS) | `FE:1745` | Tính năng ngoài đăng ký trình bày như chính | Hội đồng bắt lỗi | Ghi phụ lục; nắn về UC 40/67 |
| 9 | Nặng (SRS) | `admin.service.ts:254-303` | Admin (màn 67) không thấy OCR | OCR không giúp gì chức năng đã đăng ký | Lưu kết quả đối chiếu, hiện ở màn 67 |
| 10 | Nặng (SRS) | `kyc.svc:250-251` | Không áp BR-150 cho tên shop | Lệch BR | Kiểm 3–100 ký tự và từ dành riêng |
| 11 | Nặng | `service:499` | "Thật" = 4/6 check, không cần qua kiểm màn hình | Ảnh chụp màn hình được coi là thật | Bỏ khái niệm "thật"; chỉ báo cờ |
| 12 | Nặng | `service:148`, `:154`, `:159`, `:179-183` | Từ khoá trùng, substring, ngưỡng thấp | Giấy có chữ "Ngày tháng năm" qua layout | Template vùng trường + nhận diện phiên bản thẻ |
| 13 | Nặng | `service:125-137` | Ngưỡng FFT phụ thuộc độ phân giải | Ảnh nét, độ phân giải cao bị gắn cờ oan | Resize trước; đo trên tập có nhãn |
| 14 | Nặng | `service:327`, `:334` | Regex cắt "Nam", "Nữ" trong họ tên | Tên sai, chặn hồ sơ ở bước so tên ngân hàng | Dừng theo nhãn trường, không theo chữ |
| 15 | Nặng | `service:249-253` | Cắt chuỗi 13–14 số thành 12 | Bịa số CCCD | Không đủ đúng 12 số thì trả null |
| 16 | Nặng | `service:57-76` | Không đối chiếu chữ số thứ 4–6 với ngày sinh, giới tính | Sửa ngày sinh vụng vẫn qua | Thêm luật nhất quán (mục 4.3) |
| 17 | Nặng | `service:147-170`, `:360-373`, `:393-429` | Parser chỉ biết nhãn CCCD cũ | Thẻ căn cước 2024 (TT 16/2024: nơi cư trú, ngày cấp, hạn, QR, MRZ ở mặt sau) thiếu trường | Nhận diện phiên bản, template riêng |
| 18 | Nặng | `kyc.svc:220-223` | BE chỉ kiểm số CCCD dài ≥ 9 | Số rác lọt | Kiểm 12 số và luật cấu trúc |
| 19 | Nặng | `kyc-storage.middleware.ts:7`, `BE/.dockerignore` | Ảnh thô trên đĩa, không volume, không loại khỏi image | Lộ ảnh vào image; mất ảnh khi redeploy | Thêm `storage/` vào .dockerignore; volume riêng; mã hoá file |
| 20 | Nặng | `crypto.service.ts:4-6`, `:31`, `:128` | Khoá rơi về JWT secret (mặc định rỗng); CBC không MAC; nhận cả plaintext | Một bí mật lộ là lộ hết | Khoá riêng bắt buộc; AES-256-GCM |
| 21 | Nặng | `kyc.svc:366`, `:395-397` | Không xoá upload mồ côi, ảnh cũ khi nộp lại, ảnh sau khi duyệt | Giữ dữ liệu nhạy cảm vô thời hạn | Job xoá theo thời hạn (mục 4.5) |
| 22 | Nặng | `ocr.py:23`, `:61` | `async def` chạy OCR đồng bộ | Treo cả AI service 5–15s mỗi request | `def` (threadpool) và semaphore |
| 23 | Vừa | `ocr.py:34-35`, `service:446-447` | Tin content-type của client; decode mọi định dạng; không giới hạn pixel | Decompression bomb: OpenCV mặc định cho tới 2^30 pixel, FFT trên ảnh full | Kiểm magic bytes, kích thước header, giới hạn MP, resize |
| 24 | Vừa | `kyc.svc:135`, `:138`, `:382` | Log OTP, SĐT, email dạng thô | PII và bí mật trong log | Bỏ OTP, che SĐT và email |
| 25 | Vừa | `Dockerfile:10`, `easyocr/config.py:30-33`, `:156` | Cài torch chỉ cho EasyOCR; "vi" dùng model `latin_g2` chung ~40 ngôn ngữ; tải model từ GitHub lúc chạy | Image nặng; request đầu chậm, phụ thuộc mạng | Đổi sang ONNX (mục 4.3), gỡ torch |
| 26 | Vừa | `kyc.router:77`, `kyc.svc:116` | IP đồng ý lấy từ `x-forwarded-for` thô; OTP sinh bằng `Math.random`, không giới hạn tần suất | Bằng chứng đồng ý giả được; tốn tiền SMS | `req.ip` với trust proxy; `crypto.randomInt`; rate limit |
| 27 | Nhẹ | `tests/` | Không có test nào cho CCCD | Mọi lỗi trên không ai thấy | Bộ sanity ở mục 4.2 |

## 3. Tính năng này nên là AI gì

Seller cần điền nhanh, ít sai, không bị chặn oan. Admin (màn 67) cần biết hồ sơ nào phải nhìn kỹ. Tách làm ba bài toán, chỉ một bài là ML thật:

| Bài toán | Loại | Đầu vào | Đầu ra | Nhãn |
|---|---|---|---|---|
| Trích xuất trường | ML (nhận dạng chữ) + hình học | Ảnh mặt trước, mặt sau | Số định danh, họ tên, ngày sinh, giới tính, quốc tịch, nơi cư trú, ngày cấp, ngày hết hạn, kèm độ tin cậy từng trường | Giá trị đúng, gán tay hoặc lấy từ giá trị người dùng xác nhận |
| Kiểm tra nhất quán | Luật, **không phải ML** | Trường OCR, QR, MRZ, dữ liệu khai | Danh sách cờ bất nhất | Không cần |
| Phát hiện ảnh tấn công (PAD) | ML phân loại | Ảnh đã nắn | Điểm nghi ngờ theo loại tấn công | Ảnh thật / ảnh tấn công tự tạo có đồng ý |

Kết luận trung thực:
- Không hệ thống nào ở đây nói được thẻ **thật hay giả**. Xác thực thật cần đọc chip NFC kèm kiểm chữ ký số của chip (passive authentication theo ICAO 9303, cần app di động), hoặc tích hợp dịch vụ xác thực của Bộ Công an (điều kiện pháp lý cần xác minh). Cả hai đều ngoài phạm vi đồ án.
- Thứ làm được là **cờ cho Admin**: "số định danh không khớp ngày sinh", "MRZ sai chữ số kiểm tra", "nghi chụp lại từ màn hình". Admin quyết theo UC 40/67/68.
- Hợp đồng giữ nguyên: Buyer nộp hồ sơ, Admin duyệt hoặc từ chối kèm lý do. AI chỉ nằm bên dưới.

## 4. Đường ra: thiết kế AI chính hiệu

### 4.1 Dữ liệu: train / validation / test / thực
Không tìm được bộ ảnh CCCD Việt Nam công khai có giấy phép rõ (chưa kiểm được nguồn nào). Ảnh thẻ căn cước lại là dữ liệu nhạy cảm theo NĐ 356/2025 (cần xác minh). Vì vậy tự tạo, có đồng ý bằng văn bản:

| Tập | Nội dung | Ghi chú |
|---|---|---|
| A. Ảnh thật | Thẻ của thành viên nhóm và người thân đồng ý; mỗi thẻ chụp bằng 2–3 điện thoại × 3 điều kiện sáng × 2 góc | Gán nhãn trường bằng tay, 2 người đối soát |
| B. Ảnh tấn công | Từ chính thẻ ở tập A: chụp lại trên màn hình điện thoại/laptop, in màu, photocopy, sửa số/tên bằng phần mềm, ghép ảnh mặt | Mỗi loại là một "loài công cụ tấn công" riêng |
| C. Không phải CCCD | Thẻ sinh viên, bằng lái, giấy có chữ "Ngày … tháng … năm" | Đo tỉ lệ nhận nhầm layout |
| D. Dòng chữ tổng hợp | Render tên, địa chỉ tiếng Việt bằng font gần giống | Chỉ đo CER phần nhận dạng. **Không dựng ảnh thẻ hoàn chỉnh** (rủi ro làm giả giấy tờ, cần xác minh) |

- Chia theo **người** (GroupShuffleSplit theo `person_id`, tái dùng cách chia của Listing Intel) để ảnh của cùng một thẻ không rơi vào cả hai phía. Báo kết quả tách theo phiên bản thẻ: CCCD 2016, CCCD gắn chip 2021, thẻ căn cước 2024.
- Test khoá, ghi số lần đọc test như LI.
- Lưu trữ tập: máy của nhóm, mã hoá ổ, không đẩy git, xoá sau bảo vệ, có biên bản đồng ý.
- Dữ liệu thật VietCraft (16 shop, 79 sản phẩm) chưa đủ để đo. Chỉ dùng cho theo dõi ở 4.4.

### 4.2 Làm sạch và sanity
Ranh giới tin cậy (BE nhận file, AI decode):
- Kiểm magic bytes (JPEG/PNG/WebP thật), không tin `mimetype` của client.
- Đọc kích thước từ header (Pillow `Image.open` chưa decode). Từ chối ảnh vượt khoảng 25MP trước khi `imdecode`.
- Re-encode sang JPEG sạch và bỏ EXIF (có thể chứa GPS) trước khi lưu. Bước này cũng phá file polyglot.
- PDF chỉ dành cho giấy phép kinh doanh. Render trang 1 sang ảnh rồi bỏ file gốc, hoặc không nhận PDF.

Tiền xử lý:
- Resize cạnh dài về kích thước cố định (ví dụ 1600px) trước mọi đặc trưng, để ngưỡng không phụ thuộc độ phân giải.
- Tìm tứ giác thẻ (Canny, contour, `approxPolyDP` của OpenCV có sẵn), `warpPerspective` về tỉ lệ thẻ ID-1 (85.60 × 53.98 mm).
- Nhận diện phiên bản thẻ trước khi đọc trường. Chuẩn hoá NFC cho mọi chuỗi trước khi so.

Sanity bắt buộc (pytest, chạy CI):
- Phóng ảnh 0.5× và 2× thì quyết định không đổi.
- Họ tên chứa NAM, NỮ, ANH phải giữ nguyên.
- 13 chữ số → null; "31/02/1990" → ngày không hợp lệ.
- `["CĂN CƯỚC giả", "Số 1"]` và "Ngày 12 tháng 3 năm 2024" → không hợp lệ.
- Ảnh trắng, ảnh đen, ảnh 1×1 → lỗi rõ ràng, không 500.

### 4.3 Model
Baseline: pipeline hiện tại (EasyOCR + regex + ngưỡng cứng). **Đo nó trước**, đó là mốc phải thắng.

Model chính (CPU, không torch):
1. **Nắn thẻ:** hình học OpenCV, không cần ML. Chỉ thêm model phát hiện nếu tỉ lệ nắn hỏng trên tập A vượt ngưỡng.
2. **Cắt vùng trường (ROI)** theo template từng phiên bản thẻ.
3. **Nhận dạng dòng chữ**, chọn bằng benchmark CER:
   - VietOCR (repo `pbcquoc/vietocr`, Apache-2.0, đã kiểm). Không có bản ONNX chính thức; có bài hướng dẫn export trên Viblo. Phải tự export và so output với bản gốc.
   - RapidOCR (ONNX chuyển từ PaddleOCR, README ghi Apache-2.0). Cần kiểm có model nhận dạng tiếng Việt có dấu không.
4. **Đọc mã máy, ưu tiên hơn OCR:**
   - QR: `cv2.QRCodeDetector` (OpenCV có sẵn). Theo trả lời của Bộ Công an đăng trên VnExpress, QR trên thẻ gắn chip lưu 7 trường, gồm cả số CMND cũ.
   - MRZ mặt sau: theo báo chí là chuẩn ICAO. Thẻ cỡ ID-1 nên nhiều khả năng là dạng TD1, 3 dòng × 30 ký tự (cần xác minh trên thẻ mẫu). Kiểm chữ số kiểm tra trọng số 7-3-1 rồi so với trường mặt trước.
5. **Luật nhất quán:**
   - Mã tỉnh nằm trong danh mục 63 mã (`service:22-30` đã có).
   - Chữ số thứ 4 khớp giới tính và thế kỷ: 0/1 là nam/nữ sinh 1900–1999, 2/3 là nam/nữ sinh 2000–2099 (theo các trang pháp luật dẫn TT 59/2021/TT-BCA; cần xác minh văn bản gốc). Chữ số 5–6 bằng hai số cuối năm sinh.
   - Ngày hợp lệ. Ngày hết hạn sau ngày cấp.
   - QR, MRZ, OCR và dữ liệu người dùng khai phải khớp nhau.
6. **PAD:**
   - Baseline: đặc trưng thủ công hiện có (Laplacian, FFT), tính lại sau khi resize.
   - Model: logistic regression trên đặc trưng phổ theo dải tần (tìm đỉnh moiré chứ không lấy trung bình), vùng lóa, gam màu, nối với embedding ảnh SigLIP2 ONNX 768 chiều đã có trong Listing Intel.
   - Chỉ giữ model nếu thắng baseline có ý nghĩa (mục 4.6).
7. **Hạ tầng:** bỏ EasyOCR thì gỡ được torch khỏi `Dockerfile:10`, khớp ràng buộc server. Endpoint chạy `def` trong threadpool, tối đa 1–2 job OCR đồng thời.

### 4.4 Học từ dữ liệu thật
- **Nhãn miễn phí:** giá trị người dùng nộp sau khi sửa chính là nhãn cho output OCR. Chỉ lưu cờ đúng/sai và CER theo từng trường, kèm phiên bản thẻ và phiên bản model. Không lưu giá trị.
- **Quyết định Admin** (duyệt / từ chối kèm lý do, màn 68) là nhãn yếu cho cờ. Lưu thêm "Admin có đồng ý với cờ không".
- **Cold start:** chưa có hồ sơ thật thì dùng tập A–D. Ngưỡng PAD đặt ở BPCER ≤ 5% để không làm phiền người thật, và chỉ hiện cờ cho Admin.
- **Drift:** theo dõi theo tuần tỉ lệ trường bị người dùng sửa, tách theo phiên bản thẻ (thẻ căn cước 2024 sẽ tăng dần), và tỉ lệ đọc được QR/MRZ.
- **Không huấn luyện lại OCR bằng ảnh người dùng** khi đồng ý chưa nêu mục đích huấn luyện (nguyên tắc mục đích theo Luật 91/2025, cần xác minh). Chỉ chỉnh ngưỡng và template.

### 4.5 Bảo mật và chống gian lận

| Mối đe doạ | Hiện trạng | Biện pháp | Kiểm chứng |
|---|---|---|---|
| Gọi AI trực tiếp, DoS | Không xác thực, OCR chặn event loop (`ocr.py:22-26`, `:61`) | `X-Gateway-Secret` bắt buộc; không mở cổng 8000 ra ngoài; `def` và semaphore | Không có secret → 401; 5 request song song không treo `/health` |
| IDOR file KYC | `/scan-cccd`, `/apply` nhận tên file bất kỳ | Bảng upload `{filename, user_id, kind, created_at}`; scan, apply, files đều kiểm chủ | User B quét file của A → 404 |
| Lộ URL xem ảnh | Token 1 giờ, không gắn user, khoá HMAC dùng chung JWT secret (`kyc.router:58`, `crypto.service.ts:128`) | Khoá HMAC riêng, thiếu thì không khởi động; payload gắn user/role; TTL 5 phút; `Cache-Control: no-store`, `Referrer-Policy: no-referrer` | Token của A dùng với JWT của B → 403 |
| Mã hoá lưu trữ | Ảnh thô; tên, ngày sinh thô; CBC không MAC | AES-256-GCM cho file ảnh và các trường định danh, khoá riêng | Mở file trên đĩa không ra ảnh |
| Thời hạn xoá | Không có job nào | Xoá upload mồ côi sau 24 giờ; xoá ảnh hồ sơ bị từ chối khi hết hạn sửa; sau duyệt giữ theo nghĩa vụ lưu thông tin người bán của sàn TMĐT (cần xác minh) rồi xoá ảnh, giữ bản che | Test job trên dữ liệu giả |
| Log chứa PII | OTP, SĐT, email (`kyc.svc:135`, `:138`, `:382`); AI chỉ log side/size/type (`ocr.py:58`, tốt) | Bỏ OTP khỏi log, che SĐT và email; giữ cách log của AI | grep log sau bộ test: không có 12 số liền, không có OTP |
| Bên thứ ba | OCR chạy local, không gửi ảnh ra ngoài (tốt); model EasyOCR tải từ GitHub lúc chạy | Tải model lúc build, kiểm checksum. Không gửi ảnh CCCD cho Gemini hay API ngoài | Chạy offline vẫn quét được |
| Upload độc | Tin mimetype; decode mọi định dạng; không giới hạn pixel; không có `nosniff` (BE không dùng helmet, `app.ts:13` chỉ tắt `x-powered-by`) | Như 4.2; thêm `X-Content-Type-Options: nosniff`, `Content-Disposition: attachment` cho `/files` | PNG 30000×30000 bị từ chối trước khi decode; polyglot JPEG+ZIP lưu ra là JPEG sạch |
| Ảnh chụp màn hình, in lại | Ngưỡng cứng không đo | PAD đo APCER/BPCER; chỉ báo cờ | Bảng 4.6 |
| Ảnh chỉnh sửa | Không bắt | Luật nhất quán số ↔ ngày sinh/giới tính, MRZ, QR. Nói thẳng: sửa đồng bộ cả MRZ và QR thì không bắt được nếu không đọc chip | Tập B loại "sửa số" |
| OTP | Client tự khai; không giới hạn tần suất | Bỏ `payload.phone_verified`; rate limit theo user, SĐT, IP; `crypto.randomInt` | Gửi `phone_verified: true` mà chưa OTP → 400 |
| Đồng ý xử lý dữ liệu | Trích NĐ 13/2023 đã hết hiệu lực | Cập nhật căn cứ Luật 91/2025 và NĐ 356/2025; nói rõ ảnh căn cước là dữ liệu nhạy cảm và nêu mục đích (cần xác minh điều khoản) | Rà nội dung màn đồng ý |

### 4.6 Benchmark và kiểm chứng
Metric:
- **Trích xuất:** exact match theo trường (sau NFC và viết hoa) cho số định danh, họ tên, ngày sinh, giới tính, ngày cấp, ngày hết hạn; CER cho họ tên và nơi cư trú; tỉ lệ ảnh đúng tất cả trường; tỉ lệ từ chối (không trả trường); latency p50/p95 trên CPU. Tách theo phiên bản thẻ.
- **Nhất quán:** trên ảnh sửa có kiểm soát, tỉ lệ bắt được theo từng loại sửa.
- **PAD:** APCER theo từng loại công cụ tấn công (màn hình, in, photocopy, sửa số) và BPCER trên ảnh thật. Báo cả APCER của loại tệ nhất. Thuật ngữ theo ISO/IEC 30107-3; định nghĩa lấy từ nguồn thứ cấp, cần đối chiếu bản ISO.

Cách tính:
- CI Clopper-Pearson cho tỉ lệ. Bootstrap theo cụm **người** (tái dùng bootstrap cụm của LI) vì nhiều ảnh cùng một thẻ.
- Paired bootstrap so với baseline trên cùng ảnh.
- Sanity: xáo nhãn PAD → AUC ≈ 0.5; resize-invariance; tập C không qua layout.

Cổng "đạt khi" (đề xuất, chốt lại sau khi đo baseline):
- N tối thiểu: ≥ 10 thẻ, ≥ 100 ảnh thật. Ít hơn thì chỉ báo số đếm, không báo phần trăm.
- Số định danh exact ≥ 98% trên ảnh rõ. Họ tên CER ≤ 2%. Cả hai thắng baseline với CI paired không chứa 0.
- Cờ PAD chỉ hiện cho Admin khi APCER(màn hình) có cận trên CI ≤ 30% ở BPCER ≤ 5%. Không đạt thì ẩn cờ PAD, chỉ giữ cờ nhất quán.
- Không thắng baseline thì giữ baseline, công bố số thật, và tắt mọi chữ "thật/giả" trên UI.

## 5. Lộ trình

| Giai đoạn | Việc | Kết quả kiểm chứng |
|---|---|---|
| Ngay 1–2 ngày | Xoá 4 ô kiểm định giả, % sai, toast 95%, `setTimeout` chân dung; đổi "Hợp lệ" thành "Không có cờ / Cần Admin xem". Bỏ bypass `phone_verified`. Kiểm chủ file cho scan/apply/files. Gateway secret cho AI. Thêm `storage/` vào .dockerignore. Sửa regex tên Nam, cắt 13 số, `async def`. Bỏ OTP khỏi log | pytest sanity 4.2 xanh; curl: không secret → 401, file người khác → 404, `phone_verified` giả → 400 |
| 1–2 tuần | Thu tập A–D có biên bản đồng ý; đo baseline. Pipeline nắn + ROI + VietOCR hoặc RapidOCR ONNX; QR, MRZ, luật nhất quán. Bảng đối chiếu ở màn 67. Gỡ torch. Mã hoá GCM, job xoá, rate limit OTP | Bảng metric theo phiên bản thẻ, có CI, so baseline; image Docker không còn torch |
| Khi có hồ sơ thật | Telemetry đúng/sai theo trường; theo dõi drift; Admin đánh giá cờ; chỉnh ngưỡng | Báo cáo tháng: tỉ lệ sửa theo trường, tỉ lệ Admin đồng ý với cờ |

**Xong khi:**
- Không còn số hay huy hiệu nào trên UI mà không có nguồn đo.
- Mục 4.5 có test tự động cho IDOR, gateway, OTP, upload quá cỡ.
- Có bảng benchmark trên ≥ 100 ảnh có đồng ý, kèm CI và so baseline.
- Khớp UC 40 và màn 54, 67, 68 (Admin là người quyết; từ chối bắt buộc có lý do, đã có ở `admin.service.ts:412-415`). Khớp BR-150, BR-151 của mục SRS 3.4.1 cho phần thông tin shop trong hồ sơ. BR-152, BR-153, BR-154 thuộc màn Shop Settings, không áp cho luồng này.
- OCR được ghi vào phụ lục SRS như tính năng bổ sung hỗ trợ UC 40/67, có endpoint `/api/seller/kyc/scan-cccd`, và không tự quyết.

## 6. Hội đồng sẽ hỏi

1. **"OCR CCCD nằm ở mục nào trong SRS?"** Không có. Nhóm ghi vào phụ lục như lớp hỗ trợ cho UC 40 (tự điền, người dùng xác nhận) và màn 67 (cờ cho Admin). Admin vẫn là người quyết.
2. **"Hệ thống phát hiện CCCD giả chính xác bao nhiêu?"** Bản cũ không đo, và huy hiệu là giả, đã gỡ. Bản mới chỉ báo cờ nhất quán và cờ nghi chụp lại, với APCER/BPCER đo trên N ảnh có đồng ý. Thẻ giả mạo kỹ thì không bắt được nếu không đọc chip.
3. **"Lấy ảnh CCCD ở đâu để test, có hợp pháp không?"** Thẻ của thành viên và người thân, có biên bản đồng ý. Không dùng ảnh trên mạng, không dựng thẻ giả. Lưu mã hoá, xoá sau bảo vệ.
4. **"Ảnh CCCD của seller lưu bao lâu, ai xem được?"** Chỉ Admin và chủ hồ sơ, qua link ký 5 phút. Upload mồ côi xoá sau 24 giờ. Hồ sơ bị từ chối xoá khi hết hạn sửa. Thời hạn sau duyệt theo nghĩa vụ pháp lý (đang xác minh).
5. **"Sao không gọi Google Vision hay LLM cho nhanh?"** Gửi ảnh căn cước, một loại dữ liệu nhạy cảm, ra bên thứ ba cần căn cứ pháp lý riêng. Model local ONNX đủ đo được, và benchmark so trực tiếp với EasyOCR cũ.
