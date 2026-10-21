# F35 Giá tôi đắt hay rẻ: roast và đường ra

> Endpoint `GET /api/analytics/pricing` (BE proxy `/seller/analytics/pricing`, `BE/src/app/routes.ts:42`) · Trang FE `/seller/insights/pricing` (`FE/src/modules/analytics/pages/PricingPage.tsx`) · File chính `app/api/v1/f35_pricing.py`, `app/api/v1/_live.py` · Ngày 2026-10-21 · Người viết: Claude (subagent)

## 0. Bản đăng ký nói gì

| Mục | SRS 3.9.4 Competitive Pricing Analysis (tóm tắt) |
|---|---|
| Actor | Seller đã đăng nhập, Bearer JWT |
| Trigger | Mở tab "Phân tích giá" trong Product Analytics, chọn loại sản phẩm, vào `SellerPricingAnalysisPage` |
| Endpoint | `GET /api/analytics/pricing?productType={productType}` |
| Input | `productType` (string, bắt buộc); hệ thống lấy `sellerId` từ JWT, giá đối thủ từ "competitor scan cache", giá của seller nếu có listing loại đó |
| Output | Dữ liệu histogram giá của top 20 đối thủ và một khoảng giá đề xuất |
| Xử lý | Lấy giá top 20 listing cạnh tranh cùng loại theo doanh số ước tính, chia bucket histogram. Khoảng đề xuất là dải giá trong top 20 có tỉ lệ chuyển đổi quan sát cao nhất, nghiêng về listing bán mạnh |
| Mục đích (trích) | "suggests an optimal price range aimed at maximizing conversion rate" |
| BR-198 | Phân bố giá tính từ top 20 listing cạnh tranh theo doanh số ước tính, cùng loại sản phẩm |
| BR-199 | Khoảng đề xuất tính lại hằng tuần trong job batch analytics |
| BR-200 | Seller chưa có listing loại đó thì vẫn vẽ biểu đồ, chỉ bỏ vạch giá của seller |
| BR liên quan (3.9.1) | BR-187 scan đối thủ mỗi ngày; BR-188 xếp theo doanh số, hoà thì theo số review; BR-189 loại shop mình khỏi top 20. Ba luật này định nghĩa "competitor scan cache" mà F35 đọc |
| Màn hình | Tab "Tối ưu giá bán"; tiêu đề "Ma trận giá & hiệu quả chuyển đổi" + dropdown loại; banner "Khoảng giá đề xuất: {min}đ – {max}đ"; histogram Recharts có vạch giá của seller |
| Validation | Không có đối thủ thì empty state MSG154, gợi ý chọn loại khác; lỗi tải thì histogram trống, log console (MSG142) |

## 1. Roast: code hiện tại thực chất là gì

**Bản đăng ký hứa "tối ưu chuyển đổi", code giao "trung vị ± tứ phân vị".** `f35_pricing.py:66-71`:
```python
return {"low": pb["p25"], "high": pb["p75"],
        "basis": f"khoảng giá liên phân vị của {co_so}", ...}
```
Không có một dòng nào đụng tới view, order hay conversion. Tab đăng ký tên "Tối ưu giá bán" mà ruột là `np.percentile` viết tay. Đéo phải định giá, càng đéo phải AI.

**Chính FE tự khai là không làm đúng đăng ký.** `PricingPage.tsx:4-6` và `:266-269` ghi thẳng "không cho biết giá nào bán chạy hơn". Trung thực thì tốt. Nhưng hội đồng chấm theo bản đăng ký, và bản đăng ký nói ngược lại. Lệch mà không xin sửa SRS thì đứng trước hội đồng là ăn hành.

**Trên dữ liệu mồi, F35 đang đọc lại tham số `random.uniform`.** `app/seed/marketplace/generate_seed.py:282-284` sinh giá bằng giá vốn × `uniform(2.0, 3.0)`. Tier bán chạy xáo độc lập với giá (`:238-239`). Vậy "P25–P75 của top 20 bán chạy" trong một loại phôi chỉ xấp xỉ giá vốn × [2.25; 2.75] cộng nhiễu lấy mẫu. Mày đang "phân tích thị trường" cái hệ số random mày tự gõ vào. Ngáo vl.

**Shop thật bị regex nhét vào loại phôi sai, còn có self-check chứng nhận là đúng.** `_live.py:26-57`, tao chạy thử:

| Tên sản phẩm thật | Bị map thành | Lý do |
|---|---|---|
| Bộ ấm chén Bát Tràng | `mug_11oz` | `_live.py:28` |
| Chậu gốm trồng cây có tách nước | `mug_11oz` | chữ "tách", `:29` |
| Túi xách da bò thật | `tote` | `\btúi\b`, `:39` |
| Nón lá Huế thủ công | `hat_dad` | "nón", `:43` |
| Quần jean nữ | `sweatpants` | "quần", `:36` |
| Tranh sơn mài Hạ Long | `canvas_stretched`, `handmade_hint=False` | `:45`; "sơn mài" không có trong `:71-76` |

`_live.py:226` còn assert "Bộ Ly Gốm Mộc Men Lam Bát Tràng" → `mug_11oz` là đáp án đúng. Gốm thủ công đem so với cốc in sẵn của Printify. Đm, test viết ra để khoá cái sai lại.

**Rơi xuống fallback thì càng tệ.** `f35_pricing.py:169-201` gọi `gia_cung_danh_muc_live` (`_live.py:182-213`): mỗi biến thể là một phiếu. Sản phẩm 6 size đè sản phẩm 1 size. Không có top 20, không có doanh số, danh mục là chuỗi tự do. Vậy mà FE vẫn ghi "nhóm bán chạy" (`PricingPage.tsx:30-34`, `:254-256`).

**Hai trang, ba định nghĩa "giá của một sản phẩm".** F35 live lấy trung vị lệch trên của biến thể (`_live.py:170`, `gia[len(gia)//2]`). F33 live lấy biến thể rẻ nhất (`_competitor_live.py:97`). Fallback F35 lấy mọi biến thể. Mở F33 và F35 cạnh nhau là thấy hai con số khác nhau cho cùng một món.

**Giá vốn tính xong rồi vứt.** `_live.py:173` tính `cost_vnd`, F35 không dùng. Khoảng đề xuất có thể nằm dưới giá vốn mà không ai cảnh báo.

### Lệch bản đăng ký

- Thuật toán khoảng đề xuất: SRS là dải conversion cao nhất trong top 20, có trọng số doanh số; code là P25–P75 (`f35:66-71`).
- BR-199: SRS bắt tính lại hằng tuần trong batch; code tính lại mỗi request (`f35:120-131`, `:169-170`). Không có job tuần nào ghi khoảng giá.
- BR-200: nhánh seed ném `invalid_param` khi seller chọn loại mình chưa bán (`f35:221-223`), thay vì vẽ biểu đồ không vạch.
- BR-198: nhánh seed lấy top 20 gồm cả listing của chính seller (`f35:225-231`), trái với "competing" và BR-189. Nhánh fallback live không có top 20 (`f35:169-201`).
- Output: SRS là histogram bucket; API trả phân vị `min/p10/p25/p50/p75/p90/max` (`f35:53-55`).
- Input: SRS bắt `productType`; code cho tuỳ chọn, tự đoán (`f35:99-109`) và thêm `price`, `productId` không có trong SRS (`f35:263-266`).
- Màn hình: SRS là `SellerPricingAnalysisPage`, route `/seller/analytics/pricing`, tiêu đề "Ma trận giá & hiệu quả chuyển đổi", histogram Recharts. FE là `PricingPage`, route `/seller/insights/pricing` (`InsightsPortal.tsx:49`), tiêu đề "Giá tôi đắt hay rẻ" (`PricingPage.tsx:68`), thước SVG `DistributionRuler` (`:198-204`).

## 2. Mổ xẻ lỗi

| # | Mức | Chỗ | Lỗi | Hậu quả | Sửa nhanh |
|---|---|---|---|---|---|
| 1 | Chết người | `f35:66-71`, FE `:4-6`, `:266-269` | Lệch đăng ký: khoảng đề xuất không dựa trên conversion | Hội đồng chấm "không làm chức năng đã đăng ký" | Làm đúng thuật toán SRS, có cổng tín hiệu (mục 4.3); ghi phụ lục cho trường hợp thiếu dữ liệu |
| 2 | Nặng | `f35:120-131` | Lệch BR-199: không có batch tuần | Khoảng giá đổi theo từng lần bấm; không có mốc "tuần" để kiểm | Job tuần ghi `price_band_weekly`; endpoint chỉ đọc |
| 3 | Nặng | `f35:221-223` | Lệch BR-200 ở nhánh seed | Chọn loại chưa bán thì báo lỗi tham số | Bỏ chặn; `my_price=null` |
| 4 | Nặng | `f35:225-231` | Top 20 nhánh seed gồm cả listing của mình | Tự so với chính mình; lệch BR-198/189 | Lọc `shop_id != me` trước khi xếp |
| 5 | Nặng | `f35:53-55`, `f35:99-109`, `:263-266`, FE `:68`, `:198-204` | Lệch output, input, màn hình: không histogram; `productType` tuỳ chọn và tự đoán; thêm `price`/`productId`; tên trang và route khác SRS | Hội đồng đối chiếu màn hình không khớp | Trả `histogram: [{lo, hi, n, sales}]`, vẽ Recharts; `productType` bắt buộc, FE gửi loại mặc định; tham số thêm ghi phụ lục |
| 6 | Nặng | `_live.py:26-57`, `:226` | Regex loại phôi sai cho hàng thủ công, self-check khoá cái sai | So gốm, đồ da, nón lá với phôi POD | Phân loại bằng SigLIP2 có ngưỡng bỏ phiếu trắng (mục 4.3) |
| 7 | Nặng | `generate_seed.py:282-284`, `:238-239` | Mặt bằng seed là hệ số random, tier độc lập giá | Mọi "khoảng tối ưu" trên seed là hiện vật của bộ sinh | Ghi `seed_demo` rõ ràng; dùng seed làm phép thử null (mục 4.6) |
| 8 | Vừa | `PricingPage.tsx:30-34`, `:254-256` | Luôn ghi "nhóm bán chạy" kể cả `live_category` | Nói sai nguồn so sánh | Lời văn theo `basis_kind` |
| 9 | Vừa | `_live.py:182-213` | Mỗi biến thể một phiếu, không top 20 | Sản phẩm nhiều size chi phối phân bố | Một giá đại diện mỗi sản phẩm |
| 10 | Vừa | `_live.py:170`, `_competitor_live.py:97` | Ba định nghĩa giá sản phẩm | F33 và F35 mâu thuẫn nhau | Một hàm `gia_dai_dien()` dùng chung |
| 11 | Vừa | `_live.py:173` | `cost_vnd` tính rồi bỏ | Đề xuất có thể dưới giá vốn | Cảnh báo khi `low < cost` |
| 12 | Vừa | `PricingPage.tsx:268` | Hằng số `pct(26, 0)` đo trên seed in cho mọi shop | Kết luận của dữ liệu mồi hiện như sự thật thị trường | Lấy từ API kèm `mode` |
| 13 | Nhẹ | `f35:133-136` | `sample_size=len(rows)` trong khi phân bố chỉ dùng ≤ 20 dòng | Meta phóng đại cỡ mẫu | `sample_size=len(gia)` |
| 14 | Nhẹ | `f35:265` | `price` không kiểm biên | Giá âm hoặc 0 vẫn ra phân vị | `ge=1000` theo BR-156 |

## 3. Tính năng này nên là AI gì

Seller cần biết: với món này, mức giá nào bán được mà không lỗ, và mức đó chắc tới đâu. SRS đóng khung câu trả lời: histogram top 20 cùng loại, cộng một dải giá chuyển đổi tốt nhất. Giữ nguyên khung đó, bên dưới có ba lớp:

| Lớp | Bản chất | Đầu vào → đầu ra | Nhãn |
|---|---|---|---|
| A. Gán loại sản phẩm cho listing | AI (phân loại) | tiêu đề + ảnh (SigLIP2) → `productType` hoặc "không có loại tương ứng" | Gán tay sản phẩm VietCraft thật + tên phôi trong `blank_products` |
| B. Dải chuyển đổi tốt nhất trong top 20 | Thống kê có kiểm định, không phải ML | orders, views theo bucket giá → dải tốt nhất + xác suất là tốt nhất | orders/views thật |
| C. Model khoảng giá `price_band` (dùng chung với F42) | AI (hồi quy phân vị) | danh mục, chất liệu, vector chữ/ảnh, kNN → q25, q50, q75 | giá niêm yết Tiki |

Nói thẳng: **hiện chưa có dữ liệu conversion thật.** Sàn live có 4 đơn. Tiki chỉ có `sold` cộng dồn, không có view. Seed có view và order nhưng phễu là tham số nhập tay (`docs/SEED_PARAMS.md`). Lớp B phải được dựng đúng thuật toán SRS, nhưng chỉ được tuyên bố "dải tối ưu" khi qua cổng tín hiệu. Lớp C chỉ là tham chiếu khi sàn chưa đủ 20 đối thủ. Giá Tiki là **giá niêm yết**, không phải giá tối ưu doanh số. Muốn "giá tối ưu" thật phải có dữ liệu cầu: cùng sản phẩm, giá đổi theo thời gian, có lượt xem và đơn, để ước độ co giãn. Hiện không có.

## 4. Đường ra: thiết kế AI chính hiệu

### 4.1 Dữ liệu: train / validation / test / thực

| Nguồn | Dùng cho | Chia |
|---|---|---|
| tiki23 + tiki26 (`data-li/features/table.parquet`, `emb.npz`) | Lớp C | Dùng lại split của Listing Intel: `GroupShuffleSplit` theo seller, 70/15/15, `random_state=42`. Train 30,402 / val 7,713 / test 7,458 dòng |
| Seed `vietcraft-seed` | Demo, phép thử null và phép thử cài tín hiệu cho lớp B | Không dùng để kết luận thị trường |
| Sản phẩm VietCraft thật (79 Atlas, 29 local) | Nhãn tay cho lớp A; tập "bóng" đo độ phủ của lớp C | Không train lớp C trên tập này |
| `orders`, `product_events` live | Lớp B khi đủ ngưỡng | Cửa sổ 90 ngày, tính trong batch tuần |

Chống rò rỉ cho lớp C:
- Bỏ mọi cột suy từ giá của chính dòng: `log_price`, `price_rel`, `knn_price_pct`. Bỏ `sold` và `top25`: giá không được điều kiện theo kết quả bán của chính nó.
- Chỉ mục kNN chỉ dựng từ train; dòng train bỏ láng giềng cùng seller (giống Listing Intel).
- Nhóm `group` của tiki23 và tiki26 không trùng nhau, nên `group` cũng mã hoá nguồn. Báo kết quả theo từng nhóm.
- Test cho bài toán giá **chưa đọc lần nào**. Sổ đọc test riêng, bắt đầu từ 0.

Độ phủ: Tiki gần như không có gốm (8 tiêu đề chứa "gốm", 4 chứa "Bát Tràng"), bạc 925 (1), cốc sứ (32). Loại nào dưới ngưỡng thì lớp C trả "không đủ dữ liệu". Không quay về bảng giá cứng.

Chuyển sang dữ liệu VietCraft: lớp B bật cho một loại khi top 20 có tổng ≥ 2,000 view và ≥ 40 đơn đã giao trong 90 ngày. Đây là ngưỡng thiết kế, phải kiểm lại bằng phép thử công suất ở 4.6.

### 4.2 Làm sạch và sanity

- Giá nguyên VND ≥ 1,000 (khớp BR-156). Huấn luyện trên log giá. Cắt ngoại lai theo MAD trong từng nhóm (|z| > 4).
- Trọng số mỗi dòng = 1 / số listing của seller đó trong train, để shop lớn không chi phối.
- Ranh giới tin cậy: `productType` phải thuộc enum catalog, sai thì 422. `price` trong [1,000; 10⁹]. `productId` giữ kiểm quyền sở hữu như `f35:95-97`.
- Một hàm `gia_dai_dien(product)` dùng chung cho F33, F35, F42: trung vị biến thể đang bán.
- Sanity bắt buộc: xáo nhãn giá trong train thì MdAPE phải về quanh mức trung vị nhóm; học lại hai lần ra giống hệt; không seller nào nằm ở hai tập.

### 4.3 Model

**Lớp B, đúng SRS 3.9.4:**
1. Top 20 listing cạnh tranh cùng `productType`, bỏ shop mình, xếp theo doanh số ước tính; hoà thì theo số review.
2. Chia histogram 5 bucket theo phân vị (mỗi bucket 4 listing).
3. Mỗi bucket: CR = Σorders / Σviews. Cộng dồn như vậy đã nghiêng về listing nhiều lưu lượng và bán mạnh. Co về CR chung của loại bằng prior Beta.
4. Lấy mẫu hậu nghiệm, tính P(bucket là tốt nhất).
5. Chỉ trả `basis: "conversion"` khi P ≥ 0.9 và mọi bucket đủ ngưỡng view. Ngược lại trả khoảng phổ biến có trọng số doanh số với `basis: "no_conversion_signal"`, và banner nói rõ chưa đủ dữ liệu chuyển đổi. **Cần cập nhật SRS/phụ lục** cho nhánh này.

**Lớp C, model `price_band`, dùng chung với F42:**

| Bậc | Model | Ghi chú |
|---|---|---|
| B0 | Trung vị nhóm, P25–P75 nhóm (đã có `reference/group_median_price.json`) | Baseline 1 |
| B1 | kNN-20 trên vector tiêu đề SigLIP2: trung vị và P25–P75 của láng giềng | Baseline 2, rất khó thắng |
| M1 | `HistGradientBoostingRegressor(loss="quantile")`, α = 0.25 / 0.5 / 0.75 trên log giá | sklearn 1.9.1 có sẵn, chạy CPU |
| M1+ | Hiệu chỉnh khoảng bằng conformalized quantile regression (Romano, Patterson, Candès, NeurIPS 2019) trên validation, tách theo nhóm | Bảo đảm độ phủ 50% của khoảng P25–P75 |

Feature của M1: nhóm danh mục; multi-hot 37 chất liệu từ `lexicon.json` cộng `materials` seller khai báo; size, màu, số lượng trong bộ ("bộ 2", "combo 3"); 16 PCA của vector chữ, 16 PCA vector ảnh (tiki23 không có ảnh nên thêm cờ thiếu); `knn_median_price`, P25/P75 láng giềng, độ tương đồng trung bình của láng giềng.

**Lớp A:** kNN nguyên mẫu trên SigLIP2 (chữ + ảnh) so với tên và ảnh phôi trong `blank_products`. Độ tương đồng dưới ngưỡng thì trả "không có loại phôi tương ứng". Ngưỡng chọn trên tập nhãn tay. Baseline là regex `doan_loai_phoi` hiện tại.

### 4.4 Học từ dữ liệu thật

- Batch tuần (BR-199): job ghi `price_band_weekly {productType, week, histogram, suggested_range, basis, p_best, n_views, n_orders, model_version}`. Endpoint chỉ đọc. FE hiện "Cập nhật tuần …".
- Log mỗi lần hiển thị: khoảng đã gợi ý, giá seller chốt, view và đơn 30 ngày sau. Đây là dữ liệu quan sát, có nhiễu gây nhầm, chỉ dùng để giám sát.
- Cold start: sàn chưa đủ 20 đối thủ thì hiện số đối thủ đang có. Không có đối thủ nào thì empty state MSG154. Khoảng `price_band` từ Tiki chỉ hiện ở khối phụ, ghi rõ "thị trường tham chiếu Tiki" (**cần ghi phụ lục**).
- Drift: hằng tháng đo độ phủ của khoảng `price_band` trên listing VietCraft mới. Ra khỏi [35%; 65%] thì hiệu chỉnh lại conformal bằng listing VietCraft. Bước này chỉ cần khoảng 100 listing, không cần train lại.

### 4.5 Bảo mật và chống gian lận

- F35 không gọi LLM, nên không có prompt injection.
- Đầu độc dữ liệu: shop dựng listing ảo giá cực đoan để kéo phân bố. Chống: doanh số ước tính chỉ đếm đơn đã giao, không mô phỏng, người mua khác chủ shop. Bộ lọc hiện tại (`_competitor_live.py:103-106`) chưa loại tự mua. Listing phải đang bán ≥ 7 ngày mới vào top 20.
- Cắt ngoại lai theo MAD trước khi chia bucket, để một giá 1 đồng hay 1 tỉ không tạo bucket riêng.
- Không trả mã listing hay tên shop đối thủ trong F35, chỉ trả phân bố.
- Giấy phép: tiki23 chỉ dùng học thuật. Nếu thương mại hoá thì khối tham chiếu Tiki phải gỡ (`LISTING_INTEL_TECH_REPORT.md` mục 4).

### 4.6 Benchmark và kiểm chứng

**Số đo nhanh đã có (validation, chưa đọc test).** Validation 7,713 dòng, 642 seller. CI bootstrap 500 lần theo cụm seller.

| Phương pháp | MdAPE | MAPE | Độ phủ P25–P75 (mục tiêu 50%) | Độ rộng q75/q25 |
|---|---|---|---|---|
| B0 trung vị nhóm | 61.3% | 129.1% | 58.3% | 4.52× |
| P25–P75 của top 20 bán chạy (kiểu F35) | 70.1% | 86.0% | 28.4% | 3.12× |
| B1 kNN-20 vector tiêu đề | 39.1% | 76.2% | 47.5% | 2.14× |
| F42 hiện tại (chỉ tiêu đề, không giá vốn) | 174.5% | 443.0% | 19.1% | 2.32× |

- kNN − trung vị nhóm: MdAPE −22.2 điểm, CI95 [−26.6; −16.2].
- Khoảng của top 20 bán chạy chỉ chứa 28.4% listing cùng nhóm. Vậy câu "một nửa số sản phẩm có giá trong khoảng này" chỉ đúng với 20 listing đó, không đúng với cả thị trường.
- Cách tái lập: dùng split `table.parquet`, chỉ mục kNN dựng từ train theo nhóm, chạy trên `split == "val"`. Script đo nằm ngoài repo.

**Cổng "đạt khi" của `price_band` (đo một lần trên test, ghi sổ):**
- M1+ có MdAPE thấp hơn B1, cận trên CI95 của hiệu < 0.
- Độ phủ P25–P75 nằm trong [45%; 55%] ở mọi nhóm có ≥ 200 dòng test.
- Độ rộng trung vị không lớn hơn B1.
- Pinball loss ở α = 0.25 / 0.5 / 0.75 đều không tệ hơn B1.
- Không thắng B1 thì phục vụ B1 và ghi thẳng "kNN là đủ". Không giấu.

**Phép thử chất liệu** (đúng điểm hội đồng chê): trên validation, đổi "da PU" ↔ "da bò" trong tiêu đề túi và giày. q50 phải tăng ở ≥ 80% cặp. So mức tăng trung vị với chênh trung vị thật giữa hai nhóm tiêu đề trên Tiki train.

**Lớp B:**
- Phép thử null trên seed: xáo giá trong top 20 (1,000 lần). Tỉ lệ tuyên bố "dải tối ưu" phải ≤ 10%.
- Phép thử cài tín hiệu: bơm một đường CR theo giá đã biết vào bản sao seed. Thuật toán phải tìm đúng bucket ≥ 80% số lần khi lift ≥ 30%. Đây là cách kiểm thuật toán khi chưa có dữ liệu thật.

**Lớp A:** accuracy và tỉ lệ bỏ phiếu trắng trên ≥ 150 sản phẩm gán tay, kèm Wilson CI. Đạt khi accuracy trên phần trả lời có cận dưới ≥ 85% và cao hơn regex.

## 5. Lộ trình

| Giai đoạn | Việc | Kết quả kiểm chứng |
|---|---|---|
| Ngay 1–2 ngày | Sửa BR-200 nhánh seed; lọc shop mình khỏi top 20; trả `histogram`; sửa lời "nhóm bán chạy" theo `basis_kind`; gỡ hằng số `pct(26, 0)`; sửa self-check `_live.py:226`; `sample_size` đúng | Test BR-198/200; FE hiện đúng nguồn |
| 1–2 tuần | Job tuần `price_band_weekly` (BR-199); lớp B có cổng tín hiệu và hai phép thử; lớp C B0/B1/M1/M1+ trên Tiki; lớp A với 150 nhãn tay; viết phụ lục SRS cho nhánh `no_conversion_signal` | Bảng 4.6 đọc test một lần; báo cáo phép thử null và cài tín hiệu |
| Khi có dữ liệu thật | Bật lớp B theo từng loại đủ ngưỡng; hiệu chỉnh conformal bằng listing VietCraft; giám sát độ phủ hằng tháng | P(best) và CI trên dữ liệu thật; độ phủ VietCraft trong [35%; 65%] |

**Xong khi:**
- Khớp các BR và endpoint của mục SRS 3.9.4: `GET /api/analytics/pricing?productType=` bắt buộc `productType`. BR-198: top 20 cạnh tranh theo doanh số ước tính, không gồm shop mình. BR-199: khoảng đề xuất ghi trong job tuần. BR-200: không có listing thì vẫn vẽ, bỏ vạch. Định nghĩa competitor cache khớp BR-187, BR-188, BR-189. Có empty state MSG154 và lỗi MSG142.
- Trang có histogram và banner "Khoảng giá đề xuất". Banner ghi `basis` là `conversion` hoặc `no_conversion_signal`.
- `price_band` có bảng test một lần, đủ CI, cổng đạt hoặc ghi rõ phục vụ B1.

## 6. Hội đồng sẽ hỏi

**"SRS ghi tối ưu chuyển đổi, sao trang nói không biết giá nào bán chạy hơn?"**
Vì chưa có dữ liệu conversion thật: 4 đơn trên sàn, Tiki không có view. Thuật toán đúng SRS đã dựng, nhưng có cổng: chỉ tuyên bố dải tối ưu khi xác suất ≥ 0.9. Phép thử cài tín hiệu chứng minh thuật toán bắt được tín hiệu khi tín hiệu có thật.

**"Giá Tiki thì liên quan gì đồ thủ công VietCraft?"**
Chỉ là tham chiếu khi sàn chưa đủ 20 đối thủ, ghi rõ nguồn. Gốm và bạc gần như không có trên Tiki, nên model bỏ phiếu trắng thay vì bịa.

**"Model của em hơn cách đơn giản bao nhiêu?"**
Trên validation, kNN tiêu đề đã giảm MdAPE 22 điểm so với trung vị nhóm, CI [−26.6; −16.2]. Model phân vị phải thắng kNN trên test mới được phục vụ. Không thắng thì dùng kNN và nói thẳng.

**"Chất liệu có vào giá không?"**
Có, qua lexicon 37 chất liệu và trường `materials`. Phép thử đổi da PU ↔ da bò đo chiều tác động.

**"Sao không hồi quy giá theo doanh số để ra giá tối ưu?"**
Vì giá và doanh số trên dữ liệu quan sát bị nhiễu gây nhầm. Trên seed, tier còn được sinh độc lập với giá. Ước độ co giãn cần giá thay đổi theo thời gian, có lượt xem. Đó là việc của giai đoạn có dữ liệu thật.
