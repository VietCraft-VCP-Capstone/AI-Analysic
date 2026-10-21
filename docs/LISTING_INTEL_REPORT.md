# Báo cáo Listing Intelligence (F29 v2)

Sinh tự động bởi `scripts/li/evaluate.py` ngày 2026-10-21, model `li-1.6`, scikit-learn 1.9.1. Mọi số liệu ở phần sinh tự động lấy nguyên từ `docs/listing_intel_results.json`. Các khối "viết tay" (giữa hai dấu `manual`) được giữ nguyên khi chạy lại; số trong đó lấy từ file kết quả hoặc từ audit được nêu tên.

## 1. Tóm tắt

- Test tiki26 (tập chính): model gộp ROC-AUC 0.626, CI95 [0.539; 0.753], AUC trong nhóm 0.651, 782 dòng, 234 cụm seller. Đây là AUC của model gộp thô trên dòng Tiki (cũng là số trên thẻ model ở giao diện). Điểm phục vụ còn thêm bước che và điền feature và sàn không ảnh (mục 3); trên dòng tiki26, sàn đổi điểm ở 0.6% dòng validation và 0.8% dòng test.
- Quy tắc gắn nhãn (spec §1.2): so với baseline mạnh nhất trên chính test tiki26 `TF-IDF tiêu đề + logistic` (AUC 0.600): chênh +0.0259, CI95 [-0.071; 0.119] → không thắng có ý nghĩa.
- Tham khảo: baseline mạnh nhất trên validation là `Chỉ giá (log_price) + nhóm` (AUC test 0.557): chênh +0.0680, CI95 [0.019; 0.126] → có ý nghĩa. So sánh này không dùng để gắn nhãn.
- Nhãn chứng cứ cho lời khuyên: Ảnh: `practice`, Từ khoá (chữ): `practice`, Tag: `practice`, Thị hiếu và cạnh tranh: `practice`, Trend và mùa vụ: `practice`.
- Cách chấm trục (quyết định trên validation): image formula, text formula, market model.
- Chọn feature trên validation: không giữ ứng viên nào.
- Trend: tiêu chí 4 (MASE < 1 trên phần lớn từ khoá) với luật chọn của spec §5: mốc cuối 66.7% (đạt), trung bình 6 mốc trượt 48.9% (**không đạt**); runtime không dùng dự báo này mà dùng hệ số mùa × đà tăng (mục 8).
- Khớp từ khoá trend: tiki23: 2.5% dòng khớp ≥ 1 từ khoá trend; tiki26: 8.2% dòng khớp ≥ 1 từ khoá trend.
- Sanity: đạt tất cả (bất biến ảnh xét theo trung vị; p90 lệch lớn nhất 14.7 điểm phân vị).
- Vì model gộp không thắng có ý nghĩa baseline mạnh nhất trên test, mọi trục mang nhãn `practice`; scorer không gắn nhãn "đã đo".

## 2. Dữ liệu

| Nguồn | Dòng thô | Sau làm sạch | Trong bảng feature | Tập | Số dòng | Tỉ lệ top25 | Seller | Dòng không có seller |
|---|---|---|---|---|---|---|---|---|
| tiki23 | 41603 | 41575 | 41575 | train | 27693 | 0.255 | 2664 | 0 |
| | | | | val | 7206 | 0.232 | 571 | 0 |
| | | | | test | 6676 | 0.250 | 571 | 0 |
| tiki26 | 8169 | 3998 | 3998 | train | 2709 | 0.244 | 350 | 739 |
| | | | | val | 507 | 0.201 | 71 | 163 |
| | | | | test | 782 | 0.294 | 81 | 153 |

Tỉ lệ dòng thiếu hẳn cả nhóm cột của một trục:

| Nguồn | Nhóm danh mục | Ảnh thiếu hẳn | Từ khoá (chữ) thiếu hẳn | Thị hiếu và cạnh tranh thiếu hẳn | Trend và mùa vụ thiếu hẳn |
|---|---|---|---|---|---|
| tiki23 | accessories, bags, shoes | 100.0% | 0.0% | 100.0% | 0.0% |
| tiki26 | fashion, home, sport | 0.0% | 0.0% | 0.0% | 0.0% |

- `tikifashion`: 5000 ảnh mẫu, đã nhúng: True.
- `tikireviews_monthly`: nhóm bags, fashion, home; số review bags: 5599, fashion: 22893, home: 552232.

## 3. Phương pháp

- Điểm tổng phục vụ người bán không đúng là hàm có AUC ở mục 1 và 5. Runtime (`fusion.served`, `fusion.base_score`) làm thêm 4 bước:
  - (a) che (đặt NaN) các feature có `feature_availability` < 0,01 trong nhóm;
  - (b) đặt các feature trong `feature_constants` về hằng số lúc học;
  - (c) khi listing không có ảnh, điền feature ảnh bằng `image_impute`;
  - (d) lấy sàn: điểm = max(model(listing), model(listing bỏ ảnh)). Sau đó điểm mới nhân `h(d)`.
- Mọi AUC trong báo cáo, kể cả AUC trên thẻ model ở giao diện, là của model gộp thô trên dòng Tiki, với feature như trong bảng, chưa qua các bước (a) đến (d).
- Trên dòng tiki26 có ảnh, sàn (d) đổi điểm ở 0.6% dòng validation và 0.8% dòng test. Số này lấy từ phép tính `impute_check` đã có (mục 9), không phải một lần đọc test mới.
- Các bước (a) đến (c) nhắm vào feature mà dòng Tiki lúc học không có, hoặc chỉ có một giá trị. Ảnh hưởng của chúng lên AUC trên dòng Tiki chưa được đo riêng.
- Ghi điểm và embedding lên DB production đang **tắt theo quyết định của người dùng** (B1): runtime chỉ ghi vào Mongo local. Vì vậy trên production, trang danh sách tính lại mỗi lần xem và không lưu điểm.
- `fusion`, `text`, `market`: `HistGradientBoostingClassifier(learning_rate=0.05, max_iter=400, random_state=42)`, cột `group` dạng category, không dò siêu tham số; `early_stopping` mặc định (`auto`: bật khi tập học > 10.000 dòng, giữ ngẫu nhiên 10% train để dừng sớm).
- `image`: `max_depth=4`, `min_samples_leaf=40`, `l2_regularization=1.0`, `max_iter=10`, `early_stopping=False` (learning_rate 0,05), chọn trên validation từ lưới cấu hình ở mục 9.
- Số vòng thực tế: fusion 171, image 10, text 166, market 400.
- Học trên `split == train` của cả hai nguồn (tiki23: 27693 dòng (top25 0.255), tiki26: 2709 dòng (top25 0.244)). GroupShuffleSplit theo seller 70/15/15, random_state=42; model học trên split=train.
- Validation được dùng cho 5 việc, không dùng test: (1) chọn feature bổ sung (mục 4); (2) quyết định trục dùng model hay công thức (mục 5); (3) chọn cấu hình model trục ảnh trên lưới (mục 9); (4) thiết kế trọng số và khoảng của công thức ảnh (mục 9); (5) dựng phân phối tham chiếu để đổi điểm thành phân vị. Cùng một tập validation tiki26 đóng cả 5 vai, nên các số validation ở mục 4, 5 và 9 lạc quan hơn một tập chưa xem; test dùng để báo cáo.
- Công bố: test tiki26 đã được chấm và báo cáo cho `li-1.0`, `li-1.1`, `li-1.2`, `li-1.3`, `li-1.4`, `li-1.5` với cùng phép chia; danh sách đầy đủ các lần đọc test ở khối dưới.
- Hai cách chọn baseline được báo cáo: mạnh nhất trên test (spec §1.2, dùng để gắn nhãn) và mạnh nhất trên validation (tham khảo). Baseline có chữ "+ nhóm" học cùng cột `group`.
- CI95: bootstrap 200 lần, lấy mẫu lại theo cụm seller; chênh AUC dùng bootstrap ghép cặp trên cùng mẫu.
- Spearman và NDCG@10 tính trong từng (nguồn, nhóm) với mục tiêu `sold` (tiki26) hoặc `sold / max(tuổi, 30)` (tiki23), rồi lấy trung bình. "Top 20% trúng" là kỳ vọng khi phá hoà ngẫu nhiên đều, nên không phụ thuộc thứ tự dòng.
- Khớp từ khoá trend: ngưỡng vector `trend_match_cos` = None (`None` nghĩa là chỉ khớp chữ đã bỏ dấu); hiệu chỉnh ở mục 8.
- Feature (56 cột): `log_price`, `price_rel`, `n_images`, `title_len`, `title_words`, `title_upper_ratio`, `title_repeat_ratio`, `title_banned`, `desc_len`, `desc_words`, `attr_material`, `attr_color`, `attr_size`, `attr_occasion`, `attr_use`, `kw_lift_sum`, `kw_lift_max`, `kw_lift_terms`, `img_w`, `img_h`, `img_aspect`, `img_sharpness`, `img_brightness`, `img_contrast`, `img_border_uniform`, `img_center_edges`, `img_text_ratio`, `sim_title`, `sim_category`, `style_white_bg`, `style_lifestyle`, `style_flatlay`, `style_closeup`, `emb_pca_0`, `emb_pca_1`, `emb_pca_2`, `emb_pca_3`, `emb_pca_4`, `emb_pca_5`, `emb_pca_6`, `emb_pca_7`, `emb_pca_8`, `emb_pca_9`, `emb_pca_10`, `emb_pca_11`, `emb_pca_12`, `emb_pca_13`, `emb_pca_14`, `emb_pca_15`, `knn_price_pct`, `knn_dup_count`, `top_centroid_margin`, `trend_factor`, `trend_matches`, `trend_momentum_max`, `group`.

<!-- manual:reads -->
Các lần đọc test tiki26 (cùng một phép chia), theo thứ tự:

1. li-1.0 (Task 10): đánh giá đầu tiên.
2. li-1.1: sau khi nhúng lại và dựng lại bảng feature; feature bổ sung chọn trên validation (mục 4). Test cho thấy model ảnh chỉ đạt AUC 0,528.
3. li-1.2: model giống hệt li-1.1 từng byte. Quy tắc chọn model hay công thức cho từng trục dựa trên validation, nhưng được đưa ra ngay sau lần đọc 2.
4. li-1.3: model ảnh chọn lại trên validation, lưới 241 cấu hình. max_iter 10 và 25 được thêm sau lượt đầu. Test cho AUC model ảnh 0,486.
5. li-1.4: công thức ảnh thiết kế trên validation, được đưa ra ngay sau lần đọc 4. Có 8 ứng viên: c8 được dựng sau khi đã xem c1 đến c7, và khoảng `sharpness_rel` cũng chỉnh trên validation. Lần này test chỉ đo bất biến của công thức.
6. Review vòng lặp, sau li-1.4: người review tính AUC test của công thức đang phục vụ (ảnh 0,561 [0,443; 0,631], chữ 0,576). Theo ruling, các số này vào báo cáo để mô tả, không dùng để quyết định.
7. li-1.5, đợt go-live: chạy lại `train` và `evaluate`. Vì model giống hệt li-1.4 từng byte, mọi số test cũ không đổi. Số mới trên test chỉ có hai thứ:
   - hai dòng công thức, đúng bằng số của lần 6;
   - bất biến ảnh đo lại qua `as_trained`.

   Trong lúc làm có một phép thử cách điền feature cho listing không ảnh. Lần chạy đó in số validation và số test cùng lúc:
   - điền q10 từng feature: listing không ảnh điểm cao hơn khi có ảnh ở 44,4% dòng validation và 43,0% dòng test;
   - điền bằng ảnh train làm điểm thấp nhất: 0,6% và 0,8%.

   Số cuối nằm ở mục 9 ("Điền feature cho listing không ảnh"). Bản chạy đầu còn điền cả cột thị hiếu và cho 80,9% / 0,6% trên validation; sau đó cột thị hiếu được để trống như lúc phục vụ.

   Cách điền được chọn theo số validation. Vector để điền chỉ chọn trên train.

Hệ quả:
- Test không còn là ước lượng chưa từng xem.
- Các quyết định ở lần 3 đến 5 đều có lý do ghi trên validation, nhưng được đưa ra sau khi đã thấy test (forking paths). Vì vậy số test nên đọc như một ước lượng hơi lạc quan.
<!-- /manual:reads -->

Lưu ý về dữ liệu (đo trên bảng feature):
- Nhóm danh mục: tiki23 ['accessories', 'bags', 'shoes'], tiki26 ['fashion', 'home', 'sport'] — hai nguồn không có nhóm chung, nên cột `group` cũng nhận diện nguồn; vì vậy báo cáo kèm AUC trong nhóm.
- tiki23: `n_images` thiếu 0.0%, mô tả rỗng 0.0%, có vector ảnh 0.0%.
- tiki26: `n_images` thiếu 100.0%, mô tả rỗng 100.0%, có vector ảnh 100.0%.

## 4. Chọn feature trên validation

Hai ứng viên được thử trên validation, test không dùng: `text_lr` (xác suất TF-IDF + logistic theo nhóm, out-of-fold theo seller cho dòng train) và `title_pca_*` (PCA 16 chiều của vector tiêu đề, fit trên train).

Quy tắc định trước: giữ ứng viên khi ROC-AUC tăng trên cả validation tiki26 lẫn validation gộp, Brier tăng không quá 0.001 và ECE tăng không quá 0.01 trên cả hai tập. Số dòng: Validation tiki26 507, Validation gộp 2 nguồn 7713.

| Biến thể | Validation tiki26: AUC | Chênh so với base [CI95] | Brier | ECE | Validation gộp 2 nguồn: AUC | Chênh so với base [CI95] | Brier | ECE |
|---|---|---|---|---|---|---|---|---|
| base | 0.634 | +0.0000 [0.000; 0.000] | 0.1595 | 0.0501 | 0.706 | +0.0000 [0.000; 0.000] | 0.1620 | 0.0283 |
| +text_lr | 0.610 | -0.0249 [-0.052; 0.009] | 0.1631 | 0.0591 | 0.718 | +0.0120 [0.001; 0.022] | 0.1596 | 0.0309 |
| +title_pca | 0.632 | -0.0023 [-0.030; 0.024] | 0.1581 | 0.0541 | 0.708 | +0.0023 [-0.008; 0.014] | 0.1610 | 0.0282 |
| +text_lr+title_pca | 0.616 | -0.0180 [-0.048; 0.010] | 0.1605 | 0.0808 | 0.725 | +0.0191 [0.007; 0.031] | 0.1578 | 0.0232 |

Kết quả: không giữ ứng viên nào. Model dùng 56 cột.

## 5. Kết quả trên test

Model gộp so với baseline trên test tiki26 (CI bootstrap ghép cặp theo seller):

| Cách chọn baseline | Baseline | AUC baseline (test) | Chênh AUC | CI95 ghép cặp | Có ý nghĩa | Vai trò |
|---|---|---|---|---|---|---|
| Mạnh nhất trên test tiki26 (spec §1.2) | `TF-IDF tiêu đề + logistic` | 0.600 | +0.0259 | [-0.071; 0.119] | không | gắn nhãn chứng cứ |
| Mạnh nhất trên validation tiki26 | `Chỉ giá (log_price) + nhóm` | 0.557 | +0.0680 | [0.019; 0.126] | có | tham khảo |

Tập phụ, chỉ để đối chiếu:

- Test tiki23, cùng baseline `TF-IDF tiêu đề + logistic`: chênh +0.0201, CI95 [-0.014; 0.053]
- Test gộp 2 nguồn, cùng baseline `TF-IDF tiêu đề + logistic`: chênh +0.0180, CI95 [-0.018; 0.050]

### Chế độ chấm từng trục (quyết định trên validation)

Quy tắc: trục dùng model khi cận dưới CI95 (bootstrap theo seller) của ROC-AUC trên mọi tập validation có trục đó (validation tiki26, validation gộp) lớn hơn 0,5; nếu không, trục dùng công thức minh bạch. Riêng trục ảnh dùng công thức khi kết quả độ bền đã lưu (`reference/image_design.json`) cho thấy p90 lệch của model ổn định nhất lớn hơn p90 lệch của công thức trên cùng tập ảnh validation biến đổi.

| Trục | Validation tiki26: ROC-AUC model [CI95] | Validation gộp: ROC-AUC model [CI95] | Cách chấm | Lý do | ROC-AUC công thức đang phục vụ: validation tiki26 / test tiki26 (đo hậu kiểm) |
|---|---|---|---|---|---|
| Ảnh | 0.592 [0.540; 0.661] | 0.592 [0.540; 0.661] | **công thức minh bạch** | độ bền trên validation (507 ảnh, 241 cấu hình): model ảnh ổn định nhất (max_iter=10, max_depth=4) lệch trung vị 0,0 nhưng p90 lệch 33,8 điểm phân vị, so với p90 lớn nhất 13,3 của công thức `c8_rel_sharp_flags_0.05` | 0.489 [0.381; 0.578] / 0.561 [0.443; 0.631] |
| Từ khoá (chữ) | 0.462 [0.383; 0.589] | 0.690 [0.642; 0.734] | **công thức minh bạch** | AUC validation không hơn ngẫu nhiên | 0.577 [0.411; 0.696] / 0.576 [0.500; 0.642] |
| Thị hiếu và cạnh tranh | 0.616 [0.544; 0.703] | 0.616 [0.544; 0.703] | model học có giám sát | AUC validation hơn ngẫu nhiên | — |

Trục dùng công thức được chấm bằng phân vị của điểm công thức so với listing Tiki cùng nhóm trong quần thể tham chiếu (cùng quần thể với phân vị của trục dùng model), luôn mang nhãn `practice`. Model gộp không đổi.

Trọng số công thức (`app/core/listing_intel/formulas.py`): Ảnh: sharpness_rel 0.3, exposure_ok 0.05, contrast_ok 0.05, border 0.3, no_text 0.15, resolution 0.05, sim_title 0.05, sim_category 0.05; Từ khoá (chữ): attributes 0.35, title_length 0.2, keyword_lift 0.25, clean 0.2; Thị hiếu và cạnh tranh: price_centre 0.6, uniqueness 0.4. Ngưỡng: {'img_sharpness': [3.0, 5.5], 'sharpness_rel': [-5.2, -2.4], 'sim_title': [0.05, 0.2], 'sim_category': [0.03, 0.14], 'img_text_ratio': [0.08, 0.16], 'short_side': [128.0, 256.0], 'kw_lift_scale': 2.0}, dải độ dài tiêu đề [20.0, 120.0], lặp từ tối đa 0.3, dải độ sáng [0.25, 0.9]. `resolution` là cạnh ngắn của ảnh sau khi thu về 256 px, tức thực chất đo tỉ lệ khung; ảnh Tiki tham chiếu đều vuông 256 × 256 nên phần này bằng 1 với mọi ảnh tham chiếu và chỉ hạ điểm ảnh không vuông.

Công thức chữ chỉ dùng tiêu đề và chất liệu khai báo (listing Tiki tham chiếu không có mô tả), và trừ 0.15 cho mỗi thuộc tính bắt buộc còn thiếu theo nhóm: material: accessories, bags, fashion, shoes; color: fashion, shoes; size: fashion, shoes.

### Test tiki26 (tập chính)

| Phương pháp | ROC-AUC | CI95 (bootstrap theo seller) | PR-AUC | AUC trong nhóm | Spearman | NDCG@10 | Top 20% trúng | n dòng (cụm seller) |
|---|---|---|---|---|---|---|---|---|
| Model gộp (fusion) | 0.626 | [0.539; 0.753] | 0.391 | 0.651 | 0.261 | 0.601 | 44.9% | 782 (234) |
| Model trục Ảnh: học có giám sát, không phục vụ | 0.486 | [0.407; 0.561] | 0.285 | 0.507 | 0.054 | 0.595 | 26.3% | 782 (234) |
| Model trục Từ khoá (chữ): học có giám sát, không phục vụ | 0.590 | [0.512; 0.658] | 0.348 | 0.612 | 0.190 | 0.608 | 34.6% | 782 (234) |
| Model trục Thị hiếu và cạnh tranh: học có giám sát, đang phục vụ | 0.557 | [0.493; 0.644] | 0.345 | 0.575 | 0.120 | 0.612 | 36.5% | 782 (234) |
| Công thức trục Ảnh: đang phục vụ, đo hậu kiểm | 0.561 | [0.443; 0.631] | 0.360 | 0.522 | 0.067 | 0.566 | 41.0% | 782 (234) |
| Công thức trục Từ khoá (chữ): đang phục vụ, đo hậu kiểm | 0.576 | [0.500; 0.642] | 0.366 | 0.510 | -0.010 | 0.518 | 35.3% | 782 (234) |
| Ngẫu nhiên | 0.517 | [0.477; 0.557] | 0.310 | 0.513 | -0.000 | 0.504 | 32.1% | 782 (234) |
| health-1.0 (ảnh ≥5, mô tả ≥150) | 0.500 | [0.500; 0.500] | 0.294 | 0.500 | — | — | 29.4% | 782 (234) |
| Chỉ giá (log_price) + nhóm | 0.557 | [0.482; 0.654] | 0.328 | 0.585 | 0.173 | 0.577 | 33.3% | 782 (234) |
| Chỉ số ảnh (n_images) + nhóm | 0.428 | [0.357; 0.503] | 0.264 | 0.500 | — | — | 20.9% | 782 (234) |
| TF-IDF tiêu đề + logistic | 0.600 | [0.518; 0.701] | 0.391 | 0.622 | 0.193 | 0.612 | 42.9% | 782 (234) |

### Validation tiki26

| Phương pháp | ROC-AUC | CI95 (bootstrap theo seller) | PR-AUC | AUC trong nhóm | Spearman | NDCG@10 | Top 20% trúng | n dòng (cụm seller) |
|---|---|---|---|---|---|---|---|---|
| Model gộp (fusion) | 0.634 | [0.560; 0.743] | 0.289 | 0.654 | 0.323 | 0.665 | 28.7% | 507 (234) |
| Model trục Ảnh: học có giám sát, không phục vụ | 0.592 | [0.540; 0.661] | 0.248 | 0.607 | 0.156 | 0.554 | 24.8% | 507 (234) |
| Model trục Từ khoá (chữ): học có giám sát, không phục vụ | 0.462 | [0.383; 0.589] | 0.234 | 0.499 | 0.081 | 0.677 | 22.8% | 507 (234) |
| Model trục Thị hiếu và cạnh tranh: học có giám sát, đang phục vụ | 0.616 | [0.544; 0.703] | 0.302 | 0.628 | 0.239 | 0.687 | 28.7% | 507 (234) |
| Công thức trục Ảnh: đang phục vụ, đo hậu kiểm | 0.489 | [0.381; 0.578] | 0.191 | 0.447 | -0.047 | 0.512 | 15.8% | 507 (234) |
| Công thức trục Từ khoá (chữ): đang phục vụ, đo hậu kiểm | 0.577 | [0.411; 0.696] | 0.233 | 0.569 | 0.118 | 0.610 | 24.8% | 507 (234) |
| Ngẫu nhiên | 0.490 | [0.448; 0.549] | 0.195 | 0.496 | -0.066 | 0.472 | 13.9% | 507 (234) |
| health-1.0 (ảnh ≥5, mô tả ≥150) | 0.500 | [0.500; 0.500] | 0.201 | 0.500 | — | — | 20.1% | 507 (234) |
| Chỉ giá (log_price) + nhóm | 0.617 | [0.531; 0.723] | 0.266 | 0.644 | 0.320 | 0.636 | 32.7% | 507 (234) |
| Chỉ số ảnh (n_images) + nhóm | 0.439 | [0.311; 0.620] | 0.187 | 0.500 | — | — | 18.1% | 507 (234) |
| TF-IDF tiêu đề + logistic | 0.611 | [0.496; 0.700] | 0.295 | 0.608 | 0.150 | 0.670 | 31.7% | 507 (234) |

### Test tiki23

| Phương pháp | ROC-AUC | CI95 (bootstrap theo seller) | PR-AUC | AUC trong nhóm | Spearman | NDCG@10 | Top 20% trúng | n dòng (cụm seller) |
|---|---|---|---|---|---|---|---|---|
| Model gộp (fusion) | 0.712 | [0.677; 0.742] | 0.440 | 0.711 | 0.358 | 0.704 | 47.9% | 6676 (571) |
| Model trục Ảnh: học có giám sát, không phục vụ | — | — | — | — | — | — | — | — |
| Model trục Từ khoá (chữ): học có giám sát, không phục vụ | 0.693 | [0.658; 0.730] | 0.404 | 0.694 | 0.336 | 0.517 | 44.0% | 6676 (571) |
| Model trục Thị hiếu và cạnh tranh: học có giám sát, đang phục vụ | — | — | — | — | — | — | — | — |
| Công thức trục Ảnh: đang phục vụ, đo hậu kiểm | — | — | — | — | — | — | — | — |
| Công thức trục Từ khoá (chữ): đang phục vụ, đo hậu kiểm | 0.534 | [0.490; 0.580] | 0.288 | 0.574 | 0.134 | 0.694 | 26.0% | 6676 (571) |
| Ngẫu nhiên | 0.499 | [0.484; 0.518] | 0.250 | 0.500 | -0.012 | 0.539 | 24.6% | 6676 (571) |
| health-1.0 (ảnh ≥5, mô tả ≥150) | 0.519 | [0.485; 0.557] | 0.258 | 0.519 | 0.047 | 0.509 | 25.9% | 6676 (571) |
| Chỉ giá (log_price) + nhóm | 0.583 | [0.545; 0.620] | 0.321 | 0.577 | 0.120 | 0.581 | 35.4% | 6676 (571) |
| Chỉ số ảnh (n_images) + nhóm | 0.505 | [0.472; 0.535] | 0.259 | 0.506 | 0.002 | 0.594 | 23.7% | 6676 (571) |
| TF-IDF tiêu đề + logistic | 0.691 | [0.654; 0.729] | 0.405 | 0.692 | 0.324 | 0.677 | 44.9% | 6676 (571) |

### Test gộp 2 nguồn

| Phương pháp | ROC-AUC | CI95 (bootstrap theo seller) | PR-AUC | AUC trong nhóm | Spearman | NDCG@10 | Top 20% trúng | n dòng (cụm seller) |
|---|---|---|---|---|---|---|---|---|
| Model gộp (fusion) | 0.700 | [0.666; 0.732] | 0.432 | 0.705 | 0.310 | 0.652 | 47.7% | 7458 (804) |
| Model trục Ảnh: học có giám sát, không phục vụ | 0.486 | [0.407; 0.561] | 0.285 | 0.507 | 0.054 | 0.595 | 26.3% | 782 (234) |
| Model trục Từ khoá (chữ): học có giám sát, không phục vụ | 0.682 | [0.649; 0.719] | 0.397 | 0.685 | 0.263 | 0.562 | 43.6% | 7458 (804) |
| Model trục Thị hiếu và cạnh tranh: học có giám sát, đang phục vụ | 0.557 | [0.493; 0.644] | 0.345 | 0.575 | 0.120 | 0.612 | 36.5% | 782 (234) |
| Công thức trục Ảnh: đang phục vụ, đo hậu kiểm | 0.561 | [0.443; 0.631] | 0.360 | 0.522 | 0.067 | 0.566 | 41.0% | 782 (234) |
| Công thức trục Từ khoá (chữ): đang phục vụ, đo hậu kiểm | 0.542 | [0.499; 0.580] | 0.298 | 0.567 | 0.062 | 0.606 | 27.8% | 7458 (804) |
| Ngẫu nhiên | 0.502 | [0.484; 0.514] | 0.256 | 0.502 | -0.006 | 0.521 | 25.4% | 7458 (804) |
| health-1.0 (ảnh ≥5, mô tả ≥150) | 0.504 | [0.472; 0.543] | 0.258 | 0.517 | 0.047 | 0.509 | 25.9% | 7458 (804) |
| Chỉ giá (log_price) + nhóm | 0.578 | [0.551; 0.614] | 0.320 | 0.578 | 0.147 | 0.579 | 35.3% | 7458 (804) |
| Chỉ số ảnh (n_images) + nhóm | 0.493 | [0.465; 0.518] | 0.258 | 0.505 | 0.002 | 0.594 | 24.4% | 7458 (804) |
| TF-IDF tiêu đề + logistic | 0.682 | [0.647; 0.718] | 0.402 | 0.685 | 0.259 | 0.645 | 44.3% | 7458 (804) |

### Validation gộp 2 nguồn

| Phương pháp | ROC-AUC | CI95 (bootstrap theo seller) | PR-AUC | AUC trong nhóm | Spearman | NDCG@10 | Top 20% trúng | n dòng (cụm seller) |
|---|---|---|---|---|---|---|---|---|
| Model gộp (fusion) | 0.706 | [0.648; 0.756] | 0.402 | 0.711 | 0.335 | 0.758 | 41.2% | 7713 (805) |
| Model trục Ảnh: học có giám sát, không phục vụ | 0.592 | [0.540; 0.661] | 0.248 | 0.607 | 0.156 | 0.554 | 24.8% | 507 (234) |
| Model trục Từ khoá (chữ): học có giám sát, không phục vụ | 0.690 | [0.642; 0.734] | 0.391 | 0.688 | 0.202 | 0.732 | 40.5% | 7713 (805) |
| Model trục Thị hiếu và cạnh tranh: học có giám sát, đang phục vụ | 0.616 | [0.544; 0.703] | 0.302 | 0.628 | 0.239 | 0.687 | 28.7% | 507 (234) |
| Công thức trục Ảnh: đang phục vụ, đo hậu kiểm | 0.489 | [0.381; 0.578] | 0.191 | 0.447 | -0.047 | 0.512 | 15.8% | 507 (234) |
| Công thức trục Từ khoá (chữ): đang phục vụ, đo hậu kiểm | 0.536 | [0.475; 0.597] | 0.255 | 0.576 | 0.115 | 0.573 | 23.8% | 7713 (805) |
| Ngẫu nhiên | 0.476 | [0.464; 0.492] | 0.219 | 0.477 | -0.044 | 0.451 | 21.3% | 7713 (805) |
| health-1.0 (ảnh ≥5, mô tả ≥150) | 0.530 | [0.490; 0.566] | 0.242 | 0.525 | 0.047 | 0.509 | 24.4% | 7713 (805) |
| Chỉ giá (log_price) + nhóm | 0.571 | [0.515; 0.626] | 0.288 | 0.566 | 0.211 | 0.583 | 31.5% | 7713 (805) |
| Chỉ số ảnh (n_images) + nhóm | 0.498 | [0.444; 0.545] | 0.248 | 0.509 | 0.002 | 0.744 | 22.6% | 7713 (805) |
| TF-IDF tiêu đề + logistic | 0.674 | [0.619; 0.726] | 0.381 | 0.676 | 0.217 | 0.715 | 42.0% | 7713 (805) |

Dòng "Model trục …: học có giám sát, không phục vụ" là model đã bị thay bằng công thức; điểm trục người bán thấy đến từ dòng "Công thức trục …: đang phục vụ". Các dòng công thức được tính sau khi đã chọn chế độ chấm, chỉ để mô tả, không dùng để quyết định.

## 6. Ablation từng trục

| Trục bỏ ra | AUC giảm (lift) | CI95 ghép cặp | Số dòng test đo | Nguồn đo | Nhãn |
|---|---|---|---|---|---|
| Ảnh | +0.0093 | [-0.019; 0.053] | 782 | tiki26 | practice |
| Từ khoá (chữ) | +0.0321 | [-0.013; 0.075] | 782 | tiki26 | practice |
| Thị hiếu và cạnh tranh | -0.0030 | [-0.020; 0.029] | 782 | tiki26 | practice |
| Trend và mùa vụ | -0.0023 | [-0.020; 0.014] | 782 | tiki26 | practice |

Ablation, nhãn chứng cứ và phép so baseline đều tính trên cùng test tiki26. Quy tắc: trục là `measured` khi lift ≥ 0,005, CI95 ghép cặp không chứa 0 và model gộp thắng có ý nghĩa baseline mạnh nhất trên test. Trục tag là công thức minh bạch, không học có giám sát, nên luôn là `practice`.

## 7. Test lệch thời gian (tiki23 → tiki26)

| Cách học | Số dòng học | ROC-AUC trên tiki26 test | CI95 | AUC trong nhóm | Chênh với học tại chỗ | CI95 chênh |
|---|---|---|---|---|---|---|
| Học trên toàn bộ tiki23 (2023) → tiki26 test (2026) | 41575 | 0.554 | [0.482; 0.645] | 0.569 | -0.0544 | [-0.130; 0.039] |
| Như trên, bỏ kw_lift_* (bảng lift học từ nhãn train của cả 2 nguồn) | 41575 | 0.557 | [0.494; 0.658] | 0.558 | -0.0518 | [-0.131; 0.051] |
| Học trên tiki26 train → tiki26 test, cùng feature | 2709 | 0.608 | [0.537; 0.709] | 0.624 | — | — |
| Học trên train của cả 2 nguồn → tiki26 test, cùng feature | 30402 | 0.595 | [0.528; 0.713] | 0.617 | — | — |

Nhóm học: accessories, bags, shoes; nhóm test: fashion, home, sport. Feature: chỉ chữ và meta (`TEXT_COLS + META_COLS`); cột toàn NaN ở tập học bị bỏ: `n_images`. Hai nguồn không chung nhóm nên đây là lệch cả thời gian lẫn danh mục.

## 8. Trend và mùa vụ

### Tiêu chí 4

Tiêu chí 4 (spec §1): dự báo 8 tuần có MASE < 1 so với seasonal naive trên phần lớn (> 50%) từ khoá đủ điều kiện. MASE chia sai số dự báo cho MAE của seasonal naive (chu kỳ 52) trong phần học.

| Phương pháp dự báo 8 tuần | Mốc cuối: tỉ lệ từ khoá MASE < 1 | 6 mốc trượt: tỉ lệ từ khoá có MASE trung bình < 1 | Tỉ lệ cặp từ khoá–mốc MASE < 1 |
|---|---|---|---|
| STL | 68.9% | 46.7% | 62.2% |
| Seasonal naive | 71.1% | 46.7% | 62.2% |
| Chọn theo backtest 8 tuần trước (luật chọn của spec §5, runtime không dùng) | 66.7% | 48.9% | 63.0% |

- Luật chọn so với seasonal naive ngoài mẫu: tốt hơn hẳn ở 8.9% từ khoá (mốc cuối) và 17.8% cặp từ khoá–mốc; khi luật chọn naive thì hai bên bằng nhau.
- Kết luận: mốc cuối đạt; trung bình nhiều mốc **không đạt**.
- Runtime (`trend_axis.demand_factor`) không dùng phương pháp nào trong bảng: `h(d)` = chỉ số mùa theo tuần (thành phần mùa STL khi chuỗi ≥ 104 tuần, nếu ngắn hơn thì trung bình theo tuần) × (1 + đà tăng 4 tuần so với 4 tuần trước, cắt ±0,5), lấy trung bình theo các từ khoá khớp rồi cắt [0,5; 1,5]; không khớp từ khoá nào thì dùng mùa vụ nhóm từ `tikireviews` hoặc 1,0. Không có dự báo mức và không chọn STL hay naive. Bảng này chỉ đánh giá dự báo chuỗi từ khoá; `h(d)` được kiểm ở phần "Đỉnh trước dịp".

### Backtest chi tiết

- Một mốc (8 tuần cuối), 45/45 từ khoá đủ dài: MASE trung vị STL 0.809, naive 0.547; STL tốt hơn naive ở 26.7%. Nếu chọn bằng chính tập chấm (lạc quan, chỉ để đối chiếu): 80.0%.
- 6 mốc trượt không chồng nhau (48 tuần, 270 cặp); STL thắng naive ở 37.8% cặp.
- 15 từ khoá trong danh sách chưa có chuỗi tuần trong Mongo local: áo khoác, đầm len, váy, túi da, giày sneaker, gốm sứ, mây tre, thổ cẩm, lụa, quà trung thu, quà 11/11, black friday, quà khai giảng, halloween, trang trí trung thu.

### Mùa vụ Google Trends so với `tikireviews_monthly`

Hồ sơ 12 tháng trung bình của các từ khoá trong nhóm (gán nhóm bằng regex trên từ khoá, còn lại vào `home`) so với chỉ số tháng của review Tiki.

| Nhóm | Số từ khoá Google Trends | Pearson r (p) | Spearman ρ (p) |
|---|---|---|---|
| bags | 1 | 0.316 (0.317) | 0.308 (0.331) |
| fashion | 19 | -0.142 (0.660) | -0.091 (0.779) |
| home | 25 | 0.399 (0.199) | 0.448 (0.145) |

### Đỉnh trước dịp

Hệ số `mùa × (1 + đà tăng cắt ±0,5)` tính chỉ bằng dữ liệu trước từng tuần, chưa cắt [0,5; 1,5] như `h(d)` (để thấy vị trí đỉnh khi hệ số chạm trần); tìm đỉnh trong độ lệch -8 … +2 tuần quanh dịp (0 là tuần có dịp). 52 cặp (từ khoá, năm); đỉnh rơi vào độ lệch -4 … +0 tuần ở 84.6%.

| Từ khoá | Dịp | Số năm | Độ lệch đỉnh trung vị (tuần) | Tỉ lệ năm có đỉnh ở độ lệch -4 … +0 tuần |
|---|---|---|---|---|
| lì xì tết | tet | 4 | -2.5 | 75.0% |
| quà 20/10 | 20/10 | 4 | -1.0 | 100.0% |
| quà 20/11 | 20/11 | 4 | -2.0 | 100.0% |
| quà 8/3 | 8/3 | 4 | -1.0 | 100.0% |
| quà giáng sinh | noel | 4 | -1.5 | 100.0% |
| quà tặng người yêu | valentine | 4 | +1.5 | 0.0% |
| quà tặng thầy cô | 20/11 | 4 | -2.0 | 100.0% |
| quà tết | tet | 4 | -4.0 | 50.0% |
| quà valentine | valentine | 4 | -1.0 | 100.0% |
| trang trí noel | noel | 4 | -3.5 | 100.0% |
| trang trí tết | tet | 4 | -3.5 | 75.0% |
| áo giáng sinh | noel | 4 | -1.5 | 100.0% |
| áo tết | tet | 4 | -3.0 | 100.0% |

### Hiệu chỉnh ngưỡng khớp vector

Hiệu chỉnh trên 3998 tiêu đề tiki26 và 45 từ khoá có chuỗi: khớp chữ đã bỏ dấu ở 8.2% dòng; cos tiêu đề–từ khoá trung vị 0.787, p90 0.85, p99 0.9. Token chung của nhiều từ khoá (bị bỏ khi xét chung token): ao, qua, sinh, tang, tet, thun, trang, tri.

| Ngưỡng cos | Dòng không khớp chữ nhưng khớp vector | … và có chung token riêng của từ khoá | Số từ khoá khớp trung bình |
|---|---|---|---|
| ≥ 0.8 | 69.2% | 49.1% | 23.42 |
| ≥ 0.85 | 34.5% | 23.1% | 11.02 |
| ≥ 0.88 | 15.3% | 9.9% | 6.06 |
| ≥ 0.9 | 6.8% | 4.3% | 4.1 |
| ≥ 0.92 | 2.5% | 1.8% | 2.6 |

Mẫu chấm tay 100 cặp, có nhãn từng cặp trong `app/core/listing_intel/model/reference/trend_calib_judged.json` (không bị `evaluate` ghi đè): đúng chặt 1/100, nới 4/100; theo dải [0.8, 0.85): 0/20 (nới 0); [0.85, 0.88): 1/20 (nới 1); [0.88, 0.9): 0/20 (nới 1); [0.9, 0.92): 0/20 (nới 0); [0.92, 1.01): 0/20 (nới 2).

<!-- manual:calib -->
Chấm tay (li-1.1, 2026-10-21) 100 cặp (mẫu trong `data-li/features/trend_calib_sample.csv`; từ li-1.5 nhãn từng cặp được lưu ở `app/core/listing_intel/model/reference/trend_calib_judged.json`, dựng lại từ biên bản này và khớp đúng số đếm theo dải): 20 cặp mỗi dải cos, lấy ngẫu nhiên (seed 0) trong các tiêu đề tiki26 **không** khớp chữ với từ khoá nào, vì chỉ ở các dòng này nhánh vector mới quyết định kết quả. Một cặp là đúng khi người tìm từ khoá đó sẽ muốn thấy sản phẩm này.

| Dải cos | Đúng (chặt) | Đúng (nới: tính cả cặp lưng chừng) |
|---|---|---|
| [0,80; 0,85) | 0/20 | 0/20 |
| [0,85; 0,88) | 1/20 | 1/20 |
| [0,88; 0,90) | 0/20 | 1/20 |
| [0,90; 0,92) | 0/20 | 0/20 |
| ≥ 0,92 | 0/20 | 2/20 |
| Tổng | 1/100 | 4/100 |

- Cặp đúng duy nhất (chặt): "Áo kiểu nữ, áo phông in họa tiết hoa…" ↔ "áo thun" (0,862). Lưng chừng: "ÁO SỌC BỤI BỤI FORM RỘNG" ↔ "áo thun", "Áo nữ thun co giãn cổ tim" ↔ "áo thun thể thao", "ÁO NGẮN TAY VẠT NGANG" ↔ "áo thun".
- Ví dụ sai ở cos cao: "Áo Khoác Nam" ↔ "áo phông nữ" (0,934), "Năm sinh đẹp hiếm" ↔ "quà tết" (0,927), "Áo kiểu bo ly thời trang" ↔ "áo lớp" (0,937).
- Bắt buộc chung một token riêng của từ khoá (bỏ các token chung như "áo", "quà") không cứu được: 0/13 cặp có chung token là đúng.
- Khớp chữ đã bỏ dấu: 20/20 cặp mẫu đúng (392 cặp trên 3.998 tiêu đề tiki26, phần lớn là "áo thun" và "quà tặng").

Quyết định: không ngưỡng nào cho độ chính xác dùng được, kể cả khi đòi chung token, nên li-1.1 tắt nhánh vector (`trend_match_cos = None` trong context và `meta.thresholds`), chỉ khớp chữ đã bỏ dấu. Đây là lệch so với spec §5 ("nếu không có thì dùng độ tương đồng vector ≥ ngưỡng hiệu chỉnh"): phép hiệu chỉnh cho kết quả là bộ mã hoá chữ SigLIP2 int8 không phân biệt được loại sản phẩm tiếng Việt (cos tiêu đề–từ khoá trung vị khoảng 0,79). Hệ quả: độ phủ trend thấp, phần lớn listing dùng mùa vụ nhóm từ `tikireviews` hoặc 1,0.
<!-- /manual:calib -->

## 9. Sanity check

| Kiểm tra | Kết quả | Đạt |
|---|---|---|
| Xáo trộn nhãn train (5 seed) | AUC trung bình test tiki26 0.4952, test gộp 0.5136; từng lần tiki26 [0.5185, 0.5113, 0.4711, 0.4804, 0.4949], gộp [0.5281, 0.5359, 0.5169, 0.5028, 0.4845]; AUC trong nhóm trung bình tiki26 0.4903, gộp 0.5167; khoảng [0.45, 0.55] | đạt |
| Không seller nào ở 2 tập | tiki23: train-val=0, train-test=0, val-test=0; tiki26: train-val=0, train-test=0, val-test=0; dòng val/test có tên seller trùng với train nguồn kia: 46 | đạt |
| Không cột cấm trong feature | kiểm 56 cột, lọt: không; cột của model khớp meta: True | đạt |
| Tất định | học lại 2 lần giống hệt: True; giống bundle: True | đạt |
| Bất biến ảnh, trục đang phục vụ (formula; 50 ảnh test, ảnh đi qua `image_load.as_trained` như lúc phục vụ, ngưỡng ≤ 5.0 điểm phân vị) | trung vị lệch sáng +10%: 4.3; tối -10%: 2.81; JPEG q70: 2.59; p90 sáng +10%: 14.7; tối -10%: 10.08; JPEG q70: 11.13; ảnh gốc qua `as_trained` so với bảng feature lệch trung vị 0.34 | đạt |
| Bất biến ảnh, cách chấm không phục vụ (model, tham khảo) | trung vị lệch sáng +10%: 0.0; tối -10%: 0.0; JPEG q70: 0.0; p90 sáng +10%: 19.55; tối -10%: 14.98; JPEG q70: 22.97 | — |
| Phát hiện ảnh trùng (dHash) | Hamming trung vị bản biến đổi: sáng +10%: 1.0; tối -10%: 0.0; JPEG q70: 0.0; giữa 2 ảnh khác nhau: 28.0 | — |

Chẩn đoán bất biến ảnh với model trục ảnh học (không phục vụ; trục ảnh đang dùng công thức), 50 ảnh, không qua `as_trained`:
- Cùng một ảnh, gọi riêng so với gọi chung một lần 50 ảnh: cos trung vị 1.0, thấp nhất 1.0, tức vector không phụ thuộc lô; so với vector trong bảng feature: cos trung vị 1.0.
- sáng +10%: cos vector ảnh gốc–biến đổi 0.9785; lệch trung vị khi chỉ đổi số đo kỹ thuật 0.0, chỉ đổi vector 0.0, đổi cả hai 0.0 điểm
- tối -10%: cos vector ảnh gốc–biến đổi 0.9788; lệch trung vị khi chỉ đổi số đo kỹ thuật 0.0, chỉ đổi vector 0.0, đổi cả hai 0.0 điểm
- JPEG q70: cos vector ảnh gốc–biến đổi 0.9727; lệch trung vị khi chỉ đổi số đo kỹ thuật 0.0, chỉ đổi vector 0.0, đổi cả hai 0.0 điểm

Retrieval ảnh–caption trên 200 cặp `tikifashion`: top-1 ảnh→chữ 34.0%, chữ→ảnh 23.0%, recall@5 65.0%, ngẫu nhiên 0.5% (gấp 68.0 lần); cos cặp đúng 0.1212, cặp sai 0.062.

### Độ bền trục ảnh, chọn trên validation

Tập biến đổi dựng từ 507 ảnh validation tiki26 (không dùng test): sáng ±10%, JPEG q70; điểm phân vị so với phân phối dự đoán validation cùng nhóm, đúng như khi phục vụ. Lưới: max_depth ∈ [3, 4], min_samples_leaf ∈ [40, 100], l2_regularization ∈ [1.0, 10.0], max_iter ∈ [10, 25, 50, 100, 200, 400]; learning_rate 0,05, không dừng sớm. Bộ cột: `all`: 31 cột; `no_raw_exposure`: 30 cột; `no_emb_pca`: 15 cột; `no_emb_pca_raw_exposure`: 14 cột; `quality_only`: 8 cột. Quy tắc chọn: cận dưới CI95 ROC-AUC validation > 0,5, rồi chọn lệch trung vị lớn nhất (3 biến đổi) nhỏ nhất, hoà thì AUC cao hơn; mục tiêu ≤ 5.0 điểm phân vị.

| Cấu hình | Bộ cột | Tham số HGB | AUC validation [CI95] | Lệch trung vị (điểm phân vị) | p90 lệch lớn nhất | Số giá trị dự đoán khác nhau |
|---|---|---|---|---|---|---|
| li-1.1 | all | max_depth=None, min_samples_leaf=20, l2_regularization=0.0, max_iter=400 | 0.632 [0.548; 0.684] | JPEG q70 8.68; sáng +10% 10.39; tối -10% 9.5 | 31.02 | 507 |
| ổn định nhất của `all` (39/48 cấu hình có CI > 0,5) | all | max_depth=4, min_samples_leaf=40, l2_regularization=1.0, max_iter=10 | 0.593 [0.541; 0.661] | JPEG q70 0.0; sáng +10% 0.0; tối -10% 0.0 | 33.75 | 226 |
| ổn định nhất của `no_raw_exposure` (40/48 cấu hình có CI > 0,5) | no_raw_exposure | max_depth=4, min_samples_leaf=40, l2_regularization=1.0, max_iter=10 | 0.592 [0.540; 0.659] | JPEG q70 0.0; sáng +10% 0.0; tối -10% 0.0 | 32.69 | 224 |
| ổn định nhất của `no_emb_pca` (32/48 cấu hình có CI > 0,5) | no_emb_pca | max_depth=4, min_samples_leaf=40, l2_regularization=1.0, max_iter=10 | 0.592 [0.510; 0.681] | JPEG q70 4.31; sáng +10% 6.68; tối -10% 6.64 | 35.31 | 393 |
| ổn định nhất của `no_emb_pca_raw_exposure` (33/48 cấu hình có CI > 0,5) | no_emb_pca_raw_exposure | max_depth=4, min_samples_leaf=100, l2_regularization=10.0, max_iter=10 | 0.584 [0.507; 0.677] | JPEG q70 4.08; sáng +10% 5.08; tối -10% 5.07 | 32.5 | 354 |
| `quality_only` | quality_only | — | 0/48 cấu hình có CI > 0,5 | — | — | — |
| **được chọn** | all | max_depth=4, min_samples_leaf=40, l2_regularization=1.0, max_iter=10 | 0.593 [0.541; 0.661] | JPEG q70 0.0; sáng +10% 0.0; tối -10% 0.0 | 33.75 | 226 |

Mục tiêu ≤ 5 điểm trên validation: đạt. Lệch trung vị chỉ cho biết hơn nửa số ảnh giữ nguyên điểm; cột p90 cho thấy phần đuôi vẫn lệch lớn. Toàn bộ lưới nằm trong `data-li/features/image_robust.json` và `docs/listing_intel_results.json`. AUC ở bảng này tính trên feature tính lại từ ảnh (lệch tối đa 2.0e-04 so với bảng feature), nên có thể khác mục 5 (tính trên bảng feature) ở chữ số thứ ba. Lưới này và công thức ở phần sau được thiết kế trên feature tính thẳng từ ảnh thu nhỏ, chưa qua bước `as_trained` của runtime; số đo lại qua đường runtime ở cuối mục.

### Công thức ảnh đang phục vụ, thiết kế trên validation

Thiết kế chỉ trên 507 ảnh validation tiki26 đã biến đổi (không dùng test). Quy tắc chọn: mọi lệch trung vị ≤ 5.0, rồi p90 lớn nhất nhỏ nhất. Độ nét dùng `sharpness_rel` = log phương sai Laplacian − 2·log độ lệch chuẩn mức xám, nên không đổi khi cả ảnh tối đi; cờ `exposure_ok` theo đúng luật `too_dark`/`too_bright` của `vision.quality_issues`; cờ `contrast_ok` khi độ tương phản ≥ ngưỡng.

| Ứng viên | Trọng số | Lệch trung vị | p90 lệch | AUC validation [CI95] |
|---|---|---|---|---|
| li-1.3 | công thức li-1.3 | JPEG q70 3.68; sáng +10% 4.84; tối -10% 6.73 | JPEG q70 12.05; sáng +10% 16.6; tối -10% 16.29 | 0.557 [0.454; 0.618] |
| c1_semantic_0.2 | sharpness 0.25, exposure_ok 0.1, contrast_ok 0.1, border 0.15, no_text 0.15, resolution 0.05, sim_title 0.1, sim_category 0.1 | JPEG q70 3.28; sáng +10% 4.27; tối -10% 6.75 | JPEG q70 12.71; sáng +10% 14.22; tối -10% 14.87 | 0.544 [0.438; 0.614] |
| c2_semantic_0.1 | sharpness 0.3, exposure_ok 0.1, contrast_ok 0.1, border 0.2, no_text 0.15, resolution 0.05, sim_title 0.05, sim_category 0.05 | JPEG q70 3.92; sáng +10% 4.98; tối -10% 7.28 | JPEG q70 10.99; sáng +10% 12.66; tối -10% 13.31 | 0.534 [0.422; 0.615] |
| c3_semantic_0.3 | sharpness 0.2, exposure_ok 0.1, contrast_ok 0.1, border 0.15, no_text 0.1, resolution 0.05, sim_title 0.15, sim_category 0.15 | JPEG q70 3.51; sáng +10% 4.33; tối -10% 5.71 | JPEG q70 13.73; sáng +10% 15.86; tối -10% 16.45 | 0.548 [0.448; 0.612] |
| c4_no_semantic | sharpness 0.35, exposure_ok 0.1, contrast_ok 0.1, border 0.25, no_text 0.15, resolution 0.05 | JPEG q70 4.03; sáng +10% 5.15; tối -10% 7.31 | JPEG q70 10.93; sáng +10% 13.26; tối -10% 12.3 | 0.529 [0.405; 0.615] |
| c5_rel_sharp_no_semantic | sharpness_rel 0.35, exposure_ok 0.1, contrast_ok 0.1, border 0.25, no_text 0.15, resolution 0.05 | JPEG q70 3.58; sáng +10% 4.83; tối -10% 0.73 | JPEG q70 10.28; sáng +10% 14.45; tối -10% 4.84 | 0.489 [0.388; 0.562] |
| c6_rel_sharp_semantic_0.1 | sharpness_rel 0.3, exposure_ok 0.1, contrast_ok 0.1, border 0.2, no_text 0.15, resolution 0.05, sim_title 0.05, sim_category 0.05 | JPEG q70 3.48; sáng +10% 4.77; tối -10% 1.35 | JPEG q70 10.4; sáng +10% 15.0; tối -10% 5.96 | 0.494 [0.401; 0.567] |
| c7_rel_sharp_semantic_0.2 | sharpness_rel 0.25, exposure_ok 0.1, contrast_ok 0.1, border 0.15, no_text 0.15, resolution 0.05, sim_title 0.1, sim_category 0.1 | JPEG q70 3.28; sáng +10% 4.72; tối -10% 2.29 | JPEG q70 11.57; sáng +10% 16.34; tối -10% 9.22 | 0.499 [0.418; 0.571] |
| **c8_rel_sharp_flags_0.05** | sharpness_rel 0.3, exposure_ok 0.05, contrast_ok 0.05, border 0.3, no_text 0.15, resolution 0.05, sim_title 0.05, sim_category 0.05 | JPEG q70 2.75; sáng +10% 4.66; tối -10% 1.19 | JPEG q70 9.9; sáng +10% 13.26; tối -10% 5.75 | 0.489 [0.381; 0.578] |

Được chọn: `c8_rel_sharp_flags_0.05` (trọng số đang phục vụ khớp: True). AUC validation của công thức chỉ để tham khảo: công thức là thực hành tốt (`practice`), không phải mô hình dự báo bán chạy.

### Đo lại qua đường phục vụ (`as_trained`)

Đo lại trên 507 ảnh validation theo đúng đường phục vụ: ảnh validation → biến đổi → image_load.as_trained (thu về 256 px, JPEG q85) → feature, như lúc phục vụ. Chỉ báo cáo, không đổi thiết kế.

| Cách chấm | Lệch trung vị | p90 lệch | AUC validation [CI95] |
|---|---|---|---|
| Công thức ảnh đang phục vụ | sáng +10% 4.14; tối -10% 3.19; JPEG q70 2.9 | sáng +10% 12.69; tối -10% 9.49; JPEG q70 10.27 | 0.486 [0.376; 0.575] |
| Model ảnh học (không phục vụ) | sáng +10% 0.0; tối -10% 0.0; JPEG q70 0.0 | lớn nhất 36.0 | 0.561 [0.497; 0.650] |

Ảnh gốc qua `as_trained` so với bảng feature: điểm công thức lệch trung vị 0.68, p90 2.64 điểm phân vị; feature lệch tối đa 0.3716.

### Điền feature cho listing không ảnh

Quy tắc đang dùng (`meta.image_impute`): listing không có ảnh được điền các feature ảnh bằng vector của một ảnh train thật trong cùng nhóm, chọn là ảnh làm điểm trung bình của model gộp thấp nhất khi thay vào 200 dòng train của nhóm (cột thị hiếu để trống như lúc phục vụ); chỉ dùng train. So với cách điền q10 từng feature, tỉ lệ dòng tiki26 có ảnh mà bản bỏ ảnh rồi điền lại lại được model gộp chấm cao hơn bản có ảnh:

| Tập | Số dòng | Điền q10 từng feature | Điền bằng ảnh train làm điểm thấp nhất (đang dùng) |
|---|---|---|---|
| val | 507 | 44.4% | 0.6% |
| test | 782 | 43.0% | 0.8% |

Cách điền được chọn theo số validation; vector điền chỉ chọn trên train. Dòng test chỉ để mô tả.

## 10. Thay đổi so với phiên bản trước

| Chỉ số | li-1.0 (2026-10-21) | li-1.1 (2026-10-21) | li-1.2 (2026-10-21) | li-1.3 (2026-10-21) | li-1.4 (2026-10-21) | li-1.5 (2026-10-21) | li-1.6 (2026-10-21) |
|---|---|---|---|---|---|---|---|
| ROC-AUC model gộp, test tiki26 | 0.619 [0.529; 0.735] | 0.626 [0.539; 0.753] | 0.626 [0.539; 0.753] | 0.626 [0.539; 0.753] | 0.626 [0.539; 0.753] | 0.626 [0.539; 0.753] | 0.626 [0.539; 0.753] |
| AUC trong nhóm, test tiki26 | 0.642 | 0.651 | 0.651 | 0.651 | 0.651 | 0.651 | 0.651 |
| Model trục ảnh học có giám sát, test tiki26 | 0.539 | 0.528 | 0.528 | 0.486 | 0.486 | 0.486 | 0.486 |
| Trục ảnh đang phục vụ, test tiki26 | 0.539 (model) | 0.528 (model) | 0.528 (model) | 0.486 (model) | chưa đo (công thức) | 0.561 (công thức) | 0.561 (công thức) |
| Chênh với baseline mạnh nhất trên test | +0.0194 [-0.091; 0.117] (`TF-IDF tiêu đề + logistic`) | +0.0259 [-0.071; 0.119] (`TF-IDF tiêu đề + logistic`) | +0.0259 [-0.071; 0.119] (`TF-IDF tiêu đề + logistic`) | +0.0259 [-0.071; 0.119] (`TF-IDF tiêu đề + logistic`) | +0.0259 [-0.071; 0.119] (`TF-IDF tiêu đề + logistic`) | +0.0259 [-0.071; 0.119] (`TF-IDF tiêu đề + logistic`) | +0.0259 [-0.071; 0.119] (`TF-IDF tiêu đề + logistic`) |
| Bất biến ảnh: lệch trung vị (điểm phân vị) | sáng +10% 9.8; tối -10% 8.65; JPEG q70 10.63 | sáng +10% 13.16; tối -10% 14.39; JPEG q70 13.01 | sáng +10% 13.16; tối -10% 14.39; JPEG q70 13.01 (model) | sáng +10% 0.0; tối -10% 0.0; JPEG q70 0.0 (model) | sáng +10% 3.85; tối -10% 0.93; JPEG q70 2.63 (formula) | sáng +10% 4.3; tối -10% 2.81; JPEG q70 2.59 (formula) | sáng +10% 4.3; tối -10% 2.81; JPEG q70 2.59 (formula) |
| Chế độ chấm trục | model (cả 3 trục) | model (cả 3 trục) | image: model, text: formula, market: model | image: model, text: formula, market: model | image: formula, text: formula, market: model | image: formula, text: formula, market: model | image: formula, text: formula, market: model |
| Nhãn chứng cứ | image: practice, text: practice, tags: practice, market: practice, trend: practice | image: practice, text: practice, tags: practice, market: practice, trend: practice | image: practice, text: practice, tags: practice, market: practice, trend: practice | image: practice, text: practice, tags: practice, market: practice, trend: practice | image: practice, text: practice, tags: practice, market: practice, trend: practice | image: practice, text: practice, tags: practice, market: practice, trend: practice | image: practice, text: practice, tags: practice, market: practice, trend: practice |

<!-- manual:changes -->
- li-1.0 → li-1.1: embedder chạy từng ảnh và từng tiêu đề một (batch 1) nên vector không còn phụ thuộc lô. Đã nhúng lại 45.573 tiêu đề, 3.997 ảnh tiki26 và 5.000 cặp tikifashion, rồi dựng lại context và `table.parquet`.
- li-1.0 → li-1.1: khớp từ khoá trend dùng một hàm chung `features.trend_matches` / `features.trend_demand` cho cả feature lúc học và trục trend lúc chạy (bỏ bản sao trong `peers.py`). Ngưỡng nằm trong context (`thresholds.json`) và `meta.thresholds.trend_match_cos`; nhánh vector bị tắt sau hiệu chỉnh (mục 8). Tỉ lệ dòng khớp ≥ 1 từ khoá: tiki23 87,2% → 2,5%, tiki26 78,9% → 8,2%.
- li-1.0 → li-1.1: kNN của dòng train bỏ mọi láng giềng cùng seller (trước đây chỉ bỏ chính dòng đó). `knn_dup_count` trung bình ở tiki26: train 1,20 → 0,52; val 0,62 → 0,63; test 0,41 → 0,42.
- li-1.0 → li-1.1: báo cáo cả hai cách chọn baseline (mạnh nhất trên test để gắn nhãn, mạnh nhất trên validation để tham khảo). Ablation và nhãn chứng cứ tính trên cùng test tiki26 với phép so baseline.
- li-1.0 → li-1.1: "Top 20% trúng" là kỳ vọng khi phá hoà ngẫu nhiên, không còn phụ thuộc thứ tự dòng. Baseline có cột `group` ghi "+ nhóm".
- li-1.0 → li-1.1: phân phối tham chiếu `score_dist`, `axis_dist` lưu `.npz`, nên bundle không còn file parquet.
- li-1.0 → li-1.1: thử 2 feature chữ trên validation (mục 4). Không feature nào đạt quy tắc, nên không giữ.
- li-1.0 → li-1.1: bộ thu trend (`collect_trend_keywords --refresh`) lấy từ khoá chưa có dữ liệu trước rồi mới tới từ khoá cũ.
- li-1.0 → li-1.1: các câu khẳng định về dữ liệu trong báo cáo được sinh từ kết quả; cửa sổ "đỉnh trước dịp" ghi đúng là độ lệch −4 … 0 tuần; tiêu chí 4 có bảng riêng.
- li-1.0 → li-1.1: ở li-1.1, bất biến ảnh vẫn không đạt và lệch lớn hơn li-1.0 (trung vị 13,0–14,4 điểm so với 8,7–10,6). Vector trong bảng và vector tính lại lúc chạy nay trùng nhau (lệch 0,0 điểm, hết lệch train/serve), nên phần còn lại đến từ chính model trục ảnh: chỉ đổi vector (cos 0,973–0,979 sau biến đổi) đã làm lệch khoảng 10 điểm. Model này chạy đủ 400 vòng trên 2.709 dòng và AUC test chỉ 0,528, tức gần ngẫu nhiên. Ở li-1.1 không chỉnh siêu tham số vì test đã chấm; việc này để cho phiên bản sau, chọn trên validation.
- li-1.1 → li-1.2: trục học có giám sát chỉ được hiển thị như điểm model khi cận dưới CI95 ROC-AUC trên validation (tiki26 và gộp) lớn hơn 0,5; nếu không, trục chuyển sang công thức minh bạch (`formulas.py`), chấm bằng phân vị so với listing Tiki cùng nhóm, nhãn `practice`. Quyết định chỉ dùng validation. Kết quả: trục chữ chuyển sang công thức (validation tiki26 0,462 [0,383; 0,589]), trục ảnh (0,632 [0,548; 0,684]) và thị hiếu (0,616 [0,544; 0,703]) giữ model. Model gộp và các model trục học lại tất định, giống hệt li-1.1 từng byte, nên mọi số trên test không đổi. Bất biến ảnh của trục đang phục vụ (model) vẫn không đạt (13,0–14,4 điểm); công thức ảnh (không phục vụ) lệch 2,3–7,3 điểm, cũng chưa đạt ở trường hợp tối −10%.
- li-1.2 → li-1.3: (1) Trục ảnh chọn lại trên validation: dựng tập biến đổi (sáng ±10%, JPEG q70) từ 507 ảnh validation tiki26, thử 241 cấu hình HGB (5 bộ cột × độ sâu × lá tối thiểu × L2 × số vòng, cộng cấu hình li-1.1; giá trị max_iter 10 và 25 được thêm sau lượt đầu, khi lượt đầu (≥ 50 vòng) chỉ đạt 5,78 điểm, vẫn chỉ trên validation) và chọn cấu hình có CI > 0,5 với lệch trung vị nhỏ nhất: `max_depth=4, min_samples_leaf=40, l2_regularization=1, max_iter=10`, đủ 31 cột ảnh. Trên validation: AUC 0,592 [0,540; 0,661], lệch trung vị 0,0 điểm (li-1.1: 8,7–10,4) nhưng p90 vẫn 33,8. Test chấm lại một lần (đã xem test ở li-1.0, li-1.1, li-1.2): lệch trung vị 0,0/0,0/0,0 (đạt), p90 24,6–27,8; AUC trục ảnh trên test 0,486 [0,407; 0,561], tức không hơn ngẫu nhiên, dù validation chọn nó. (2) Công thức chữ chỉ dùng tiêu đề và chất liệu khai báo, trừ 0,15 cho mỗi thuộc tính bắt buộc còn thiếu (chất liệu, màu, size theo nhóm). Model gộp, model chữ và model thị hiếu giống hệt li-1.2 từng byte; số trên test của model gộp không đổi.
- li-1.3 → li-1.4: trục ảnh phục vụ bằng công thức minh bạch (`practice`), không dùng model học. Lý do lấy từ validation: model ảnh chỉ ổn định khi giảm còn 10 vòng và p90 lệch vẫn 33,8 điểm. Kết quả âm của model ảnh được giữ lại: validation 0,593 [0,541; 0,661], test 0,486 [0,407; 0,561], p90 lệch trên test 24,6–27,8. Công thức ảnh được làm bền với phơi sáng và chọn chỉ trên 507 ảnh validation đã biến đổi: độ nét chuẩn hoá theo độ tương phản, cờ phơi sáng theo luật `too_dark`/`too_bright`, cờ tương phản ≥ 0,1, cùng độ đồng màu viền, chữ đè, cạnh ngắn, độ khớp tiêu đề và danh mục. Trên validation: lệch trung vị sáng +10% 4,7, tối −10% 1,2, JPEG q70 2,8; p90 lần lượt 13,3, 5,8, 9,9. Test chấm một lần (lần đọc test thứ năm, đã công bố): lệch trung vị sáng +10% 3,9, tối −10% 0,9, JPEG q70 2,6 (đạt); p90 lần lượt 14,2, 5,6, 9,3. Model gộp và mọi file model giống hệt li-1.3 từng byte.
- li-1.4 → li-1.5 (đợt sửa go-live): chỉ đổi meta, reference và báo cáo. `fusion.joblib`, ba file `axis_*.joblib`, `score_dist`, `axis_dist`, `formula_dist` và mọi bảng kNN giống hệt li-1.4 từng byte (so sha256), nên mọi dòng số cũ trên test và validation không đổi. Thay đổi: (1) bảng kết quả tách "Model trục …: học có giám sát, không phục vụ" khỏi "Công thức trục …: đang phục vụ" và thêm AUC của công thức đang phục vụ (ảnh: validation 0,489 [0,381; 0,578], test 0,561 [0,443; 0,631]; chữ: validation 0,577 [0,411; 0,696], test 0,576 [0,500; 0,642]), đo hậu kiểm, không dùng để quyết định; (2) lý do chuyển trục ảnh sang công thức không còn viết cứng con số mà đọc từ kết quả độ bền đã lưu `reference/image_design.json`; (3) nhãn chấm tay hiệu chỉnh trend lưu từng cặp trong `reference/trend_calib_judged.json`; (4) `pca.joblib` đổi sang `pca.npz` (chiếu tay, khớp sklearn tuyệt đối trên 500 vector: lệch 0,0); (5) danh sách 45 từ khoá trend có chuỗi lúc học được khoá trong `thresholds.json`, nên thu thêm từ khoá sau này không lặng lẽ đổi feature; (6) meta có `feature_availability`, `image_impute`, `feature_constants` (tính trên train) để runtime che feature mà nhóm chưa từng có lúc học, đặt về hằng số những feature chỉ có một giá trị lúc học, và điền feature ảnh cho listing không ảnh (cột thị hiếu để trống). Điền bằng q10 từng feature như kế hoạch ban đầu làm listing không ảnh điểm cao hơn chính nó khi có ảnh ở 44,4% dòng validation tiki26, nên `image_impute` dùng vector của ảnh train làm điểm model gộp thấp nhất trong nhóm (0,6% dòng validation); (7) bất biến ảnh đo lại qua `image_load.as_trained` như lúc phục vụ: test trung vị sáng +10% 4,3, tối −10% 2,8, JPEG q70 2,6 (vẫn đạt, tối −10% tăng từ 0,9), p90 14,7, 10,1, 11,1; validation trung vị 4,1, 3,2, 2,9. Hàng "Bất biến ảnh" ở bảng trên cho li-1.5 vì vậy đo theo đường phục vụ, các cột trước đo thẳng trên ảnh thu nhỏ.
- li-1.5 → li-1.6 (đợt sửa cuối): chỉ đổi `reference/top_medians.json` và `meta.model_version`. Lời khuyên "thêm ảnh" (`no_images`) nay thay cả 31 cột ảnh (không chỉ `n_images`, cột này trống toàn bộ ở fashion, home, sport lúc học) bằng trung vị listing top25 cùng nhóm, nên có impact thay vì `None`; trung vị cũ của mọi cột khác giữ nguyên (đã so). Model, `score_dist`, `axis_dist`, `formula_dist` và kNN giống hệt li-1.5 từng byte, điểm tổng không đổi. Không chạy lại `train`, `evaluate` hay test: cột li-1.6 ở bảng trên chép số test của li-1.5; báo cáo dựng lại từ `docs/listing_intel_results.json` với mục 11 đo lại.
<!-- /manual:changes -->

## 11. Dữ liệu VietCraft (Mongo local)

Đo ngày 2026-10-21 trên Mongo local `vietcraft-test`: 29 sản phẩm của 8 shop, 16 có ảnh tải được. Nhóm: fashion 17, sport 3, accessories 3, bags 3, home 2, shoes 1. Chạy `intel.analyze` không ghi gì (`persist=False`, `store_embeddings=False`).

- Độ phủ trục (có điểm): Ảnh 55.2%, Từ khoá (chữ) 100.0%, Tag 100.0%, Thị hiếu và cạnh tranh 44.8%, Trend và mùa vụ 100.0%.
- Điểm tổng: nhỏ nhất 0.84, tứ phân vị 2.86 / 8.12 / 48.0, lớn nhất 100.0. Trung vị có ảnh 20.03, không ảnh 2.86.
- Lời khuyên "thêm ảnh" ở 13 listing chưa có ảnh: 12 có impact > 0, trung vị +19.6 điểm (từ 0.0 đến 66.8). Đây là ước tính khi thay feature ảnh bằng trung vị listing top25 cùng nhóm, không phải cam kết.
- PSI: 10 bin theo phân vị Tiki train cùng nhóm, chỉ trên giá trị không thiếu, chỉ cho nhóm có ≥ 5 sản phẩm.

- Nhóm `fashion` (17 sản phẩm, 8 có ảnh): 22/30 feature có PSI > 0,25. Lệch lớn nhất (PSI; trung vị Tiki train → VietCraft): `img_sharpness` 5.85 (4.551 → 3.578); `img_brightness` 5.75 (0.662 → 0.781); `img_border_uniform` 5.11 (0.611 → 0.958); `knn_price_pct` 4.2 (55.0 → 92.5); `sim_category` 3.98 (0.098 → 0.088); `top_centroid_margin` 3.98 (-0.006 → -0.01); `kw_lift_max` 3.26 (0.356 → 0.204); `sim_title` 3.07 (0.125 → 0.116).

5 sản phẩm có ảnh điểm tổng cao nhất:

| Sản phẩm | Nhóm | Điểm tổng | Ảnh | Từ khoá (chữ) | Tag | Thị hiếu và cạnh tranh | Trend và mùa vụ |
|---|---|---|---|---|---|---|---|
| Balo Vải Canvas Phủ Chống Nước Ngăn Laptop 15.6 inch Đi Học | bags | 100.0 | 2.5 | 99.7 | 100.0 | — | 75.0 |
| ÁO KHOÁC LÔNG CỪU NHIỀU MÀU VẢI DÀY PHÙ HỢP MÙA ĐÔNG | fashion | 93.4 | 28.1 | 30.6 | 56.2 | 88.2 | 65.6 |
| Khăn Pandama buộc đầu phong cách miền viễn tây | accessories | 84.4 | 39.4 | 54.8 | 25.0 | — | 50.0 |
| Áo Khoác Lông Cropped Bolero Dáng Ngắn Cổ Bẻ Phong Cách Y2K | fashion | 72.6 | 54.5 | 17.0 | 6.2 | 6.8 | 65.6 |
| Áo Thun Nam Nữ Form Rộng The Bad God Serenity Cotton Cổ Tròn | fashion | 48.6 | 14.6 | 53.9 | 78.1 | 67.8 | 12.5 |

<!-- manual:vietcraft -->
Đọc kết quả:

- **Dữ liệu mô phỏng (D12).** Không có doanh số thật, nên phần này chỉ đo độ phủ, phân phối và độ lệch, không đo độ đúng. Atlas có 79 sản phẩm thật nhưng chưa được chấm: lần chạy chỉ đọc trên Atlas ở readiness audit bị chặn quyền.
- **Mã đã dùng.** Số đo chạy lại ngày 21/10 trên mã runtime cuối (li-1.6): có bước che, đặt hằng số và điền feature (`fusion.served` đọc `feature_availability`, `feature_constants`, `image_impute`) và sàn "điểm có ảnh ≥ điểm khi bỏ ảnh". Lần đo trước chạy trước khi `feature_constants` được áp, nên trung vị điểm tổng giảm từ 20,15 xuống 8,12 (có ảnh 33,3 → 20,03; không ảnh 4,23 → 2,86). li-1.6 không đổi điểm, chỉ đổi impact của lời khuyên.
- **Lời khuyên "thêm ảnh".** Trước li-1.6, listing không ảnh của fashion, home, sport nhận impact `None` cho "Thêm ít nhất 3 ảnh", và lời khuyên này có thể bị đẩy ra khỏi 6 mục. Nay 12/13 listing không ảnh có impact > 0 (trung vị +19,6 điểm), và mục có impact lớn nhất luôn được giữ. FE hiện "Điểm tổng thấp vì sản phẩm chưa có ảnh" kèm số này (cờ `capped_reason`).
- **Trang danh sách.** `shop_summary` dùng luôn điểm vừa tính trong request (tối đa 20 sản phẩm mỗi lượt), nên trên production, nơi không ghi điểm, trang danh sách vẫn có điểm thay vì "—".
- **Listing không ảnh nằm gần đáy.** Lý do: nó được điền như ảnh train kém nhất trong nhóm (mục 9). Trước đợt sửa, readiness audit đo ngược lại: trung vị không ảnh 48, có ảnh 26.
- **PSI chỉ là dấu hiệu.** PSI tính trên số ít sản phẩm fashion có ảnh, nên bị phóng đại bởi các bin rỗng. Hướng lệch nên đọc ở trung vị:
  - ảnh VietCraft là mockup nền trơn: độ đồng màu viền cao hơn hẳn, ảnh sáng hơn và kém nét hơn;
  - giá cao hơn hàng Tiki giống nó (phân vị giá trong láng giềng kNN).
- **Điểm tổng lệch hẳn khỏi các trục (C1).** Ví dụ đầu bảng (balo, nhóm `bags`) có điểm tổng 100 trong khi trục ảnh rất thấp.
  - Nhóm `bags` chỉ có ở tiki23, không có ảnh lúc học. Vì vậy model gộp che toàn bộ feature ảnh và chấm theo chữ và giá; còn trục ảnh là một công thức riêng.
  - Điểm tổng là phân vị của model gộp so với listing Tiki cùng nhóm. Các trục là chỉ số riêng, không cộng lại thành điểm tổng. FE có InfoTip giải thích điều này.
- **Kết luận.** Listing VietCraft nằm ngoài phân phối Tiki ở phần lớn feature. Điểm tổng là xếp hạng tham khảo, nhãn `practice`, không phải dự báo bán hàng trên VietCraft.
<!-- /manual:vietcraft -->

## 12. Điểm yếu và ảnh hưởng

<!-- manual:weakness -->
Bảng này gộp hai nguồn:
- bản nháp `docs/LISTING_INTEL_WEAKNESSES_DRAFT.md`, viết trước Task 10;
- các phát hiện sau đó: readiness audit, kiểm thử E2E, review vòng lặp li-1.1 → li-1.4, và đợt sửa go-live. Đợt sửa go-live gồm: AI runtime, báo cáo và meta (li-1.5), FE, BE.

Cách đọc bảng:
- Mã D, P, K, V lấy theo bản nháp. Mã M (model và đánh giá), G (go-live) và E (giao diện) là các mục mới.
- Mức (cao, trung bình, thấp) là đánh giá của người viết.
- Số trong bảng lấy từ `docs/listing_intel_results.json`, trừ một số mục lấy từ audit:
  - readiness audit: 394 MB, 7 GB, 13,9 s, 48 so với 26, 9/79;
  - báo cáo đợt go-live của nhóm AI: 0,18 s, 42,9 điểm;
  - bản nháp: 26% dòng OEM, khoảng 15% khớp nhầm.
- Trạng thái có bốn loại:
  - **đã sửa**: kèm số đo hoặc test;
  - **giới hạn chấp nhận**: đã công bố, không sửa trong phạm vi này;
  - **còn mở**.
- "(AI)", "(FE)", "(BE)" cho biết nhóm nào sửa trong đợt go-live; "(li-1.5)", "(li-1.6)" là thay đổi meta, reference và báo cáo.

### Dữ liệu

| Mã | Điểm yếu | Ảnh hưởng tới | Mức | Cách xử lý | Trạng thái |
|---|---|---|---|---|---|
| D1 | Không có dữ liệu Việt về đồ thủ công hay POD: học trên Tiki, chấm VietCraft. Ánh xạ danh mục chỉ gần đúng; danh mục ngoài `category_map.json` có nhóm `None` | mọi trục, điểm tổng | cao | Đo độ lệch ở mục 11: phần lớn feature của nhóm fashion có PSI > 0,25. `feature_availability` che các feature mà nhóm chưa từng có lúc học | giới hạn chấp nhận (đã đo) |
| D2 | Nhãn `top25` dựa trên `quantity_sold` tích luỹ, nhiễu bởi quảng cáo và tuổi listing; là tương quan, không phải nhân quả | mọi model, lời khuyên | cao | Chuẩn hoá theo tuổi ở tiki23, so trong nhóm, cổng chứng cứ | giới hạn chấp nhận |
| D3 | tiki26 nhỏ: 3.998 dòng, 3 nhóm; test 782 dòng / 234 cụm seller. CI rộng, ví dụ model gộp [0,539; 0,753], và chỉ dùng 200 lần bootstrap | mọi số test | cao | Bootstrap theo cụm seller; không diễn giải chênh nhỏ | giới hạn chấp nhận |
| D4 | tiki26 không có `seller_id`. Nhóm tách theo brand; khoảng 26% dòng OEM hoặc không brand thành từng cụm 1 dòng, nên có thể vẫn chung shop ẩn | CI (có thể lạc quan) | trung bình | Kiểm tra 0 seller hoặc brand nằm ở 2 tập (mục 9) | giới hạn chấp nhận |
| D5 | tiki23 không có ảnh và là dữ liệu 2023. Hai nguồn không chung nhóm nào, nên cột `group` cũng nhận diện nguồn | ảnh, thị hiếu, mọi AUC gộp | trung bình | Báo AUC trong nhóm; báo test lệch thời gian (mục 7) | giới hạn chấp nhận |
| D6 | tiki26 không có mô tả: `desc_len = 0` với mọi dòng train của fashion, home, sport. Mô tả VietCraft vì vậy nằm ngoài phân phối | điểm tổng | trung bình | `meta.feature_constants` ghi giá trị duy nhất lúc học (0). Runtime đặt các feature này về hằng số đó cho model gộp, khớp lúc học; đổi này làm điểm gốc của sản phẩm local dịch tới 42,9 điểm | đã sửa và đo lại: meta (li-1.5), runtime áp (AI); mục 11 đo lại trên mã cuối, trung vị điểm tổng local 20,15 → 8,12 |
| D7 | Bỏ các cột là đáp án (review, rating, order…), nên chỉ còn nội dung, giá và metadata | điểm tổng | trung bình | Có chủ đích; kiểm tra "cột cấm" (mục 9) | giới hạn chấp nhận |
| D8–D10 | `tikireviews`: nhóm `home` là rổ gom, `shoes` bị bỏ, `sport` không có chỉ số; xu hướng trong năm vẫn còn | trend (mùa vụ nhóm) | trung bình | Coi là nhu cầu Tiki chung; detrend theo năm | giới hạn chấp nhận |
| D11 | tiki23 có `age_days` ngoại lai; tỉ lệ chia tập lệch 70/15/15 vì tách theo seller | nhãn, bảng dữ liệu | thấp | `age_days` không là feature; báo tỉ lệ thực | còn mở (không ảnh hưởng model) |
| D12 | Dữ liệu VietCraft local là mô phỏng; 79 sản phẩm thật trên Atlas chưa được chấm | mục 11, mọi kết luận về VietCraft | cao | Chỉ đo độ phủ, phân phối và độ lệch | giới hạn chấp nhận |
| D13 | VietCraft local: 13/29 sản phẩm không có ảnh tải được | ảnh, thị hiếu, điểm tổng | trung bình | Trục ảnh trả `null` kèm lý do; điểm tổng của listing không ảnh dùng cách điền ở P18 | đã sửa (mục 11) |
| D14 | Chuỗi trend dừng ở 2026-08-16 (khoảng 9 tuần); 15 từ khoá chưa thu (mục 8) | trend, `/trends/calendar` | trung bình | Chạy collector hoặc GitHub Action. Runtime đọc trend từ Mongo cấu hình hoặc từ snapshot `reference/trend_weekly.json` | còn mở (dữ liệu); đã sửa nguồn đọc (AI) |
| D15 | Lỗi làm sạch và chia tập lúc đầu (seller NaN, id trùng, review lẫn khối lượng theo năm) | nhãn, trend | trung bình | Vòng sửa của Task 1 | đã sửa |

### Model và đánh giá

| Mã | Điểm yếu | Ảnh hưởng tới | Mức | Cách xử lý | Trạng thái |
|---|---|---|---|---|---|
| M1 | Model gộp không thắng có ý nghĩa baseline mạnh nhất trên test (TF-IDF): +0,0259 [−0,071; 0,119] | nhãn chứng cứ, lời khuyên | cao | Mọi trục mang nhãn `practice`, không có "đã đo"; báo cả phép so với baseline mạnh nhất trên validation (chỉ tham khảo) | giới hạn chấp nhận |
| M2 | Test đã đọc 7 lần; các quyết định ở li-1.2 → li-1.4 đều đưa ra sau một lần đọc test; validation đóng 5 vai | độ tin của mọi số test và validation | cao | Liệt kê đủ ở mục 3; mọi lựa chọn đều ghi lý do trên validation | giới hạn chấp nhận (đã công bố) |
| M3 | Model ảnh học có giám sát không tổng quát: validation 0,592, test 0,486. Công thức ảnh đang phục vụ: validation 0,489, test 0,561 (đo hậu kiểm) | trục ảnh | trung bình | Trục ảnh là điểm thực hành tốt (`practice`), không phải dự báo bán chạy | giới hạn chấp nhận |
| M4 | Model chữ bị thay bằng công thức (validation tiki26 0,462) dù test đạt 0,590; công thức chữ: validation 0,577, test 0,576 | trục chữ | thấp | Quy tắc cổng "mọi tập validation" cố định trước khi xem; số công thức ở mục 5 | giới hạn chấp nhận |
| M5 | Bất biến ảnh chỉ đạt theo trung vị; phần đuôi còn lớn. Test qua `as_trained`: p90 14,7 (sáng +10%) | trục ảnh | trung bình | Công thức bền với phơi sáng; đo lại qua đường phục vụ (mục 9) | giới hạn chấp nhận (đã đo lại) |
| M6 | Tiêu chí 4 chỉ đạt ở mốc cuối (66,7%); trung bình 6 mốc là 48,9%. Runtime `h(d)` không dùng dự báo đó | trend | trung bình | Mục 8 ghi rõ runtime dùng mùa × đà tăng; đỉnh trước dịp ở 84,6% cặp | giới hạn chấp nhận |
| M7 | Khớp vector cho trend không dùng được (1/100 cặp đúng), nên chỉ còn khớp chữ: độ phủ 2,5% (tiki23) / 8,2% (tiki26). Lệch spec §5 | trend | trung bình | Tắt nhánh vector (`trend_match_cos = None`) | giới hạn chấp nhận |
| M8 | Kiểm tra xáo trộn nhãn không bắt được rò rỉ qua feature suy từ nhãn | lập luận chống rò rỉ | thấp | Lift và centroid là out-of-fold (5 fold theo seller); kNN loại cả seller; PCA, giá trung vị và kNN fit trên train | giới hạn chấp nhận |
| M9 | `group_season` gộp mọi năm (nhìn trước nhẹ với tiki23); 46 dòng val/test trùng tên seller với train của nguồn kia, chỉ ảnh hưởng tập gộp | trend, tập gộp | thấp | Không tính vào tiêu chí đạt | giới hạn chấp nhận |
| M10 | Quần thể tham chiếu sẽ lấy cả dòng train và test cho nhóm có < 20 dòng validation; hiện mọi nhóm đều đủ 20 dòng | phân vị | thấp | Đổi sang rơi về phân phối "all" của validation | còn mở (tiềm ẩn, chưa xảy ra) |
| M11 | Hai bản sao chỉ dùng offline: `trend_eval.factor` (hệ số chưa cắt) và `features.exposure_ok` (khác nghĩa `formulas.exposure_ok`) | đọc báo cáo, bảo trì | thấp | Mục 8 ghi "chưa cắt [0,5; 1,5]" | còn mở (đã ghi rõ) |

### Phương pháp (từ bản nháp, cập nhật)

| Mã | Điểm yếu | Ảnh hưởng tới | Mức | Cách xử lý | Trạng thái |
|---|---|---|---|---|---|
| P1 | Tín hiệu từ nội dung yếu khi không có lịch sử bán | mọi trục | cao | Cổng chứng cứ (M1) | giới hạn chấp nhận |
| P2 | Trục tag là công thức, không học có giám sát; tag lạ được coi là trung tính | tag | trung bình | Phân vị theo nhóm VietCraft | giới hạn chấp nhận |
| P3 | `impact` là counterfactual trên model, không phải nhân quả; nhiều lời khuyên có impact 0 | lời khuyên, FE | trung bình | FE ẩn chip "+N điểm" khi impact ≤ 0 | đã sửa (FE) |
| P4 | Lexicon còn khớp nhầm ("Cam kết" thành màu cam, "may" thành mây…) | chữ, tag, lời khuyên chất liệu | trung bình | Khớp phân biệt dấu đã giảm khoảng 15%; phần còn lại cần sửa term | còn mở |
| P5 | Từ cấm viết lẫn có dấu và không dấu bị lọt | chữ (từ cấm) | trung bình | Khớp thêm trên chuỗi bỏ dấu hoàn toàn (đổi `norm` thì phải tăng phiên bản model) | còn mở |
| P6 | Heuristic chữ thô (`title_repeat_ratio`, cụm cấm chồng nhau) | chữ | thấp | Theo brief | giới hạn chấp nhận |
| P7 | Ngưỡng `text_overlay` | ảnh (vấn đề chữ đè) | trung bình | Đã đo lại trên ảnh thật ở vòng cải tiến vision, giữ ngưỡng | giới hạn chấp nhận |
| P8 | Feature ảnh học trên ảnh thu nhỏ 256 px nhưng runtime nhận ảnh gốc | ảnh, điểm tổng | cao | Runtime thu về 256 px, JPEG q85 (`image_load.as_trained`). Bất biến đo lại qua đúng đường này (mục 9); ảnh gốc qua `as_trained` lệch trung vị 0,34 điểm so với bảng | đã sửa và đo lại |
| P9 | Độ khớp ảnh–chữ của SigLIP2 int8 có biên nhỏ | ảnh (`sim_*`, `style_*`), trend | trung bình | Retrieval: top-1 34%, gấp 68 lần ngẫu nhiên (mục 9); tắt khớp vector cho trend (M7) | giới hạn chấp nhận |
| P10 | Bất biến ảnh trên ảnh thật | ảnh | trung bình | Xem M5 | giới hạn chấp nhận |
| P11 | Đà tăng cắt ±0,5 và `h(d)` cắt [0,5; 1,5], làm phẳng đột biến thật | trend, FE timeline | trung bình | Theo công thức dispatch | giới hạn chấp nhận |
| P12 | Seasonal naive thường thắng STL; lệch pha một tuần do bucket Chủ nhật | trend | trung bình | Báo đủ ở mục 8 (M6); runtime không dùng dự báo mức | giới hạn chấp nhận |
| P13 | Lỗi phương pháp bắt ở review: nhìn trước ở `demand_factor`, lift lệch âm, kNN tự khớp, khớp lexicon bỏ dấu quá rộng | trend, chữ, tag, thị hiếu | cao | Đã sửa kèm test | đã sửa |
| P14 | Ghi đè chế độ trục ảnh từng viết cứng "33,8" | meta, báo cáo | thấp | Lý do và quyết định đọc từ `reference/image_design.json` | đã sửa (li-1.5) |
| P15 | Nhãn chấm tay hiệu chỉnh trend chỉ có trong văn bản; mẫu bị `evaluate` ghi lại mỗi lần chạy | bằng chứng cho lệch spec §5 | thấp | Nhãn từng cặp lưu ở `reference/trend_calib_judged.json`; mẫu chỉ ghi khi chưa có | đã sửa (li-1.5) |
| P16 | Thu thêm từ khoá trend sẽ lặng lẽ đổi feature mà không tăng phiên bản | trend, điểm tổng | trung bình | Khoá 45 từ khoá lúc học trong `thresholds.json` (`trend_keywords`) | đã sửa (li-1.5, có test) |
| P17 | Phép kiểm bất biến từng đi tắt, không qua đường xử lý ảnh khi phục vụ | độ tin của số bất biến | trung bình | `imgcheck.features_for` gọi `as_trained`; thêm số validation qua đường runtime | đã sửa (li-1.5) |
| P18 | Listing không ảnh từng điểm cao hơn listing có ảnh (readiness audit: trung vị 48 so với 26) | điểm tổng | cao | Che feature theo `feature_availability`; điền feature ảnh bằng ảnh train làm điểm thấp nhất (`image_impute`), để trống cột thị hiếu. Bản bỏ ảnh cao điểm hơn bản có ảnh ở 0,6% dòng validation; nếu điền q10 thì là 44,4% (mục 9). Runtime thêm một sàn: điểm có ảnh không thấp hơn điểm của chính listing đó khi bỏ ảnh. Với cách điền này, sàn chỉ có tác dụng ở khoảng 0,6% listing validation, nên điểm có ảnh vẫn do model quyết định; nếu điền q10 thì sàn sẽ đè lên khoảng 44,4%. Local: trung vị không ảnh thấp hơn hẳn có ảnh (mục 11) | đã sửa (li-1.5 và AI); hệ quả: listing không ảnh nằm gần đáy |
| P19 | Không có trục thị hiếu cho bags, shoes, accessories vì không có chỉ mục kNN (9/79 sản phẩm trên Atlas) | thị hiếu | trung bình | Trả `null` kèm lý do | giới hạn chấp nhận |
| P20 | Listing không ảnh không có impact cho "thêm ảnh" vì `n_images` trống lúc học ở fashion, home, sport; lời khuyên có giá trị nhất có thể bị cắt khỏi 6 mục | lời khuyên, FE | trung bình | `FIXES["no_images"]` gồm cả cột ảnh, `top_medians` dựng lại; mục có impact lớn nhất luôn được giữ | đã sửa (li-1.6, có test): 12/13 listing không ảnh local có impact > 0 (mục 11) |

### Kỹ thuật và triển khai

| Mã | Điểm yếu | Ảnh hưởng tới | Mức | Cách xử lý | Trạng thái |
|---|---|---|---|---|---|
| G1 | Chốt "chỉ ghi DB local" làm rơi mọi lần ghi điểm và embedding trên Atlas: trang danh sách luôn "—", job đêm tính lại vô ích | trang danh sách, job đêm | blocker | Cờ `LI_ALLOW_REMOTE_WRITES=1` chỉ cho production; tạo index không chặn request | **tắt theo quyết định của người dùng**: tạo index đã chạy nền (AI); không có cờ ghi remote, nên production không lưu điểm và embedding (mục 3). Trang danh sách vẫn có điểm: `shop_summary` trả điểm vừa tính trong request, tối đa 20 sản phẩm mỗi lượt (AI, có test với store từ chối ghi); chi phí tính lại mỗi lượt xem vẫn còn |
| G2 | Model ONNX (394 MB) không có trên server, hạ cấp im lặng | ảnh, thị hiếu, trend | blocker | Dockerfile tải model lúc build (ghim revision HF, kiểm sha256), cảnh báo lúc khởi động, `meta.degraded` | đã sửa (AI); image chưa build thử |
| G3 | Nguồn trend mặc định là local; kết quả rỗng không được cache (+2 s mỗi lần phân tích) | trend, lịch, nguy cơ 504 | blocker | Đọc URI Mongo cấu hình (`LI_TREND_DB`), cache kết quả rỗng, fallback snapshot | đã sửa (AI) |
| G4 | Toàn bộ mã Listing Intelligence chưa commit | triển khai | blocker | Commit khi người dùng đồng ý | còn mở (chờ đồng ý) |
| G5 | Job trend hằng tuần: thiếu `trendspy`, Google trả 429 từ IP server | trend | trung bình | Thêm `trendspy`; dùng GitHub Action sẵn có | còn mở một phần: đã thêm `trendspy` (AI), collector vẫn chỉ ghi local, rủi ro 429 còn |
| G6 | Chi phí mỗi request tăng theo số peer (1.000 peer mất 13,9 s chưa cache) | độ trễ, 504 | trung bình | Cache dòng peer theo nhóm (TTL), tối đa 300 peer mới nhất | đã sửa (AI): 1.000 peer chạy ấm 0,18 s, đo trên Mongo giả lập |
| G7 | Image khoảng 7 GB vì torch bản CUDA; cần ≥ 3 GB RAM | triển khai | trung bình | Torch bản CPU | đã sửa (AI); image chưa build thử |
| G8 | Không giới hạn tần suất `/listings/intel/preview` | an ninh, tải | trung bình | BE: 20 lần/phút/người, trả 429 tiếng Việt; đếm trong bộ nhớ, theo từng tiến trình | đã sửa (BE) |
| G9 | Allowlist `res.cloudinary.com` nhận mọi tenant; tiền tố cloud bị vượt bằng `../`, `%2e%2e` và đường `/image/fetch/` | SSRF, tải, quota Cloudinary | trung bình | BE và AI: parse URL, bắt buộc `https`, host đúng `res.cloudinary.com`, chỉ nhận `/<cloud>/image/upload/…`, chặn `..`, `%2e`, `%2f`, `%5c`, `fetch:`, độ dài ≤ 2048; khi có `CLOUDINARY_CLOUD_NAME` thì cloud phải trùng. FE lọc ảnh chấm thử theo cùng quy tắc | đã sửa (BE, AI, FE; self-check BE và pytest AI). Production phải đặt `CLOUDINARY_CLOUD_NAME` |
| G10 | `?date=` nhận mọi khoảng; preview trả `product_id: null`; tag gợi ý là token brand ("mrm", "mayhomes") | API, FE | thấp | Giới hạn ±730 ngày; bỏ `product_id`; lọc tag theo lexicon, tag đã duyệt và từ có dấu | đã sửa (AI) |
| G11 | Bundle hỏng trả 500; `client.address` lỗi khi chạy sau load balancer | API | thấp | Bắt thêm lỗi khi nạp bundle | còn mở |
| G12 | Scheduler chạy theo tiến trình: chỉ được 1 worker, 1 replica | job | thấp | Ghi trong tài liệu triển khai | giới hạn chấp nhận |
| G13 | `reference/pca.joblib` là pickle trong bundle | an toàn bundle | thấp | Đổi sang `pca.npz`, chiếu bằng tay, khớp tuyệt đối | đã sửa (li-1.5) |
| G14 | Thẻ model hiện chữ cho dev ("GroupShuffleSplit…, random_state=42") | FE thẻ model | thấp | `meta.trained_on` thành câu tiếng Việt | đã sửa (li-1.5) |
| K1–K2 | Tải ảnh (SSRF qua redirect, EXIF, treo kết nối); lỗi nền embedder và vision | ảnh, chấm thử | trung bình | Vòng sửa Task 3 và 4 | đã sửa |
| K3 | Hợp đồng JSON giữa FE và AI lỏng | API, FE | trung bình | Ghim kiểu (`events`, `effort`, `trained_on`, null thay NaN) | đã sửa |
| K4 | Tải file ONNX không có checksum | triển khai | thấp | Xem G2 | đã sửa (AI) |
| K5 | Minor BE: độ dài URL, tag rỗng, NFC của `materials` | BE | thấp | Vòng dọn BE (URL ≤ 2048, cắt tag, NFC). Còn lại: mô tả và danh mục chưa trim | đã sửa phần lớn |
| K6 | Minor FE: `Step4ProductDetails.tsx` khoảng 613 dòng, modal chưa có focus trap | FE | thấp | Tách component | còn mở |
| K7 | FE thiếu lịch trend | FE, trend | trung bình | Thêm thẻ `TrendCalendar` ở trang danh sách và chi tiết | đã sửa |
| K8 | Ảnh trong luồng tạo sản phẩm thường chưa lên Cloudinary nên bị lọc khi chấm thử | chấm thử | trung bình | Copy giải thích; điểm ảnh đầy đủ sau khi đăng | giới hạn chấp nhận |
| K9 | Danh sách chất liệu ở FE trùng `lexicon.json` | chữ, FE | thấp | Đồng bộ tay | giới hạn chấp nhận |
| K10–K11 | Minor trend (client không đóng, cache không khoá) và minor khác của Task 1, 2, 9 | trend, tag | thấp | Vòng dọn sau | còn mở |
| V1 | Google Trends trả 429 nên 15 từ khoá chưa thu | trend | trung bình | Xem D14, G5 | còn mở |
| V2 | Dễ nhầm Mongo local và Atlas (`app/.env` thắng `.env`) | mọi endpoint, nguy cơ ghi nhầm | trung bình | Chạy với `MONGO_DB_LIVE=vietcraft-test`; hiện runtime chỉ ghi vào Mongo local (G1) | giới hạn chấp nhận |
| V3 | Không có lịch sử commit theo task | rollback | thấp | Xem G4 | giới hạn chấp nhận |

### Giao diện (E2E ngày 21/10)

| Mã | Điểm yếu | Ảnh hưởng tới | Mức | Cách xử lý | Trạng thái |
|---|---|---|---|---|---|
| E1 | Bảng danh sách bị cắt cột: ở 375 px chỉ thấy tên sản phẩm | trang danh sách | trung bình | Dưới md dùng danh sách thẻ (điểm, 5 thanh trục, mũi tên trend); từ md dùng bảng gọn: xu hướng và ngày cập nhật nằm dưới tên, cột trục hẹp, vẫn giữ bóng cuộn khi thiếu chỗ | đã sửa (FE) |
| E2 | Sidebar mở sẵn ở 375 px nên nội dung chỉ còn khoảng 140 px | mọi trang seller | trung bình | Thu gọn mặc định khi ≤ 767 px (chỉ lúc tải trang) | đã sửa (FE) |
| E3 | Chip vấn đề không xuống dòng, nhãn radar bị cắt, nhãn sự kiện trên timeline đè nhau | trang chi tiết, chấm thử | trung bình | Chip xuống dòng, radar thêm lề, timeline đánh số kèm chú giải | đã sửa (FE) |
| E4 | Điểm tổng và điểm trục trông mâu thuẫn (C1); câu "xếp hạng so với N listing" sai vì điểm tổng là phân vị so với listing Tiki tham chiếu | trang chi tiết | trung bình | Câu mới: "Phân vị so với listing Tiki tham chiếu nhóm …; tag và trend so với N listing VietCraft"; listing không ảnh có thông báo riêng kèm impact thêm ảnh | đã sửa (FE, AI thêm `capped_reason`) |
| E5 | Chip "+0 điểm" | lời khuyên | thấp | Ẩn khi impact ≤ 0 | đã sửa (FE) |
| E6 | Câu trong MarketPanel mơ hồ ("Cao hơn 0%") | thị hiếu | thấp | Câu đầy đủ kèm giá trung vị | đã sửa (FE) |
| E7 | Bảng từ khoá hiện lift âm thô; thông báo thị hiếu của chấm thử sai lý do khi thiếu danh mục; chip lịch gần như luôn "→ 0%" và từ khoá không liên quan dịp | từ khoá, chấm thử, lịch | thấp | Lift âm hiện "ít gặp ở nhóm bán chạy"; lý do thị hiếu theo đúng nguyên nhân (thiếu ảnh hay thiếu dữ liệu nhóm); từ khoá lịch lọc theo chủ đề của dịp (`seed_keywords` topic), xếp theo mùa vụ trong cửa sổ chuẩn bị; đà tăng hiện "chưa có dữ liệu mới" khi chuỗi dừng quá 4 tuần trước hôm nay | đã sửa (AI, FE) |
| E8 | Modal chấm thử chưa chụp lại sau đợt sửa FE: luồng tạo sản phẩm tải mockup thật lên Cloudinary | chấm thử | thấp | Modal dùng chung component với trang chi tiết đã kiểm | còn mở (kiểm tay) |
<!-- /manual:weakness -->
