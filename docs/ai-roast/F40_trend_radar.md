# F40 Tag đang tăng nhanh: roast và đường ra

> Endpoint `GET /api/analytics/forecast/radar` (BE proxy `/api/seller/analytics/forecast/radar`) · Trang FE `/seller/insights/radar` (`FE/src/modules/analytics/pages/RadarPage.tsx`) · File chính `app/api/v1/f40_radar.py`, `app/core/build_marts.py:258-307` · Ngày 2026-10-21 · Người viết: Claude (subagent)

## 0. Bản đăng ký nói gì

| Mục | SRS 3.10.4 Emerging Niche Radar (tóm tắt) |
|---|---|
| Actor, trigger | Seller đã đăng nhập. Mở cùng lúc với Cơ hội ngách (3.10.3), ở panel bên phải hoặc tab con |
| Endpoint | `GET /api/analytics/forecast/radar`, Bearer JWT |
| Input | Không có. Dữ liệu hệ thống là lượng tìm kiếm gom theo tuần |
| Xử lý | Tính tăng trưởng tìm kiếm **tuần so với tuần (WoW)** cho mọi tag. Momentum Score dựa trên **gia tốc** tìm kiếm trong 3 tuần qua. Định dạng cho Recharts Radar với trục là danh mục lớn |
| Output, màn hình | `EmergingNicheRadar.tsx`. Radar vẽ **Momentum Score** trên 5–8 trục danh mục lớn. Bên dưới là danh sách top 10 tag tăng nhanh nhất, kèm % WoW. Cập nhật hằng tuần |
| BR-212 | Radar chỉ vẽ danh mục lớn; danh sách mới ghi tag chi tiết |
| BR-213 | Momentum Score chỉ tính khi tag có ít nhất 100 lượt tìm mỗi tuần |
| Validation | Thiếu dữ liệu tuần thì radar co lại, chỉ vẽ trục có dữ liệu hợp lệ |
| Ngoại lệ | FE parse trục radar lỗi thì vẽ biểu đồ cột thay thế |

## 1. Roast: code hiện tại thực chất là gì

**Đường dẫn là `/forecast`, ruột không có dự báo.** `f40_radar.py:21-66` đọc mart, gom nhóm, chia cho max. Không có dòng nào nhìn về tương lai.

**"Tăng nhanh" là 4 tuần so với 4 tuần, không phải tuần so với tuần.** `build_marts.py:279-288`:
```python
gan += [v for _, v in diem[-4:]]
truoc += [v for _, v in diem[-8:-4]]
tang = round((tb_gan - tb_truoc) / tb_truoc * 100, 1)
```
FE lại ghi "Tốc độ tăng so với tuần trước" (`RadarPage.tsx:76`). Nói một đằng, tính một nẻo.

**"Đà tăng" chỉ là tăng trưởng vẽ lại thang.** `momentum = clamp(tang/100 + 0.5, 0, 1)` (`:298`). Không gia tốc, không 3 tuần, chỉ là một phép biến đổi tuyến tính của đúng con số `growth_pct`. FE còn chém: "Đà tăng gần 1 nghĩa là tăng liên tục nhiều tuần, không phải vọt một hôm rồi tụt" (`RadarPage.tsx:76`). Sai hoàn toàn. Lấy một chuỗi đứng ở 10, chỉ một tuần vọt lên 50: trung bình 4 tuần thành 20, tăng +100%, momentum 1,0. Tức là đúng cái kiểu "vọt một hôm" mà FE thề là không phải. Bịa vl.

**Radar vẽ mức cầu, không vẽ momentum.** Trục là trung bình `demand_index` theo danh mục cấp 1, chia cho trục cao nhất (`f40:31-41`). Đây là mức tìm kiếm trung bình 4 tuần, không phải độ tăng. Danh mục nào lúc nào cũng được tìm nhiều thì luôn phình to trên "radar tăng nhanh". FE ghi tiêu đề "Nhu cầu theo nhóm hàng" (`RadarPage.tsx:50`), trung thực, nhưng không phải thứ đã đăng ký.

**Top 10 thực chất là 5 chuỗi in đôi.** Một từ khoá Trends map vào nhiều tag: `tag_keyword_map` có 118 dòng cho 40 từ khoá, riêng "áo thun" vào 9 tag. Mỗi tag nhận nguyên chuỗi của từ khoá đó (`build_marts.py:266-269`). Snapshot `mart_demand` trong backup seed (`backupDB/mongo-backup/vietcraft-seed`, dựng 2026-09-21) có các cặp trùng hệt nhau:
- `tranh-canvas` và `decor-khong-gian`: +33,3%;
- `tote-canvas` và `tui-tote`: +21,4%;
- `keychain` và `moc-khoa`;
- `ao-lop` và `ao-hoc-sinh`;
- `tranh-decor` và `tranh-treo-tuong`.

"10 tag tăng nhanh nhất" đếm ra 5 tín hiệu. Đm.

**"Tuần này" là tuần của dữ liệu seed.** Nhãn tuần lấy ngày cuối của `listing_daily` seed (`build_marts.py:34-38,263-264`), ra `2026-W35`. Trends tuần lại dừng ở 2026-08-16, tức tuần 33. Trang ghi "10 tag tăng nhanh nhất tuần này" (`RadarPage.tsx:75`) cho dữ liệu đã cũ 2 tháng, và nhãn tuần lệch 2 tuần so với chính dữ liệu.

**Rác quanh rìa.**
- `shop_id` nhận vào rồi bỏ (`f40:22`).
- `mode="live"` (`:44`), trong khi `supply_n_listings` đếm listing seed (`build_marts.py:299`). FE in nó thành cột "Listing đang có" (`RadarPage.tsx:92,107`). Snapshot: 187–215 listing mỗi tag, đều tăm tắp vì tag seed bốc ngẫu nhiên (`generate_seed.py:277-279`).
- Tag nền thấp (33/75 trong snapshot) bị xếp xuống dưới. Mart có cờ `low_base` (`:302`) nhưng API không trả ra.
- Không có job tuần dựng lại mart; chỉ chạy tay `run.py:161`.
- Không test, không đánh giá.

Công bằng mà nói: BR-213 không áp được, và code nói thẳng điều đó thay vì bịa số lượt tìm (`f40:62-65`, `RadarPage.tsx:118-124`). `searches_per_week` để `null`. Đây là chỗ trung thực nhất của cả nhóm tính năng.

### Lệch bản đăng ký
- **Tăng trưởng:** SRS là WoW. Code là trung bình 4 tuần so với 4 tuần trước.
- **Momentum Score:** SRS dựa trên gia tốc 3 tuần. Code là `clamp(growth/100 + 0.5)`.
- **Radar:** SRS vẽ Momentum Score theo danh mục lớn. Code vẽ mức cầu chuẩn hoá theo max. BR-212 chỉ đúng một nửa: có gom về danh mục cấp 1, sai đại lượng.
- **Số trục:** SRS là 5–8 trục. Code không ràng buộc; chỉ cần ≥ 3 tag mỗi trục (`f40:18,36`). Trục "khac" có thể thành một đỉnh radar (`:33`). Snapshot hôm nay ra 6 trục là nhờ may.
- **BR-213:** chưa áp, đã khai. Ngưỡng nền thấp `NEN_TOI_THIEU = 5` trên chỉ số Trends (`build_marts.py:23,286`) đang làm thay. **Cần cập nhật SRS/phụ lục.**
- **Màn hình:** SRS là `EmergingNicheRadar.tsx`, mở cùng trang Cơ hội ngách. Code là trang riêng `RadarPage.tsx`, menu "Tag đang tăng nhanh" (`nav.ts:84`). Không có biểu đồ cột thay thế khi radar lỗi.
- **Cập nhật hằng tuần:** không có lịch.

## 2. Mổ xẻ lỗi

Lệch bản đăng ký: các dòng ghi mức "(SRS)" là chỗ code khác mục SRS đã đăng ký. Chúng được xếp Nặng trở lên vì hội đồng chấm theo bản đăng ký.

| # | Mức | Chỗ | Lỗi | Hậu quả | Sửa nhanh |
|---|---|---|---|---|---|
| 1 | Chết người | `RadarPage.tsx:76` | Ghi "so với tuần trước" và "đà tăng gần 1 là tăng liên tục" | Nói sai cách tính cho người dùng | Sửa chữ theo công thức thật, hoặc sửa công thức theo SRS |
| 2 | Chết người | `f40:44`, `build_marts.py:299`, `RadarPage.tsx:92` | `mode="live"`; cột "Listing đang có" là listing seed | Trình bày số seed như số sàn | `mode="derived"`; ẩn cột cung với shop thật |
| 3 | Nặng (SRS) | `build_marts.py:279-288` | Tăng 4 tuần so với 4 tuần, không phải WoW | Lệch thuật toán đăng ký | Tính WoW (4.3), giữ 4v4 làm cột phụ nếu cần |
| 4 | Nặng (SRS) | `build_marts.py:298` | Momentum là thang lại của growth, không phải gia tốc 3 tuần | Lệch định nghĩa; trùng thông tin với cột "Tăng" | Gia tốc 3 tuần (4.3) |
| 5 | Nặng (SRS) | `f40:31-41` | Radar vẽ mức cầu, không phải momentum | Trục to là trục phổ biến, không phải đang lên | Trung vị momentum theo danh mục |
| 6 | Nặng (SRS) | `f40:18,36` | Không ràng buộc 5–8 trục; trục "khac" | Có thể vẽ radar 3 trục hoặc 12 trục | Chọn 5–8 trục có dữ liệu hợp lệ; thiếu thì co lại theo Validation SRS |
| 7 | Nặng | `build_marts.py:266-269` | Một chuỗi từ khoá nhân bản sang nhiều tag | Top 10 chỉ có 5 tín hiệu | Xếp theo cụm từ khoá; mỗi cụm một dòng, liệt kê các tag con |
| 8 | Nặng | `build_marts.py:34-38,263-264` | Nhãn tuần lấy từ seed, không từ chuỗi Trends | "Tuần này" sai 2 tuần và cũ 2 tháng | Tuần lấy từ điểm Trends cuối; hiện tuổi dữ liệu |
| 9 | Vừa | `run.py:161` | Không có job tuần | Không "cập nhật hằng tuần" như SRS | Job thứ Hai sau `weekly_trends` (`listing_intel/jobs.py:65`) |
| 10 | Vừa | `f40:47-59` | Không trả `low_base` | FE không biết dòng nào nền yếu | Trả cờ, FE hiện nhãn |
| 11 | Vừa | `f40:23` | Không lọc từ cấm (BR-211 của 3.10.3) | Tag bản quyền có thể lên top | Dùng chung bộ lọc với F39 |
| 12 | Nhẹ | `f40:22` | `shop_id` nhận rồi bỏ | Không sai, nhưng gây hiểu nhầm | Ghi rõ `scope="platform"` (đã có) và bỏ tham số |
| 13 | Nhẹ | `RadarPage.tsx:54-65` | Không có biểu đồ cột thay thế | Trượt nhánh ngoại lệ SRS | Bọc error boundary, rơi về biểu đồ cột |

## 3. Tính năng này nên là AI gì

Seller cần biết: "Chủ đề nào **bắt đầu** lên, sớm hơn đối thủ, mà không phải chỉ vì sắp tới dịp?" Đây là bài toán **phát hiện xu hướng sớm**, không phải dự báo mức. Giữ đúng SRS cho phần hiển thị: WoW, Momentum Score theo gia tốc 3 tuần, radar danh mục lớn, top 10 tag. Lớp AI đáng làm:

| Bài toán | Đầu vào | Đầu ra | Nhãn |
|---|---|---|---|
| Khử mùa | Chuỗi tuần của từng cụm từ khoá; chỉ số mùa tính từ quá khứ (`trend_axis.seasonal_index`) | Mức cầu đã khử mùa; WoW thô và WoW khử mùa | Không cần nhãn |
| Cờ "mới nổi" | WoW, gia tốc, z-score phần dư STL, mức nền, số tuần tăng liên tiếp | Xác suất bùng nổ trong 4 tuần tới, đã hiệu chỉnh | "Bùng nổ" định nghĩa trước (4.6) |

Đừng gắn mác AI cho WoW và gia tốc. Hai cái đó là thống kê mô tả, cứ gọi đúng tên. Phần có giá trị thật, và kiểm được, là khử mùa cùng cờ mới nổi có backtest. Nếu đếm ra quá ít ca bùng nổ ngoài mùa vụ (xem 4.6), dừng ở thống kê và nói thẳng.

## 4. Đường ra: thiết kế AI chính hiệu

### 4.1 Dữ liệu: train / validation / test / thực
- **Chuỗi tuần:** `data-collection.trend_interest`, 2021-08-15 → 2026-08-16, 45 từ khoá, 262 tuần.
- **Chuỗi ngày:** 44 từ khoá, 2026-05-18 → 2026-10-17. Tổng 7 ngày so với 7 ngày trước cho WoW tươi hơn chuỗi tuần, đang trễ 2 tháng.
- **Đơn vị phân tích:** cụm từ khoá, không phải tag. Tag chỉ là nhãn hiển thị qua `tag_keyword_map`. Cách này dẹp lỗi nhân bản.
- **Chia theo thời gian:** mốc mỗi tuần.
  - Train: tới 2024-08.
  - Validation: 2024-08 → 2025-08, dùng để chọn ngưỡng và hệ số.
  - Test: 2025-08 → 2026-08, đọc một lần, ghi số lần đọc.
- **Chống rò rỉ:** chỉ số mùa và z-score chỉ dùng dữ liệu đến mốc. Nhãn bùng nổ dùng T+1…T+4, không bao giờ lọt vào đặc trưng.
- **Dữ liệu sàn:** `search_logs` (`BE/.../search-log.model.ts:9-16`) đếm user duy nhất theo `keyword_norm` mỗi tuần. Đây là nguồn duy nhất áp được BR-213 (100 lượt tìm/tuần) một cách trung thực. Chuyển nguồn khi đủ 12 tuần liên tục cho ít nhất 5 danh mục.

### 4.2 Làm sạch và sanity
- **Nền thấp:** giữ `NEN_TOI_THIEU` trên Trends làm ngưỡng tạm cho BR-213, ghi phụ lục. Khi có `search_logs` thì áp đúng 100 lượt mỗi tuần.
- **Mẫu số:** dùng log ratio `log(y_t + 1) − log(y_{t−1} + 1)` để mẫu số nhỏ không nổ %. Hiển thị % WoW chỉ khi nền đạt ngưỡng.
- **Cụm trùng:** một chuỗi chỉ được đếm một lần trong top 10 và trong trung vị theo trục.
- **Nhãn tuần:** lấy từ điểm Trends cuối. Dữ liệu cũ hơn 14 ngày thì hiện tuổi dữ liệu và `partial`.
- **Sanity bắt buộc:**
  1. Chuỗi phẳng cộng nhiễu: tỉ lệ bị cờ ≤ tỉ lệ báo nhầm đã chọn.
  2. Chuỗi tổng hợp gắn một bước nhảy bền ở tuần t0: phải bị cờ trong 1–3 tuần.
  3. Một tuần vọt rồi tụt: momentum **không** được chạm trần. Đây là test cho đúng lời FE đang hứa.
  4. Xáo thứ tự tuần trong từng chuỗi: precision rơi về mức ngẫu nhiên.

### 4.3 Model
- **Định nghĩa theo SRS:**
  - `g_t = log(y_t+1) − log(y_{t−1}+1)` (WoW).
  - Gia tốc 3 tuần: `a_t = g_t − g_{t−2}`.
  - `Momentum_t = 100 × phân vị của (g_t + a_t)` trong các cụm đạt nền cùng tuần.
  - Trục radar = trung vị momentum của các cụm thuộc danh mục lớn. Chọn 5–8 trục có ít nhất 3 cụm hợp lệ.
- **Baseline:**
  - (a) Ngẫu nhiên.
  - (b) Top WoW thô, đúng nghĩa đen SRS.
  - (c) Code hiện tại (4v4).
  - (d) Độ phổ biến.
  - (e) **Lịch dịp:** cờ mọi từ khoá có dịp trong 4 tuần tới, dùng `calendar_vn.upcoming_events`.

  Baseline (e) rất mạnh. Báo cáo Listing Intel §8 cho thấy 84,6% đỉnh theo dịp rơi vào −4…0 tuần trước dịp. Nếu model không thắng (e) thì nó chỉ đang đọc lịch.
- **Chính:** `LogisticRegression` của sklearn trên các đặc trưng ở mục 3, cộng cờ "có dịp trong 4 tuần". Hiệu chỉnh bằng `CalibratedClassifierCV` trên validation. Chạy trên CPU, vài giây.

### 4.4 Học từ dữ liệu thật
- **Lịch:** job thứ Hai, ngay sau `weekly_trends` (`listing_intel/jobs.py:65`). Dựng mart, ghi `computed_at` và tuần dữ liệu thật.
- **Feedback:** seller có tạo sản phẩm theo tag được cờ không, và các listing đó có view hoặc đơn trong 4 tuần sau không? So với tag không bị cờ cùng danh mục.
- **Drift:** mỗi tuần, khi nhãn T−4 đã lộ, đo precision và độ hiệu chỉnh (Brier). Precision giảm ba tuần liền thì chọn lại ngưỡng trên validation mới.
- **Chuyển nguồn:** khi `search_logs` đủ (4.1), cầu chuyển sang sàn; Trends giữ làm đặc trưng phụ. Đo lại toàn bộ 4.6.

### 4.5 Bảo mật và chống gian lận
- **Không có LLM.**
- **Bơm search giả:** tín hiệu WoW trên nền nhỏ rất rẻ để làm giả. Một nhóm bot tìm một tag là nó lên radar, lùa seller vào ngách chết. Phòng bằng cách:
  - đếm user duy nhất;
  - loại tài khoản mới tạo và lượt tìm của chính seller;
  - giới hạn tần suất theo IP;
  - đòi nền tối thiểu (đúng mục đích của BR-213);
  - cảnh báo khi phần lớn lượt tăng đến từ ít user.
- **PII:** chỉ xuất số tổng hợp. Một từ khoá phải có ít nhất 5 user duy nhất mỗi tuần mới được hiện.
- **Pháp lý:** lọc `banned_keywords` (BR-211 của 3.10.3) trên danh sách tag, vì đây cũng là bảng xếp hạng hiện cho seller.
- **Thao túng Trends:** nguồn ngoài, khó thao túng ở quy mô này. Rủi ro chính là lỗi thu thập: lỗi 429 làm thiếu tuần. Thiếu tuần thì đánh dấu, không nội suy rồi gọi là tăng.

### 4.6 Benchmark và kiểm chứng
- **Nhãn bùng nổ, định nghĩa trước khi chạy:** cụm c bùng nổ ở mốc T khi thoả cả ba:
  - trung bình T+1…T+4 ≥ 1,5 × trung bình 12 tuần trước T;
  - giá trị đó ≥ 1,3 × mức kỳ vọng theo mùa (chỉ số mùa từ quá khứ);
  - nền ≥ ngưỡng.

  Đếm số ca dương trên train trước. Ít hơn khoảng 20 ca thì kết luận "không đủ ca để học", và chỉ báo thống kê.
- **Metric:**
  - Precision@10 mỗi tuần.
  - Recall của ca bùng nổ.
  - **Lead time:** số tuần từ lần đầu vào top 10 tới khi bùng nổ. Báo trung vị.
  - Số cờ sai mỗi tuần.
  - Brier score cho xác suất.
- **So sánh:** 5 baseline ở 4.3. Bootstrap theo khối tuần, ghép cặp với baseline tốt nhất.
- **Cổng đạt:**
  - Precision@10 cao hơn **cả** (b) và (e), CI 95% không chứa 0, ở lead time không kém hơn.
  - Brier thấp hơn tần suất nền.
  - Sanity 4.2 đều qua.
- **Không thắng thì sao:** ship WoW và gia tốc đúng SRS, gắn nhãn "thống kê". Thêm cột "có dịp sắp tới" từ lịch, vì đó là thông tin thật và hữu ích. Ghi trên trang rằng radar chưa dự báo.

## 5. Lộ trình

| Giai đoạn | Việc | Kết quả kiểm chứng |
|---|---|---|
| Ngay 1–2 ngày | Sửa chữ FE (lỗi 1); `mode="derived"`, ẩn cột cung seed; nhãn tuần theo Trends; gộp tag trùng chuỗi; trả `low_base`; lọc từ cấm | Test: top 10 không có hai dòng cùng chuỗi; test chuỗi vọt một tuần không cho momentum 1,0 |
| 1–2 tuần | WoW và gia tốc theo SRS; radar momentum 5–8 trục; biểu đồ cột thay thế; job tuần; script backtest `scripts/f40/` có test | Bảng 4.6 kèm CI; số ca bùng nổ đã đếm |
| Khi có dữ liệu thật | Cầu từ `search_logs`, áp BR-213 đúng 100 lượt mỗi tuần; feedback theo tag | Precision@10 và lead time trên dữ liệu sàn |

**Xong khi:**
- Mọi câu chữ trên trang khớp công thức.
- Bảng 4.6 có số kèm CI, kể cả khi thua baseline lịch.
- Có test cho momentum, cho gộp trùng và cho nhãn tuần.
- Khớp endpoint và các BR của mục SRS 3.10.4:
  - `GET /api/analytics/forecast/radar`, không input.
  - Tăng trưởng WoW; Momentum Score theo gia tốc 3 tuần.
  - Radar 5–8 trục danh mục lớn; top 10 tag kèm % WoW; cập nhật hằng tuần.
  - BR-212: radar chỉ vẽ danh mục lớn, danh sách ghi tag.
  - BR-213: ngưỡng 100 lượt tìm mỗi tuần, áp khi có `search_logs`. Tới lúc đó dùng ngưỡng nền Trends, có ghi phụ lục.
  - Validation co trục khi thiếu dữ liệu; biểu đồ cột thay thế.

## 6. Hội đồng sẽ hỏi

1. **"Momentum Score tính thế nào?"** Hiện tại là `growth/100 + 0.5` cắt về [0, 1], không đúng SRS. Bản sửa dùng WoW cộng gia tốc 3 tuần, quy về phân vị 0–100.
2. **"BR-213 đòi 100 lượt tìm/tuần, lấy đâu ra?"** Google Trends chỉ có chỉ số 0–100 tương đối, nên đổi ra lượt tìm là bịa. Áp đúng được khi có `search_logs` của sàn. Tới lúc đó dùng ngưỡng nền trên chỉ số, có ghi phụ lục.
3. **"Radar này có phát hiện sớm thật không?"** Đo bằng backtest 5 năm: precision@10 và lead time so với nhãn bùng nổ định nghĩa trước. Có baseline "chỉ đọc lịch dịp" để chắc model không chỉ nhìn lịch.
4. **"Sao top 10 có hai dòng giống hệt?"** Một từ khoá Trends map vào nhiều tag. Bản sửa xếp theo cụm từ khoá, mỗi cụm một dòng.
5. **"Có phải AI không?"** WoW và gia tốc là thống kê, và sẽ gọi đúng tên. Chỉ cờ "mới nổi" có hiệu chỉnh mới là lớp học máy, và nó chỉ được bật nếu thắng baseline lịch dịp.
