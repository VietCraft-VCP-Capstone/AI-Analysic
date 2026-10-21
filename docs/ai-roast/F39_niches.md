# F39 Ngách tiềm năng: roast và đường ra

> Endpoint `GET /api/analytics/forecast/niches?categoryId=` (BE proxy `/api/seller/analytics/forecast/niches`; BE còn gọi thẳng cho ô "Tìm kiếm thịnh hành" của người mua) · Trang FE `/seller/insights/niches` (`FE/src/modules/analytics/pages/NichesPage.tsx`) · File chính `app/api/v1/f39_niches.py`, `app/core/build_marts.py:177-251`, `BE/src/modules/product/application/trending-keywords.ts` · Ngày 2026-10-21 · Người viết: Claude (subagent)

## 0. Bản đăng ký nói gì

| Mục | SRS 3.10.3 Niche Opportunity Detection (tóm tắt) |
|---|---|
| Actor, trigger | Seller đã đăng nhập; bấm tab [Cơ hội ngách] |
| Endpoint | `GET /api/analytics/forecast/niches`, Bearer JWT |
| Input | Không có. Hệ thống tự tính trên chỉ số toàn sàn |
| Dữ liệu hệ thống | Search log của sàn, metadata tag của listing, Gap Score tính theo batch hằng ngày |
| Xử lý | Cron hằng ngày gom lượng tìm kiếm và số listing đang bán theo **tag**. `Gap = (tốc độ tăng lượng tìm × conversion trung bình) / mật độ sản phẩm cạnh tranh`. Trả **top 10** tag |
| Output, màn hình | `NicheOpportunitiesPage.tsx`. Bảng top 10 gồm: tag, lượng tìm, mức cạnh tranh Cao/Vừa/Thấp, Gap Score, sparkline **7 ngày**. Bấm một dòng mở panel: tag liên quan và top 3 sản phẩm bán chạy trong ngách |
| BR-210 | Gap Score tính lại mỗi 24 giờ, lúc nửa đêm GMT+7 |
| BR-211 | Ngách **chứa** từ khoá cấm (bản quyền, NSFW) phải bị lọc khỏi bảng |
| Validation | Job hôm nay chưa xong thì trả bảng hôm qua kèm nhãn "Dữ liệu cập nhật lúc…" |
| Luồng, ngoại lệ | Đọc top 10 từ Redis; Redis trượt thì truy vấn PostgreSQL và hiện spinner. Stack thật là Mongo, **cần cập nhật SRS/phụ lục** |

## 1. Roast: code hiện tại thực chất là gì

**Gap Score là phép trừ hai thứ hạng, không phải công thức đã đăng ký.** `build_marts.py:221-228`:
```python
cau_pct = _phan_vi_xep_hang(cau_tho)
cung_pct = _phan_vi_xep_hang(cung_tho)
gap = round(cau_pct[kw] - cung_pct[kw], 1)
```
SRS đòi tốc độ tăng nhân conversion, chia mật độ cạnh tranh. Code lấy phân vị cầu trừ phân vị cung. Tốc độ tăng chỉ dùng để gắn nhãn `rising/falling` (`:216-218`). Conversion không có trong cả file. Đăng ký một đằng, làm một nẻo, ngáo vl.

**Phía cung là xúc xắc.** Cung đếm listing trong DB seed (`:177-183`, `_db()` ở `:30-31`). Tag của 5.000 listing seed bốc ngẫu nhiên: chọn theme bằng `random.choice` (`app/seed/marketplace/generate_seed.py:265`), rồi bốc tag bằng `random.sample` (`:277-279`). Vậy `supply_pct` là phân vị của một lần tung xúc xắc. `gap_score` là Google Trends thật trừ đi số ngẫu nhiên. Code có tự thú (`f39_niches.py:114-116`), FE cũng thú (`NichesPage.tsx:195`). Thú thì tốt, nhưng bảng xếp hạng vẫn được bày ra như hàng thật.

**Ngách đang rơi vẫn được xếp là "cơ hội".** Gap bỏ qua tăng trưởng, nên snapshot `niche_score` trong backup seed (`backupDB/mongo-backup/vietcraft-seed`, ngày `2026-08-30`) cho ra:
- hạng 4 là "áo tết", xu hướng `falling` −70,4%;
- hạng 6 là "quà tết", −40,9%;
- hạng 7 là "áo bóng đá việt nam", `rising` +135,7%, trên một chuỗi trung bình 5 năm chỉ 2,3.

Bảo seller nhảy vào ngách đang sập. Đỉnh cao của "AI".

**"Ngách" là 45 từ khoá Google, không phải tag.** Tập xếp hạng là 45 từ khoá chọn tay trong `trend_interest`. Có những từ gần trùng nhau như "áo thun", "in áo thun", "áo phông nam", "áo phông nữ". Ba ô top 10 có thể cùng là một ngách. Chia góc phần tư ở 50 (`:243-245`) thì luôn có khoảng một nửa số từ khoá "cầu cao", vì phân vị tự chia đôi. Cái này là thứ hạng, đéo phải ngưỡng.

**Tốc độ tăng của F39 không có sàn chặn nền thấp.** `tang = (cau - tb_truoc) / tb_truoc * 100` (`:217`), không kiểm `NEN_TOI_THIEU`. Hằng số này có ở `:23` và F40 có dùng (`:286`). Một từ khoá đi từ 0,3 lên 1,0 là "+233%, rising".

**`sparkline_7d` là 7 tuần.** `tia[kw] = [... diem[-7:]]` (`:219`) lấy 7 điểm của chuỗi **tuần**. FE ghi "7 kỳ gần nhất" (`NichesPage.tsx:227`), trung thực, nhưng SRS đòi 7 ngày. Trong khi đó Mongo local có sẵn Trends theo ngày cho 44 từ khoá (2026-05-18 → 2026-10-17).

**Shop thật nhận một lời hứa suông.**
- Với shop live, `supply_pct`, `gap_score`, `n_listings` bị đặt `null` (`f39:83-87`).
- Bảng vẫn giữ **thứ tự theo gap seed** (`:50`, `:64-77`). Người dùng thấy một bảng xếp hạng mà cột lý do đã bị giấu.
- `limitation` hứa phần cung "sẽ tự hiện khi đủ dữ liệu" (`:100-102`). Không có dòng code nào tính cung từ dữ liệu live.
- `unlock.current` đếm **mọi** sản phẩm thật có tag (`:81-82`), nhưng mục tiêu ghi "≥ 20 listing cùng tag" (`:21`). Sai đơn vị. Mà đạt 20 cũng đéo mở khoá gì.

**BR-211 lọc kiểu bằng nhau, không phải "chứa".** `r["keyword"].lower().strip() not in cam` (`:55`) chỉ loại ngách trùng nguyên chuỗi với từ cấm. Cấm "naruto" thì "áo anime naruto" vẫn lọt. Còn nữa:
- Atlas mất kết nối thì `raise` (`:42-45`) thành 500. Không trả bảng hôm qua như Validation của SRS.
- `categoryId` ghép thẳng vào regex `f"^{categoryId}"` (`:60`), không escape.
- Không có tag nào khớp thì bộ lọc bị bỏ qua im lặng (`:61`). Trả về toàn sàn như thể đã lọc.

**BE đem ngách đi làm "tìm kiếm thịnh hành" cho người mua.** `trending-keywords.ts:37-48` gọi F39 với `X-Shop-Id: demo`, lấy `niches[].keyword` theo thứ tự `gap_score`. Ô người mua ghi "Tìm kiếm thịnh hành" (`SearchPopover.tsx:56`). Ngách xếp đầu là ngách cầu cao mà ít hàng nhất (theo seed). Tức là sàn chỉ người mua tới chỗ ít sản phẩm nhất. Đm, phễu ngược. AI tắt thì lấy 8 từ khoá cứng (`trending-keywords.ts:8-11`). Dòng chờ còn ghi "Đang cập nhật xu hướng từ AI Analyst..." (`SearchPopover.tsx:64`).

**Không đánh giá gì.** Test chỉ kiểm endpoint không trả 404 hoặc 500 (`tests/test_api_contract.py:53-60`). Chưa ai hỏi ngách xếp đầu tháng trước tháng này có tăng thật không.

### Lệch bản đăng ký
- **Công thức:** SRS là `growth × conversion / density`. Code là `pct(cầu) − pct(cung)`. Không có conversion.
- **Nguồn cầu:** SRS dùng search log sàn. Code dùng Google Trends. BE đã có `search_logs` (`BE/.../search-log.model.ts:9-16`) mà AI không đọc.
- **Đơn vị:** SRS tính theo tag. Code tính theo 45 từ khoá Trends; tag chỉ dùng để lọc danh mục.
- **Số dòng:** SRS là top 10. Code là `TOP_N = 20` (`f39:20`).
- **Màn hình:** thiếu cột lượng tìm, mức cạnh tranh Cao/Vừa/Thấp, sparkline 7 ngày. Thiếu panel tag liên quan và top 3 sản phẩm bán chạy: bấm dòng chỉ hiện một câu tóm tắt (`NichesPage.tsx:159-166`). Tên trang `NichesPage.tsx`, menu "Ngách tiềm năng" (`nav.ts:83`), khác `NicheOpportunitiesPage.tsx` và [Cơ hội ngách].
- **BR-210:** không có job nửa đêm GMT+7. Mart chỉ dựng khi chạy tay `run.py:161`. Job có lịch hiện có thuộc F29 (`f29_scheduler.py:131`, 00:00 UTC) và Listing Intel (`listing_intel/jobs.py:63-65`).
- **BR-211:** khớp bằng nhau, không phải "chứa".
- **Input:** SRS không có input. Code nhận `categoryId` (`f39:49`). Bổ sung thì được, nhưng phải ghi phụ lục.
- **Validation:** không có nhánh trả bảng hôm qua khi job lỗi.

## 2. Mổ xẻ lỗi

Lệch bản đăng ký: các dòng ghi mức "(SRS)" là chỗ code khác mục SRS đã đăng ký. Chúng được xếp Nặng trở lên vì hội đồng chấm theo bản đăng ký.

| # | Mức | Chỗ | Lỗi | Hậu quả | Sửa nhanh |
|---|---|---|---|---|---|
| 1 | Chết người | `build_marts.py:177-183,222-228`, `generate_seed.py:265,277-279` | Cung đếm trên tag seed sinh ngẫu nhiên | `gap_score` và thứ hạng một nửa là nhiễu | Cung lấy từ dữ liệu có thật (4.1); chưa có thì ẩn gap |
| 2 | Chết người | `trending-keywords.ts:37-48`, `SearchPopover.tsx:56` | Ngách ít hàng nhất được gọi là "Tìm kiếm thịnh hành" | Lừa người mua, đưa họ tới chỗ ít sản phẩm | Ô người mua lấy từ `search_logs` hoặc chỉ cầu; tách khỏi F39 |
| 3 | Chết người | `f39:100-102`, `:81-82,93-94` | Hứa cung "tự hiện khi đủ dữ liệu", nhưng không có code | Nói dối người dùng | Viết code tính cung live, hoặc xoá lời hứa |
| 4 | Nặng (SRS) | `build_marts.py:221-228` | Công thức Gap khác SRS, không có conversion | Trượt chấm theo đăng ký | Tính đúng `growth × conv / density` (4.3) |
| 5 | Nặng (SRS) | `build_marts.py:157-164` | Cầu từ Google Trends thay cho search log sàn | Lệch nguồn đã đăng ký | Đọc `search_logs`; Trends làm prior; ghi phụ lục |
| 6 | Nặng (SRS) | `f39:55` | BR-211 khớp nguyên chuỗi | Ngách chứa từ cấm vẫn lọt | Khớp chứa theo từ, đã bỏ dấu, trên cả từ khoá và tag |
| 7 | Nặng (SRS) | `run.py:161` | BR-210: không có job nửa đêm GMT+7 | Bảng không tươi; không có nhãn cập nhật đúng | Job APScheduler 00:00 `Asia/Ho_Chi_Minh`, theo mẫu `jobs.py` |
| 8 | Nặng (SRS) | `f39:20`, `NichesPage.tsx:218-232` | Top 20; thiếu cột cạnh tranh, lượng tìm, sparkline 7 ngày, panel chi tiết | Màn hình khác đăng ký | Top 10; thêm cột và panel |
| 9 | Nặng | `f39:50,64-77` | Shop live vẫn thấy thứ tự theo gap seed | Thứ hạng seed bị gán cho shop thật | Shop live xếp theo cầu, ghi rõ |
| 10 | Nặng | `build_marts.py:216-218` | Tốc độ tăng không chặn nền thấp | Từ khoá gần 0 thành "rising" | Áp `NEN_TOI_THIEU` như F40 |
| 11 | Vừa | `f39:42-45` | Atlas mất thì 500 | Validation SRS (trả bảng hôm qua) không chạy | Cache danh sách cấm có TTL; lỗi thì 503 kèm bảng cũ đã lọc |
| 12 | Vừa | `f39:60-62` | Regex không escape; không khớp thì bỏ lọc im lặng | Lọc sai; ReDoS nhẹ | `re.escape`; không khớp thì trả rỗng hoặc 400 |
| 13 | Vừa | `build_marts.py:219` | `sparkline_7d` là 7 tuần | Tên field nói dối | Dùng Trends ngày, hoặc đổi tên `sparkline_7w` |
| 14 | Vừa | `build_marts.py:243-245` | Góc phần tư cắt ở phân vị 50 | Luôn khoảng một nửa là "cầu cao" | Ngưỡng tuyệt đối chọn trên validation, hoặc bỏ nhãn |
| 15 | Nhẹ | `trending-keywords.ts:8-11`, `SearchPopover.tsx:64` | Fallback cứng; ghi "AI Analyst" | Gắn mác AI cho danh sách cứng | Ghi "gợi ý phổ biến" |

## 3. Tính năng này nên là AI gì

Seller cần biết: "Tag nào đang có người tìm nhiều hơn, mua tốt, mà ít người bán, để tôi thiết kế vào." Đây là **bài toán xếp hạng**. Giữ đúng công thức SRS làm điểm xếp hạng. Phần AI nằm ở chỗ ước lượng trung thực từng thành phần và kiểm chứng thứ hạng:

| Thành phần SRS | Ước lượng đề xuất | Khi chưa có dữ liệu thật |
|---|---|---|
| Tốc độ tăng lượng tìm | Tăng trưởng dự báo 4–8 tuần tới so với 4 tuần qua, dùng chung module dự báo với F38 | Trends VN, có chặn nền thấp |
| Conversion trung bình | Beta-binomial co về prior danh mục; hệ số `M_BAYES` đã chọn ở `docs/BAYES_M_SELECTION.md` | Sàn mới có 4 đơn, nên đặt hằng số prior. Công thức thành `growth / density`, ghi rõ trên trang. **Cần cập nhật SRS/phụ lục** cho giai đoạn này |
| Mật độ cạnh tranh | `log(1 + số listing đang bán có tag) − log(1 + cầu)` | Proxy thị trường: số listing tiki23 khớp từ khoá bằng chữ đã bỏ dấu (Listing Intel `normalize.fold`) |
| Mức cạnh tranh Cao/Vừa/Thấp | Chia tam phân vị theo mật độ | Như trên |

Nhãn để kiểm chứng: cầu thực tế ở T+4…T+12 sau khi xếp hạng ở mốc T. Sau này thêm view và đơn của listing mới tạo trong ngách. Không train ranker. Với 45 đơn vị xếp hạng, ranker học được gì cũng là overfit. Ranker chỉ đáng làm khi `search_logs` có hàng trăm tag.

## 4. Đường ra: thiết kế AI chính hiệu

### 4.1 Dữ liệu: train / validation / test / thực
- **Cầu:**
  - Trends tuần 2021-08-15 → 2026-08-16 (45 từ khoá).
  - Trends ngày 2026-05-18 → 2026-10-17 (44 từ khoá), dùng cho sparkline 7 ngày.
  - `search_logs` của sàn khi có. Mongo local `vietcraft-test` có 5.437 bản ghi, nhưng chỉ 21 từ khoá với số đếm gần đều nhau. Đó là dữ liệu test sinh ra, không dùng làm bằng chứng.
- **Cung thị trường:** tiki23, 41.575 dòng có danh mục và số bán. Khớp chữ đã bỏ dấu chỉ phủ khoảng 8,2% tiêu đề tiki26 (`LISTING_INTEL_REPORT.md` §8), nên phải báo độ phủ theo từ khoá. Khớp vector bị tắt vì chỉ đúng 1/100, không được bật lại.
- **Cung sàn:** sản phẩm Atlas có tag, lọc bằng `LOC_SP_THAT`. Khoảng 79 sản phẩm thì chưa đủ. Chỉ chuyển sang cung sàn khi một tag có ít nhất 20 listing thật (giữ đúng `NGUONG_CUNG_LIVE`).
- **Chia theo thời gian:** xếp hạng ở mốc T chỉ dùng dữ liệu đến T. Mốc cách nhau 4 tuần.
  - Validation: các mốc 2024-08 → 2025-08.
  - Test: các mốc 2025-08 → 2026-08, đọc một lần.
- **Giới hạn:** tiki23 là ảnh chụp một thời điểm, nên cung không đổi theo mốc. Backtest chỉ kiểm được vế cầu. Ghi rõ điều này.

### 4.2 Làm sạch và sanity
- **Gộp đồng nghĩa:** gom "áo thun", "in áo thun", "áo phông nam", "áo phông nữ" thành một cụm. Một cụm chỉ chiếm một ô trong top 10.
- **Nền thấp:** chặn `NEN_TOI_THIEU` cho vế tăng trưởng. Từ khoá có trên 50% tuần bằng 0 thì gắn cờ "dữ liệu thưa".
- **BR-211:** chuẩn hoá cả từ cấm lẫn ngách (chữ thường, bỏ dấu, tách từ), khớp theo cụm từ. Có test cho có dấu, không dấu, viết hoa và từ cấm nằm giữa chuỗi. Áp cả cho ô người mua.
- **Ranh giới tin cậy:** `categoryId` qua whitelist hoặc `re.escape`. Trả 400 nếu sai miền.
- **Sanity bắt buộc:**
  1. Xáo cầu tương lai giữa các từ khoá: precision@10 phải rơi về mức ngẫu nhiên.
  2. Xáo vế cung: thứ hạng phải đổi. Nếu không đổi thì cung không đóng góp gì, phải nói ra.
  3. Độ ổn định: Kendall tau giữa hai ngày liên tiếp cao. Nếu không cao, thứ hạng đang chạy theo nhiễu.
  4. Không còn bản ghi seed nào trong cung khi `mode="live"`.

### 4.3 Model
- **Baseline:**
  - (a) Chọn ngẫu nhiên 10.
  - (b) Độ phổ biến: top theo cầu hiện tại.
  - (c) Chỉ tăng trưởng 4 tuần so với 4 tuần.
  - (d) Code hiện tại (`pct` cầu trừ `pct` cung).
- **Chính:** `Gap = ĝ × ĉ / d̂`.
  - `ĝ` là tăng trưởng dự báo. Phương pháp dự báo chọn trên validation: seasonal naive hoặc STL kèm drift.
  - `ĉ` là conversion co Bayes.
  - `d̂` là mật độ như mục 3.
  - Cộng 1 để làm trơn, lấy log để một từ khoá cực lớn không đè hết.
- **Phiên bản khử mùa:** tính `ĝ` sau khi chia chỉ số mùa (`trend_axis.seasonal_index`, chỉ dùng dữ liệu quá khứ). Cách này tách "tăng vì sắp Tết", việc của F38, khỏi "tăng thật".
- **Tài nguyên:** chạy bằng numpy và statsmodels trên CPU, vài giây mỗi đêm.

### 4.4 Học từ dữ liệu thật
- **Lịch:** job 00:00 GMT+7 mỗi ngày (BR-210). Lỗi thì giữ bảng hôm qua, kèm `computed_at` cho nhãn "Dữ liệu cập nhật lúc…".
- **Feedback:** ghi log mỗi lần hiện ngách, mỗi lần bấm "Tạo sản phẩm", các listing tạo ra có tag ngách, rồi view và đơn của chúng sau 30 ngày. So listing trong ngách được gợi ý với listing cùng danh mục ngoài ngách.
- **Vòng phản hồi:** khi nhiều seller cùng vào một ngách thì cung tăng và gap tự giảm. Cần theo dõi tốc độ này để không đẩy mọi người vào cùng một chỗ.
- **Chuyển nguồn:**
  - Cầu chuyển sang `search_logs` khi một tag có ít nhất N user duy nhất mỗi tuần trong 8 tuần liền. N chọn sao cho sai số tăng trưởng đủ nhỏ.
  - Conversion chuyển sang dữ liệu thật khi một tag có ít nhất 30 lượt mua.
- **Drift:** độ xáo trộn thứ hạng theo tuần; tỉ lệ ngách được gợi ý mà cầu sau đó giảm.

### 4.5 Bảo mật và chống gian lận
- **Không có LLM**, nên không có prompt injection.
- **Đầu độc search log:** bot tìm một từ khoá liên tục để tạo ngách giả, lùa đối thủ vào chỗ chết. Phòng bằng cách:
  - chỉ đếm user hoặc phiên duy nhất;
  - loại lượt tìm của chính seller và tài khoản mới tạo;
  - giới hạn tần suất;
  - phát hiện đột biến từ một nhóm nhỏ user.
- **Thổi phồng cung:** seller tạo nhiều listing ẩn để ngách trông đông đúc, doạ đối thủ. Chỉ đếm listing đang bán, hiển thị, có ít nhất 1 view; gộp tiêu đề gần trùng.
- **PII:** `search_logs` có `user_id`. Chỉ xuất số tổng hợp, và chỉ khi một từ khoá có ít nhất 5 user duy nhất trong tuần. Không trả từ khoá thô mà ít người tìm.
- **Pháp lý:** BR-211 áp cho cả F39 lẫn ô người mua. Danh sách cấm đọc lỗi thì không hiện ngách (đóng an toàn), nhưng trả 503 kèm bảng cũ đã lọc.
- **Input:** regex `categoryId` (lỗi số 12).

### 4.6 Benchmark và kiểm chứng
- **Nhãn định nghĩa trước khi chạy:** một ngách "tăng thật" khi trung bình cầu ở T+4…T+12 ≥ 1,2 × trung bình 12 tuần trước T, và nền ≥ `NEN_TOI_THIEU`.
- **Metric:**
  - Precision@10.
  - NDCG@10, lấy tăng trưởng thực làm gain.
  - Spearman giữa điểm và tăng trưởng thực.
  - Cả bản thô và bản khử mùa.
- **So sánh:** với 4 baseline ở 4.3. Bootstrap theo khối mốc thời gian, cụm theo từ khoá; ghép cặp với baseline tốt nhất.
- **Cổng đạt:** trên các mốc test, precision@10 của model trừ baseline tốt nhất > 0, CI 95% không chứa 0. Thêm điều kiện: sanity xáo nhãn rơi về mức ngẫu nhiên.
- **Nói trước:**
  - 45 từ khoá thì top 10 đã là 22% tập, độ mạnh thống kê thấp.
  - Nhiều từ khoá theo dịp, nên "tăng" phần lớn đoán được từ lịch.
  - Nếu không thắng baseline (c) hoặc (b), ship baseline đó, ghi "xếp theo tăng trưởng tìm kiếm", và giữ công thức SRS để chạy khi có search log thật.
- **Vế cung:** chưa kiểm được bằng lịch sử. Kiểm sau trên dữ liệu sàn: so đơn mỗi listing trong ngách được gợi ý với nhóm đối chứng cùng danh mục.

## 5. Lộ trình

| Giai đoạn | Việc | Kết quả kiểm chứng |
|---|---|---|
| Ngay 1–2 ngày | Tách ô "Tìm kiếm thịnh hành" khỏi F39; xoá lời hứa cung live; BR-211 khớp chứa; escape `categoryId`; chặn nền thấp; top 10; đổi tên sparkline hoặc dùng dữ liệu ngày | Test BR-211 có dấu và không dấu; test regex; grep không còn `X-Shop-Id: demo` cho người mua |
| 1–2 tuần | Công thức `ĝ × ĉ / d̂` với cung tiki23; cột cạnh tranh Cao/Vừa/Thấp; panel tag liên quan và top 3 bán chạy; job 00:00 GMT+7 kèm bảng hôm qua; script backtest `scripts/f39/` có test | Bảng 4.6 kèm CI; sanity xáo nhãn đạt |
| Khi có dữ liệu thật | Cầu từ `search_logs`; cung và conversion từ sàn; feedback listing tạo theo ngách | Precision@10 trên dữ liệu sàn; đơn mỗi listing so với đối chứng |

**Xong khi:**
- Không còn số cung từ seed trên trang của shop thật.
- Bảng 4.6 có số kèm CI.
- Có test cho BR-211 và cho công thức.
- Khớp endpoint và các BR của mục SRS 3.10.3:
  - `GET /api/analytics/forecast/niches`, không bắt buộc input.
  - Top 10 tag, cột lượng tìm, cạnh tranh Cao/Vừa/Thấp, Gap Score, sparkline 7 ngày, panel chi tiết.
  - BR-210: tính lại lúc 00:00 GMT+7, lỗi thì trả bảng hôm qua kèm mốc cập nhật.
  - BR-211: lọc ngách **chứa** từ cấm.
  - Ghi phụ lục cho các chỗ lệch có lý do: Trends thay search log, Mongo thay Redis/PostgreSQL, conversion là hằng số prior.

## 6. Hội đồng sẽ hỏi

1. **"Gap Score có đúng công thức đăng ký không?"** Hiện tại không: đang là hiệu hai phân vị. Bản sửa tính đúng `growth × conversion / density`. Conversion tạm là hằng số prior vì sàn mới có 4 đơn, và điều này ghi trên trang lẫn trong phụ lục.
2. **"Cung lấy ở đâu?"** Đang lấy từ listing seed có tag ngẫu nhiên, nên vô nghĩa. Bản sửa dùng số listing Tiki khớp từ khoá làm proxy thị trường, chuyển sang sàn khi một tag có ít nhất 20 listing thật.
3. **"Làm sao biết ngách gợi ý là đúng?"** Backtest: xếp hạng ở mốc T, chấm cầu thật ở T+4…T+12. So precision@10 với chọn ngẫu nhiên, theo độ phổ biến và chỉ theo tăng trưởng, có CI bootstrap.
4. **"Sao ô tìm kiếm của người mua lại dùng F39?"** Đó là lỗi: lấy ngách ít hàng gọi là "thịnh hành". Sẽ tách ra, dùng `search_logs` hoặc chỉ vế cầu.
5. **"Sao không train model?"** Mới có 45 đơn vị xếp hạng và chưa có nhãn chuyển đổi thật. Một công thức minh bạch, có backtest, trung thực hơn một ranker overfit.
