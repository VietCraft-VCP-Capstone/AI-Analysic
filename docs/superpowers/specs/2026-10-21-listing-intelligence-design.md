# Listing Intelligence (F29 v2): thiết kế

Ngày: 2026-10-21 · Hạn chạy được và có báo cáo: 2026-10-22 · Phạm vi: AI-Analysic, BE, FE

## 1. Mục tiêu

Chấm một listing trên sàn VietCraft (sàn Việt Nam) bằng dữ liệu và mô hình học từ TMĐT Việt Nam, không chỉ bằng checklist. Kết quả gồm một điểm tổng, 5 điểm trục, lời khuyên có mức chứng cứ, và điểm thay đổi theo trend và thời điểm trong năm.

Thành công khi:

1. Có đủ 4 bộ dữ liệu cho báo cáo: train, validation, test (tách theo shop) và test lệch thời gian, cùng baseline và kết quả trên dữ liệu thật của sàn.
2. Model tổng thắng baseline mạnh nhất trên test, và khoảng tin cậy bootstrap theo shop của phần chênh không chứa 0. Nếu không thắng, báo cáo nói thẳng và scorer không gắn nhãn "đã đo".
3. Mỗi trục có ablation. Lời khuyên chỉ gắn nhãn "đã đo" khi trục đó có mức giảm AUC khi bỏ ra ≥ 0,005 và khoảng tin cậy không chứa 0.
4. Trend: dự báo 8 tuần có MASE < 1 so với seasonal naive trên phần lớn từ khoá đủ điều kiện. Sanity check: listing có từ khoá theo dịp phải đạt đỉnh điểm ở tuần trước dịp.
5. Endpoint chạy được trên stack local (Mongo local `vietcraft-test`), FE hiển thị đủ, chấm thử bản nháp 3 ảnh dưới 3 giây sau khi model đã nạp.
6. `docs/LISTING_INTEL_REPORT.md` có kết quả, drawback, sanity check, điểm yếu, phần bị ảnh hưởng; các điểm yếu sửa được đã sửa và đo lại.

## 2. Phạm vi

Trong phạm vi: 5 trục (ảnh, từ khoá, tag, thị hiếu và cạnh tranh, trend và mùa vụ), trường `materials` ở BE và FE, endpoint chấm listing đã đăng, chấm thử bản nháp, danh sách theo shop, lịch trend; job đêm và job tuần; trang FE "Phân tích listing" và nút chấm thử trong form tạo sản phẩm; báo cáo.

Ngoài phạm vi: viết lại F42 gợi ý giá, model uy tín shop, tự crawl Tiki (IP máy bị chặn), dùng LLM để chấm điểm, GPU hoặc torch trong module mới.

## 3. Dữ liệu

Mọi dữ liệu ngoài lưu ở `vietcraft/data-li/` (ngoài 3 repo git) và Mongo local DB `li-research`. Chỉ dùng cho học thuật, không phân phối lại, không commit CSV hay ảnh.

| Tên trong code | Nguồn | Số dòng | Vai trò |
|---|---|---|---|
| `tiki23` | Kaggle `michaelminhpham/vietnamese-tiki-e-commerce-dataset` | 41.603 | Train và validation cho model chữ, giá, metadata |
| `tiki26` | Kaggle `huyhoang1308/tiki-csv` (Apache-2.0, crawl 2026-04-18) | 8.169 | Train, validation, test cho model đủ trục (có thumbnail) và test lệch thời gian |
| `tikifashion` | Kaggle `giaphoangkim/tiki-fashion` | 22.334 | Hiệu chỉnh độ khớp ảnh–tiêu đề và nhận diện danh mục từ ảnh (lấy mẫu 5.000 ảnh) |
| `tikireviews` | Kaggle `farmingfree/vietnamese-e-commerce-suspicious-reviews-dataset` | 584.005 | Mùa vụ mua hàng theo tháng 2020–2024 |
| `trends` | Mongo `data-collection.trend_interest` + collector sẵn có, thêm từ khoá mới | 45 → khoảng 100 chuỗi | Mức quan tâm, đà tăng, chỉ số mùa, dự báo |
| `vietcraft` | Mongo local `vietcraft-test` | 29 sản phẩm, 16 có ảnh | Chạy thật, đo độ phủ và lệch phân phối |

Nhãn: `top25` = listing thuộc 25% `quantity_sold` cao nhất trong nhóm danh mục; với `tiki23` dùng `quantity_sold / max(tuổi_ngày, 30)` vì có tuổi listing. `review_count`, `rating_average`, `favourite_count`, `order_count`, `revenue_estimate` bị loại khỏi feature vì là đáp án hoặc suy ra từ đáp án.

Chia tập: `GroupShuffleSplit` theo shop (`current_seller`, nếu thiếu thì `brand`), 70/15/15, cố định seed. Test lệch thời gian: model chữ học trên `tiki23`, chấm trên `tiki26`.

Ánh xạ danh mục VietCraft sang nhóm Tiki nằm trong `app/core/listing_intel/data/category_map.json` (ví dụ Áo thun, Áo khoác → thời trang; Túi → túi xách; Giày dép → giày; Phụ kiện → phụ kiện thời trang; Trang trí, Ly tách, Nhà cửa, Tranh ảnh → đồ gia dụng).

## 4. Kiến trúc

```
FE (trang Phân tích listing, form tạo sản phẩm)
  → BE /api/seller/analytics/... (xác thực, chọn shop, kiểm tra body)
    → AI /api/analytics/listings/.../intel
       listing_intel: normalize, lexicon, embedder, vision, text_axis, tags_axis,
                      market_axis, trend_axis, fusion, advice, store
       → Mongo live (products, variants, tags, categories, listing_embeddings, listing_intel_scores)
       → Mongo data-collection (trend_interest)
       → model bundle app/core/listing_intel/model/ (joblib + json + reference parquet nhỏ)
Offline: scripts/li/ (tải, làm sạch, embed, train, đánh giá, sinh báo cáo)
```

Ranh giới:

- `embedder` là chỗ duy nhất biết ONNX. Đầu vào: list ảnh PIL hoặc list chuỗi. Đầu ra: ma trận float32 đã chuẩn hoá L2.
- `vision` không biết Mongo; nhận bytes ảnh, trả số đo.
- Mỗi `*_axis` nhận một `ListingInput` (title, description, tags, materials, category, price, image_urls) và ngữ cảnh tham chiếu, trả `AxisResult` (điểm 0–100 hoặc None, số đo, vấn đề, lý do thiếu).
- `fusion` ghép feature từ các trục, chạy model, quy ra phân vị.
- `advice` chỉ đọc `AxisResult` và bảng ablation trong model bundle.
- `store` là chỗ duy nhất ghi Mongo.

Scripts offline gọi đúng các hàm feature này, nên train và chạy thật dùng chung một đường tính feature.

## 5. Các trục và cách tính điểm

**Ảnh.**
- Số đo kỹ thuật bằng OpenCV:
  - kích thước, tỉ lệ khung;
  - độ nét (phương sai Laplacian);
  - độ sáng, tương phản;
  - tỉ lệ viền nền đồng màu;
  - mật độ cạnh vùng giữa (thay cho độ chiếm khung);
  - ước lượng chữ đè ảnh bằng MSER;
  - perceptual hash để bắt ảnh trùng.
- Số đo ngữ nghĩa bằng SigLIP2 (`onnx-community/siglip2-base-patch16-224`, int8):
  - độ khớp ảnh–tiêu đề;
  - độ khớp ảnh–danh mục (zero-shot với câu mô tả tiếng Việt);
  - kiểu ảnh: nền trắng, lifestyle có người, flat lay, cận chất liệu;
  - độ đa dạng giữa các ảnh.
- Điểm trục là phân vị của model chỉ dùng feature ảnh, học trên `tiki26`.

**Từ khoá.**
- Chuẩn hoá NFC, chữ thường, bản bỏ dấu để so khớp.
- Độ dài; tỉ lệ từ lặp (nhồi từ khoá); từ bị cấm (bộ 87 cụm sẵn có, chuyển sang Python); viết hoa toàn bộ.
- Thuộc tính có hoặc thiếu: chất liệu, màu, size, dịp, công dụng.
- Điểm từ khoá bán chạy: tổng log-lift của các n-gram trong tiêu đề, học từ tiêu đề `tiki23` theo nhóm danh mục, chỉ dùng tập train.
- Độ quan tâm trend của các từ khoá khớp.
- Điểm trục là phân vị của model chỉ dùng feature chữ.

**Tag.** Tiki không có tag, nên mỗi tag được coi như một cụm từ khoá:
- lift bán chạy (cùng bảng với trục từ khoá);
- độ quan tâm trend;
- độ khớp ngữ nghĩa với ảnh và tiêu đề;
- tag trùng hoặc gần trùng, tag đang chờ duyệt;
- phủ đủ các nhóm thuộc tính (chất liệu, phong cách, dịp).

Điểm trục là công thức minh bạch, chuẩn hoá thành phân vị so với các listing VietCraft cùng nhóm. Báo cáo ghi rõ trục này không được học có giám sát.

**Thị hiếu và cạnh tranh.** Chỉ mục láng giềng gần dùng vector ảnh cộng tiêu đề của `tiki26` và VietCraft, chia theo nhóm danh mục:
- phân vị giá so với 20 láng giềng gần nhất;
- số listing gần như trùng (cos > 0,92);
- khoảng cách tới tâm nhóm bán chạy (top25) so với tâm nhóm còn lại.

Điểm trục là phân vị của model chỉ dùng các feature này.

**Trend và mùa vụ (thay đổi theo ngày `d`).**
- Mỗi listing ghép với từ khoá trend bằng so khớp chữ trước, nếu không có thì dùng độ tương đồng vector ≥ ngưỡng hiệu chỉnh.
- Với mỗi từ khoá:
  - mức hiện tại (phân vị trong 52 tuần);
  - đà tăng (4 tuần gần so với 4 tuần trước);
  - chỉ số mùa theo tuần trong năm (STL trên chuỗi tuần 5 năm);
  - dự báo 8 tuần (chọn giữa seasonal naive và STL theo backtest).
- Lịch sự kiện mở rộng `calendar_vn.py`: Tết âm lịch, Trung thu (rằm tháng 8 âm lịch, bảng 2021–2030), 14/2, 8/3, 30/4, 1/6, khai giảng 5/9, 20/10, Halloween, 11/11, Black Friday (thứ Sáu tuần thứ 4 tháng 11), 20/11, 12/12, Noel. Mỗi sự kiện có cửa sổ chuẩn bị theo danh mục.
- Hệ số nhu cầu `h(d)` là trung bình có trọng số (theo độ liên quan) của chỉ số mùa và đà tăng các từ khoá khớp, cắt trong [0,5; 1,5]. Nếu không khớp từ khoá nào thì dùng mùa vụ danh mục từ `tikireviews`.
- Điểm trục trend(d) = phân vị của `h(d)` so với listing cùng nhóm tại cùng ngày.

**Điểm tổng.**
- `base` = phân vị trong nhóm danh mục của model đầy đủ (HistGradientBoosting học trên `tiki26`, feature từ 4 trục học được cộng giá và metadata). Phần chữ được bổ sung bằng một model chữ học trên `tiki23`.
- Điểm theo ngày: `score(d) = clip(base × h(d), 0, 100)`. Endpoint trả `score(d)` cho hôm nay và cho 8 tuần tới, kèm các mốc sự kiện.

**Lời khuyên.**
- Mỗi vấn đề có `evidence`:
  - `measured`: trục có lift đạt tiêu chí ở mục 1;
  - `practice`: thực hành tốt, chưa đo được.
- Mỗi lời khuyên có `effort` và, nếu có, `impact` (mức phân vị tăng thêm khi sửa feature đó, ước lượng bằng counterfactual trên model).
- Thiếu chất liệu ở nhóm thời trang luôn được nêu, gắn nhãn `practice`, trừ khi đo được tác động.

## 6. API, BE, FE

AI (FastAPI, router `f29_intel.py`, đăng ký như các router F khác):

- `GET /api/analytics/listings/{id}/intel?date=YYYY-MM-DD`: kiểm tra listing thuộc shop. Trả `{score, score_timeline[8], axes{image,text,tags,market,trend}, issues[], advice[], material, peers, model}`.
- `POST /api/analytics/listings/intel/preview`: body `{title, description, tags[], materials[], category, price, image_urls[≤8]}`. Trả cùng dạng, không ghi Mongo.
- `GET /api/analytics/listings/intel`: danh sách listing của shop, mỗi dòng có điểm và 5 trục lấy từ `listing_intel_scores` mới nhất. Listing chưa có thì tính ngay.
- `GET /api/analytics/trends/calendar?category=`: sự kiện 12 tuần tới cùng từ khoá đang lên theo danh mục của shop.

Phản hồi dùng envelope `ok` / `insufficient` sẵn có, meta có `model_version`.

BE:
- `seller-analytics.router.ts` thêm các dòng route.
- Endpoint chấm thử có hàm parse body: giới hạn độ dài, tối đa 8 ảnh, ảnh chỉ nhận `https://res.cloudinary.com/...`.
- Product model và DTO thêm `materials?: string[]` (tối đa 5, mỗi mục ≤ 40 ký tự). Hàm create/update ghi trường này.

FE:
- Route `insights/listing-intel` và `insights/listing-intel/:id`, mục nav "Phân tích listing" trong nhóm "Nhìn vào trong".
- Component đặt trong `components/intel/`:
  - `IntelTable`
  - `AxisRadar`
  - `ImagePanel`
  - `KeywordPanel`
  - `TagPanel`
  - `MarketPanel`
  - `TrendTimeline`
  - `AdviceList`
  - `ModelCard`
- Form tạo và sửa sản phẩm có ô chọn chất liệu (gợi ý từ bộ từ vựng, cho nhập thêm) và nút "Chấm thử trước khi đăng". Nút này mở modal dùng lại các component trên.

## 7. Vận hành

- **Model bundle** `app/core/listing_intel/model/` gồm:
  - `fusion.joblib`, `axis_*.joblib`;
  - `meta.json` (phiên bản, sklearn, các chỉ số, ablation, ngưỡng);
  - `reference.parquet` (phân phối điểm theo nhóm, tâm nhóm, bảng lift n-gram, chỉ mục láng giềng ở dạng float16).
- **Model ONNX:** tải lần đầu vào `~/.cache/vietcraft-li/`, không commit; script `scripts/li/fetch_models.py`.
- Nạp lười và kiểm tra phiên bản sklearn khi nạp.
- **Cache:**
  - vector ảnh theo sha1 của URL trong `listing_embeddings`;
  - trend theo giờ trong bộ nhớ;
  - bảng tham chiếu nạp một lần.
- **Job:**
  - 02:00 tính lại cho listing có `updated_at` mới hơn điểm cuối, ghi `listing_intel_scores` (product_id, date, score, axes, model_version);
  - thứ Hai 03:00 chạy collector trend cho bộ từ khoá mở rộng, `request_delay` 4–8 giây, lỗi 429 thì để tuần sau thử lại.
- **An toàn:**
  - tải ảnh chỉ từ host trong danh sách cho phép;
  - timeout 5 giây, tối đa 8 MB, kiểm tra content-type ảnh;
  - không bao giờ ghi vào DB `vietcraft` thật trong lúc nghiên cứu.
- **Phụ thuộc mới ở runtime:** `onnxruntime`, `tokenizers`. Không thêm torch.

## 8. Đánh giá và báo cáo

`scripts/li/evaluate.py` sinh `docs/LISTING_INTEL_REPORT.md` và `docs/listing_intel_results.json`:

- **Bảng dữ liệu:** số dòng, làm sạch, tỉ lệ dương ở từng tập.
- **Baseline:**
  - ngẫu nhiên;
  - checklist health-1.0 (phần đo được);
  - chỉ giá;
  - chỉ số ảnh;
  - TF-IDF tiêu đề + logistic.
- **Model:** chữ (`tiki23`), từng trục, đầy đủ (`tiki26`).
- **Thước đo:**
  - AUC top25 kèm CI bootstrap theo shop;
  - Spearman và NDCG@10 trung bình theo nhóm;
  - chênh với baseline mạnh nhất kèm CI ghép cặp.
- **Ablation từng trục:** bỏ trục rồi học lại.
- **Test lệch thời gian:** từ `tiki23` sang `tiki26`.
- **Trend:**
  - MASE từng từ khoá so với seasonal naive;
  - tương quan mùa vụ Google Trends với `tikireviews`;
  - kiểm tra đỉnh trước dịp.
- **Sanity check:**
  - xáo trộn nhãn thì AUC ≈ 0,5;
  - test rò rỉ (không trùng shop giữa các tập, không feature bị loại lọt vào);
  - bất biến ảnh: độ sáng ±10% và JPEG chất lượng 70 làm điểm trục ảnh đổi ≤ 5 điểm;
  - phát hiện ảnh trùng;
  - điểm vẫn tất định khi chạy lại.
- **Dữ liệu thật VietCraft:**
  - độ phủ từng trục;
  - phân phối điểm;
  - PSI giữa feature Tiki và VietCraft;
  - 5 ví dụ có ảnh.
- **Mục viết tay:** drawback, điểm yếu → phần bị ảnh hưởng → cách sửa → trạng thái sau sửa.

Kiểm thử code:
- pytest cho từng module (fake Mongo, ảnh tổng hợp bằng numpy, chuỗi trend tổng hợp);
- `tsc` cho BE và FE;
- chạy đầu cuối trên stack local, chụp màn hình bằng Chrome headless;
- 2 agent review độc lập trước khi báo xong.

## 9. Rủi ro

| Rủi ro | Giảm thiểu |
|---|---|
| Không có dataset Việt về đồ thủ công hay POD | Ánh xạ danh mục gần nhất; báo PSI và độ phủ; ghi rõ trong báo cáo |
| `quantity_sold` là tổng tích luỹ, bị ảnh hưởng bởi quảng cáo và tuổi listing | Chuẩn hoá theo tuổi ở `tiki23`; so trong cùng nhóm; nêu thành điểm yếu |
| Ảnh Tiki không tải được hoặc bị chặn | Thử 50 ảnh trước; nếu tỉ lệ lỗi > 20% thì trục ảnh học trên `tikifashion`, dùng nhãn khớp danh mục thay cho lượt bán |
| Google Trends trả 429 | Giãn cách, lưu kết quả, chạy dần; từ khoá thiếu dùng mùa vụ từ `tikireviews` |
| Ổ đĩa còn ít | Ảnh thu nhỏ còn 256px dạng JPEG; dọn cache nghiên cứu cũ; đo dung lượng trước mỗi bước tải |
| Hạn 1 ngày | Chia việc cho nhiều agent song song theo plan; phần chưa đạt ghi vào báo cáo kèm cách sửa |
