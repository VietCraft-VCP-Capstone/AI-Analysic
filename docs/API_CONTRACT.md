# API_CONTRACT — module Product Analytics (F26–F41)

> **Draft do máy dựng 21/09/2026.** Đường dẫn và business rule lấy từ
> `context/report3.pdf` mục 3.8–3.10; hình dạng JSON lấy từ
> `plan/IMPLEMENT_F26_F41.md` mục 3. **Đạt đọc lại và chốt** — chỗ nào lệch ý thì sửa,
> đừng viết lại từ đầu.
>
> Mục đích của file này: **FE bắt đầu dựng màn hình mà không phải chờ BE làm xong.**
> Đó là lý do duy nhất nó tồn tại. Khoá và tên bảng mart thì đã nằm trong code
> (`app/core/writer.py` → `MART_SCHEMA`), không lặp lại ở đây.

---

## 1. Quy ước chung — áp cho cả 16 endpoint

### Xác thực
```
Authorization: Bearer <JWT>
```
`shopId` **luôn lấy từ JWT**, không nhận từ query. `BR-174` và `BR-177`: người bán
chỉ xem được dữ liệu shop mình sở hữu. Endpoint nào nhận `listingId` phải kiểm
listing đó thuộc shop trong token, không thì `403`.

### Mọi phản hồi đều có khối `meta`

> Khuôn này **gộp** hai tài liệu có trước: `HYBRID_AI_MVP_DATA_CONTRACT.md`
> (khối `source` / `quality`) và yêu cầu 3 trường của cổng ra. Trước 21/09 hai nơi
> quy định hai khuôn khác nhau — ai làm theo cái này thì vi phạm cái kia mà không
> biết. **Đây là bản duy nhất còn hiệu lực.**

```json
{
  "data": { },
  "meta": {
    "computed_at": "2026-09-21T06:00:00Z",
    "model_version": "daily-1.0",
    "scope": "listing_day",

    "source": {
      "database": "vietcraft-seed",
      "collection": "listing_daily",
      "mode": "seed_demo",
      "attributed_to_live_shop": false
    },
    "quality": {
      "status": "ready",
      "sample_size": 796025,
      "identity_linked": true,
      "confidence": "high"
    }
  }
}
```

**`computed_at` · `model_version` · `scope`** — cổng ra kiểm đúng ba trường này.
Job ghi vào mart, API chỉ đọc ra.

**`source.mode`** ∈ `live` · `seed_demo` · `derived` — **bắt buộc**.
FE phải hiện nhãn cảnh báo khi giá trị là `seed_demo`. Dữ liệu mồi mà trình bày như
số thật là lỗi nặng nhất của loại dashboard này.

**`source.attributed_to_live_shop`** — dữ liệu mồi **không bao giờ** được gán cho một
shop có thật trên sàn. Bảng `vietcraft-seed` và `vietcraft` là **hai miền khác nhau**.

**`quality.status`** ∈ `ready` · `limited` · `insufficient_data`.
**`quality.identity_linked`** = đã nối được sang khoá định danh thật chưa.

> ⚠️ **Quy tắc định danh — đọc `LIVE_ANALYTICS_IDENTITY_CONTRACT.md` trước khi ghép bảng:**
> ```
> Live : product_id  (MongoDB ObjectId)  — vietcraft.products._id
> Seed : listing_id  (lst_*)             — vietcraft-seed.listing_daily
> ```
> **KHÔNG join hai miền bằng tiêu đề, vị trí, SKU hay ID bịa ra.** Muốn nối phải có
> bảng ánh xạ tường minh. Một rollup live chỉ được phơi `listing_id = live_<product_id>`
> như trường hiển thị cho tương thích — khoá nguồn vẫn là `product_id`.

### Nguồn cho từng loại tính năng

Lấy từ `HYBRID_AI_MVP_DATA_CONTRACT.md`:

| Loại | Nguồn | Ghi chú |
|---|---|---|
| Cửa hàng · catalog · giá | live `vietcraft` | |
| Phễu live | `vietcraft.product_events` + `product_daily_metrics` | **chưa deploy** → trả `insufficient_data` |
| Phễu demo | `vietcraft-seed.listing_daily` | `mode: seed_demo`, **không bao giờ** là live |
| Xu hướng · mùa vụ | `data-collection.trend_interest` | dữ liệu THẬT |
| Đối thủ | chỉ catalog live | không có snapshot thì **không được phát biểu về hiệu suất** |
| Doanh thu | live `orders.items` hoặc seed `orders`/`order_items` | luôn kèm nhãn nguồn |

### THIẾU ≠ 0 — quy ước quan trọng nhất
Không đủ dữ liệu thì **không được trả `0`**:
```json
{"data": null, "status": "insufficient_data",
 "reason": "Listing mới tạo 3 ngày, cần tối thiểu 7 ngày",
 "meta": { }}
```
Shop mới nhìn thấy *"doanh thu 0đ"* thay vì *"chưa đủ dữ liệu"* là lỗi nặng nhất của
loại dashboard này. FE phải dựng **trạng thái rỗng thân thiện** cho mọi màn hình.

`status` nhận: `ok` · `insufficient_data` · `partial` (có số nhưng độ tin cậy thấp).

### Lỗi
| Mã | Khi nào | Body |
|---|---|---|
| `400` | Tham số sai kiểu / ngoài miền | `{"error":"invalid_param","field":"timeRange"}` |
| `401` | Thiếu hoặc hết hạn JWT | `{"error":"unauthorized"}` |
| `403` | Xem dữ liệu không thuộc shop mình | `{"error":"forbidden"}` |
| `404` | `listingId` không tồn tại | `{"error":"not_found"}` |
| `503` | Job chưa chạy lần nào, mart rỗng | `{"error":"mart_not_ready","collection":"mart_demand"}` |

**Không có `500` cho chuyện mart rỗng.** Mart rỗng là trạng thái bình thường trước
lần chạy job đầu tiên — trả `503` kèm tên bảng để biết chờ job nào.

### Tiền tệ và thời gian
- Mọi số tiền: **VND, số nguyên, không phần thập phân**. Tên trường kết thúc `_vnd`.
- Mọi ngày: `YYYY-MM-DD`. Mọi mốc thời gian: ISO 8601 UTC kết thúc `Z`.
- **Riêng heatmap của F31**: giờ và thứ đã quy về **giờ Việt Nam (GMT+7)** ở tầng job,
  FE không phải đổi nữa (`BR-185`).

### Hiệu năng
Mọi endpoint là `GET` và **chỉ đọc mart đã tính sẵn** — không tính lúc gọi.
SRS đặt hạn `AI service timeout > 5s` là lỗi (MSG132), nên mục tiêu **p95 < 500ms**.
Endpoint nào cần tính toán là thiết kế sai, đẩy về job chạy đêm.

### Nguồn lúc CHẠY THẬT chỉ là MongoDB

Mọi endpoint đọc từ MongoDB. **CSV và file xuất ra không bao giờ là đầu vào lúc chạy.**

> Thư mục `vc-data/` là ngoại lệ **chỉ cho việc làm mô hình ngoại tuyến** — train, đo,
> chạy thử. Không API nào được đọc từ đó.

---

## 2. Hợp đồng bảng rollup live — `product_daily_metrics`

> Gộp từ `LIVE_ANALYTICS_IDENTITY_CONTRACT.md` ngày 21/09.
> Bảng này **chưa tồn tại** — event tracking trên sàn thật chưa deploy. Nhưng khi
> dựng thì phải theo đúng hợp đồng dưới, nếu không mọi tính năng cấp live đều lệch.

### Trường bắt buộc

```text
product_id        khoá nguồn, MongoDB ObjectId
shop_id
date
views
add_to_carts
orders_count      SỐ ĐƠN ĐÃ THANH TOÁN RIÊNG BIỆT — không phải số dòng hàng
units_sold        tổng quantity của các dòng hàng
revenue
favorited_count
```

### Quy tắc gộp

- **Khoá upsert: `(product_id, date)`.**
- `orders_count` đếm **đơn riêng biệt**. Một đơn có 3 sản phẩm thì mỗi sản phẩm
  cộng **1** đơn, không phải 3. Đây là chỗ hay tính sai nhất.
- **Vi phạm phễu thì TỪ CHỐI và ghi log.** Không bao giờ âm thầm nâng số nguồn lên
  cho khớp — `orders ≤ add_to_carts ≤ views` là điều kiện, không phải thứ để ép.
- ⚠️ **Thiếu metadata sản phẩm là LỖI CHẤT LƯỢNG, không phải lý do điền chuỗi rỗng.**

  > Bỏ qua quy tắc này đã trả giá thật: `listing_daily` có **796.025 dòng với
  > `shop_id` / `product_type_id` / `category_id` / `tags` rỗng 100%** suốt 3 tuần
  > mà không ai biết, vì `task9_listing_daily.py:142` dùng `merge(how="left")` rồi
  > để `NaN` thành chuỗi rỗng. Mọi màn hình cấp shop trống rỗng vì lỗi đó.
  > Thiếu thì **raise**, đừng điền `""`.

- Bảng mồi `vietcraft-seed.listing_daily` **không được join** sang
  `vietcraft.product_daily_metrics` nếu chưa có bảng ánh xạ tường minh.
- Rollup live được phơi `listing_id = live_<product_id>` **chỉ như trường hiển thị
  cho tương thích** — khoá nguồn vẫn luôn là `product_id`.

---

## 3. Bảng 16 endpoint

| F | Method · Path | Tham số | Đọc mart | Người làm |
|---|---|---|---|---|
| F26 | `GET /api/analytics/shop/overview` | `timeRange` | `listing_daily` ⁽¹⁾ | Hiếu |
| F27 | `GET /api/analytics/listings/{id}/timeseries` | `timeRange` | `listing_daily` ⁽¹⁾ | Hiếu |
| F28 | `GET /api/analytics/listings/{id}/conversion` | — | `mart_listing_quality` | Hạt |
| F29 | `GET /api/analytics/listings/{id}/health` | — | `listing_health` | Hạt |
| F30 | `GET /api/notifications/alerts` | `period` | `anomaly_event` | Hiếu |
| F31 | `GET /api/analytics/shop/categories/revenue` | `timeRange` | `listing_daily` ⁽¹⁾ | Hiếu |
| F32 | `GET /api/analytics/competitors` | `categoryId` | `mart_competitor` | Nhi |
| F33 | `GET /api/analytics/shop-comparison` | — | `mart_competitor` | Nhi |
| F34 | `GET /api/analytics/tag-gap` | `categoryId` | `mart_competitor` | Đạt |
| F35 | `GET /api/analytics/pricing` | `productType`, `price` | `mart_competitor` | Nhi |
| F36 | `GET` · `POST` · `DELETE /api/analytics/competitor-tracking` | `shopId` (body) | `mart_competitor` | Đạt |
| F37 | `GET /api/analytics/forecast/revenue` | `targetId`, `window` | `forecast_point` | Đạt |
| F38 | `GET /api/analytics/forecast/seasonal` | `categoryId?` | `seasonal_profile` | Hưng |
| F39 | `GET /api/analytics/forecast/niches` | `categoryId?` | `niche_score` | Hưng |
| F40 | `GET /api/analytics/forecast/radar` | — | `mart_demand` | Hưng |
| F41 | `GET /api/analytics/forecast/recommendations` | — | gộp 3 mart | Đạt |

⁽¹⁾ Trước ghi là `mart_listing_daily`. Bảng đó **bị chặn** trong `writer.BLOCKED` —
xem mục 7. Đọc thẳng `vietcraft-seed.listing_daily`, đã backfill đủ 4 cột khoá và có index.

**F36 là endpoint duy nhất có ghi** (`POST` thêm shop theo dõi, `DELETE` bỏ theo dõi).
15 cái còn lại chỉ đọc.

---

## 4. Chi tiết từng endpoint

Dưới đây chỉ ghi phần `data`. Khối `meta` mặc định như mục 1.

### F26 · `GET /api/analytics/shop/overview`
`timeRange` ∈ `7d | 30d | 90d`
```json
{"range":"30d",
 "kpi":{"views":{"value":48210,"pop_pct":12.4},
        "orders":{"value":1392,"pop_pct":-3.1},
        "revenue_vnd":{"value":284500000,"pop_pct":8.8},
        "conversion_pct":{"value":2.89,"pop_pct":-1.2}},
 "series":[{"date":"2026-08-01","views":1520,"orders":44,"revenue_vnd":9240000}],
 "top_products":[{"listing_id":"lst_000123","title":"...","revenue_vnd":18400000}],
 "recent_feedback":[]}
```
`BR-175` kỳ so sánh phải **đúng bằng độ dài** khoảng đã chọn, liền trước nó.
`BR-176` CR toàn shop = `orders / views × 100`. **0 lượt xem → CR trả `null`**, không chia cho 0.

### F27 · `GET /api/analytics/listings/{id}/timeseries`
```json
{"listing_id":"lst_000123",
 "series":[{"date":"2026-08-01","views":412,"carts":31,"orders":12,"revenue_vnd":2508000}],
 "category_median":[{"date":"2026-08-01","views":260}],
 "trend":{"views":"up","orders":"flat"},
 "status":"ok"}
```
`BR-178` gắn cờ tăng/giảm khi **độ dốc hồi quy** vượt ±5%.
Listing dưới 7 ngày → `status: insufficient_data`, **không vẽ trend badge**.

### F28 · `GET /api/analytics/listings/{id}/conversion`
```json
{"listing_id":"lst_000123",
 "funnel":{"views":1204,"carts":86,"orders":35},
 "view_to_cart_pct":7.14,"cart_to_order_pct":40.7,"view_to_order_pct":2.91,
 "category_avg_pct":2.64,"cr_index":1.10,
 "weakest_step":"view_to_cart",
 "tips":[{"issue":"Chỉ 7,1% người xem thêm vào giỏ, danh mục là 9,8%",
          "action":"Ảnh đầu tiên nên chụp sản phẩm đang được dùng thật"}]}
```
`BR-179` **chỉ hiện `tips` khi CR thấp hơn trung bình danh mục ≥ 20%**. Không thì mảng rỗng.

### F29 · `GET /api/analytics/listings/{id}/health`
```json
{"listing_id":"lst_000123","health_score":73.4,"band":"cần cải thiện",
 "conversion_rate":0.0291,"category_avg_cr":0.0264,"cr_index":1.10,
 "rating_shrunk":4.31,"n_reviews":12,
 "breakdown":{"conversion":{"score":55,"weight":0.30},
              "rating":{"score":86,"weight":0.25},
              "content":{"score":70,"weight":0.20},
              "stock":{"score":90,"weight":0.15},
              "freshness":{"score":40,"weight":0.10}},
 "todo":[{"priority":1,"action":"Thêm ảnh: hiện có 2, trung vị danh mục là 5",
          "expected_gain":"+8 điểm"}],
 "status":"ok"}
```
`BR-182` dải màu: **≥ 80 `tốt` (xanh) · 50–79 `cần cải thiện` (vàng) · < 50 `kém` (đỏ)**.
Trọng số phải **cộng đúng 1.0** — cổng ra kiểm.
Listing chưa có đánh giá → `rating_shrunk: null`, **không mặc định 4.0 sao**.

### F30 · `GET /api/notifications/alerts`
```json
{"alerts":[{"listing_id":"lst_000123","date":"2026-09-18","direction":"drop",
            "z":-10.6,"expected":1940000,"actual":520000,
            "severity":"high","calendar_sensitive":false,
            "confidence":"ok"}]}
```
⚠️ **Ngưỡng là `|z| > 7.0`, KHÔNG phải 2.0 như `BR-183`.** Nhóm đo thực nghiệm: ngưỡng
2.0 cho **7,38% báo động giả**, ngưỡng 7.0 còn **0,6%**. Code đúng hơn SRS — đã ghi
lệch vào `docs/SPEC_CHANGES.md` và phải sửa SRS.
`confidence` nhận `ok` · `calendar_sensitive` · `limited_few_cycles` · `unreliable_high_rate`.
`BR-184` chỉ gửi email khi người bán bật "Cảnh báo hiệu suất".

### F31 · `GET /api/analytics/shop/categories/revenue`
```json
{"by_product_type":[{"product_type_id":"tshirt_men","name_vi":"Áo thun nam",
                     "revenue_vnd":18400000,"orders":78,"share_pct":31.2}],
 "heatmap":[{"dow":1,"hour":20,"orders":34}],
 "peak_window":{"dow":"Chủ nhật","hour":21,"note":"18% đơn rơi vào khung này"}}
```
⚠️ **Endpoint này BẮT BUỘC trả `meta.source.mode = "seed_demo"`.** Nhịp giờ/thứ trong
dữ liệu mồi kế thừa từ phân phối Olist (Brazil) — xem
`plan/huong-dan/BOI_CANH_VA_BAN_CHAT.md`. FE phải hiện nhãn khi gặp `seed_demo`:
*"Nhịp giờ/thứ kế thừa từ dữ liệu tham chiếu quốc tế, chưa phản ánh người mua Việt Nam."*
Khi sàn có đủ đơn thật, job đổi `mode` thành `live` và nhãn tự biến mất.
`BR-185` giờ đã quy về GMT+7 ở tầng job.

### F32 · `GET /api/analytics/competitors?categoryId=`
```json
{"category_id":"apparel",
 "my_listings":[{"listing_id":"lst_000123","price_vnd":237000,"rank_in_cat":17}],
 "competitors":[{"rank":1,"listing_id":"lst_004821","shop_name":"...","price_vnd":198000,
                 "est_sales_90d":214,"rating_shrunk":4.7,"n_reviews":88,
                 "favorite_count":1204}],
 "my_position":{"price_percentile":92,"rating_percentile":41}}
```
`BR-188` **top 20 xếp theo `est_sales_90d` giảm dần**. `BR-189` loại shop của chính
người bán khỏi bảng xếp hạng, nhưng vẫn hiện riêng ở `my_listings`.
`BR-186` dropdown danh mục chỉ liệt kê danh mục người bán có ≥ 1 listing.

### F33 · `GET /api/analytics/shop-comparison`
```json
{"segment":"apparel",
 "axes":["listing_count","avg_rating","response_speed","avg_price","product_diversity"],
 "me":[62,78,45,55,71],
 "competitors":[{"shop_id":"shp_00042","shop_name":"...","values":[88,82,90,61,84]}]}
```
`BR-190` phân khúc xác định **tự động** = danh mục chiếm tỉ trọng lớn nhất.
`BR-191` 5 shop = top 5 theo doanh thu ước tính. `BR-192` chuẩn hoá min–max về 0–100.
`BR-193` cần shop có **≥ 5 listing đã đăng**, không thì `insufficient_data`.

### F34 · `GET /api/analytics/tag-gap?categoryId=`
```json
{"category_id":"apparel","competitors_scanned":20,
 "missing_tags":[{"tag_id":"ao-cap-doi","name":"áo cặp đôi",
                  "used_by_competitors":14,"competitor_share_pct":70,
                  "demand_index":58.2,
                  "estimated_traffic_gain":{"low_pct":8,"high_pct":15,
                                            "basis":"correlational"}}],
 "note":"Ước lượng là tương quan, không phải nhân quả."}
```
⚠️ Đây là **phép trừ tập hợp** — tag đối thủ có mà mình không có. **Không phải** gợi ý
tag từ tiêu đề (quyết định **E22**; bản cũ làm nhầm bài toán).
`BR-194` cần ≥ 10 listing cạnh tranh. `BR-196` traffic gain **phải là KHOẢNG %** và
**phải ghi rõ là ước lượng** — FE không được hiển thị một con số đơn.
`BR-197` xếp giảm dần theo traffic gain.

### F35 · `GET /api/analytics/pricing?productType=&price=`
```json
{"product_type_id":"tshirt_men","n_listings":36,
 "distribution":{"min":150000,"p10":168000,"p25":185000,"p50":237000,
                 "p75":325000,"p90":368000,"max":391000},
 "my_price":480000,"percentile":100,"band":"far_above",
 "suggested_range":{"low":198000,"high":268000,
                    "basis":"khoảng giá của 10 listing bán chạy nhất",
                    "caveat":"tương quan"}}
```
`band` ∈ `far_below · below · competitive · premium · far_above`.
`BR-198` phân bố tính từ **top 20 listing theo doanh số**, không phải toàn bộ listing.
`BR-200` người bán chưa có listing loại đó → vẫn vẽ biểu đồ, bỏ vạch của mình.
⚠️ Quyết định **E21**: endpoint này **KHÔNG hứa "giá nào bán chạy hơn"**. Đo được chỉ
**24/94** loại phôi có thứ tự giá `hot > medium > tail` — gần mức ngẫu nhiên. Chỉ trả lời
*"giá này đứng ở đâu"*.

### F36 · `/api/analytics/competitor-tracking`
```
GET    → danh sách đang theo dõi + cảnh báo
POST   {"shop_id":"shp_00042"}   → thêm
DELETE {"shop_id":"shp_00042"}   → bỏ
```
```json
{"tracked":[{"shop_id":"shp_00042","shop_name":"...","added_at":"...","new_listings_7d":3}],
 "alerts":[{"shop_id":"shp_00042","listing_id":"...","title":"...",
            "detected_at":"...","in_my_niche":true}]}
```
`BR-201` **tối đa 10 shop** → vượt thì `400 {"error":"tracking_limit_reached","limit":10}`.
`BR-202` trùng shop → `400 {"error":"already_tracked"}`.
`BR-203` chỉ báo khi sản phẩm mới rơi vào ngách đang hoạt động.
`BR-204` bỏ theo dõi **dừng cảnh báo tương lai, không xoá cảnh báo cũ**.

### F37 · `GET /api/analytics/forecast/revenue?targetId=&window=`
`window` ∈ `30 | 60 | 90`
```json
{"scope":"shop","target_id":"shp_00017","horizon_days":30,"model":"arima",
 "points":[{"date":"2026-10-01","yhat":1840000,"lo95":980000,"hi95":2710000}],
 "validation":{"metric":"MASE","value":0.87,"baseline":1.00,"n_origins":8},
 "status":"ok"}
```
⚠️ **`BR-206`: khoảng tin cậy 95% LUÔN phải trả về.** `lo95`/`hi95` **không được null**
khi `status: ok` — FE vẽ vùng mờ giữa hai đường.
`BR-207` **`lo95` kẹp ở 0** — không dự báo doanh thu âm.
`BR-205` chọn mô hình: `arima` khi lịch sử < 90 ngày, `lstm` khi ≥ 90 ngày.
Dưới 7 ngày lịch sử → `insufficient_data`, thông điệp MSG:
*"Không đủ dữ liệu lịch sử để chạy mô hình dự báo"*.
Quyết định **E20**: dự báo ở **cấp shop**, không cấp listing (ARIMA cấp listing MASE 1,12 — thua mốc ngây thơ).

### F38 · `GET /api/analytics/forecast/seasonal?categoryId=`
```json
{"tag":"qua-tang",
 "decomposition":{"trend":[],"seasonal":[],"residual":[]},
 "events":[{"name":"Tết","date":"2027-02-06","driver":"lunar",
            "peak_offset_days":-11,
            "launch_window":{"start":"2026-12-20","end":"2027-01-10"},
            "amplitude":468.7}],
 "content_calendar":[{"week":"2026-W48","action":"Đăng sản phẩm quà 20/11"}]}
```
`BR-208` cần **≥ 12 tháng** dữ liệu. `BR-209` cửa sổ ra hàng trừ lùi thời gian in +
giao, mặc định **−21 ngày**.
Danh mục không có mùa vụ rõ → MSG150 *"Ngành hàng này có nhu cầu ổn định quanh năm"*.
✅ Endpoint này trả `meta.source.mode = "live"` — chạy trên Google Trends Việt Nam
**thật** (`data-collection.trend_interest`), không cần nhãn cảnh báo.

### F39 · `GET /api/analytics/forecast/niches?categoryId=`
```json
{"niches":[{"rank":1,"tag_id":"ao-cap-doi","demand_pct":91,"supply_pct":22,
            "gap_score":69,"n_listings":14,"demand_index":58.2,"trend":"rising",
            "sparkline_7d":[12,14,13,18,22,25,31]}],
 "computed_at":"..."}
```
`BR-210` tính lại mỗi 24h lúc nửa đêm GMT+7.
⚠️ `BR-211` **bắt buộc lọc bỏ ngách chứa từ khoá cấm** (bản quyền / NSFW) — đọc
collection `banned_keywords` trên sàn live. Chưa lọc thì không được bật endpoint này.

### F40 · `GET /api/analytics/forecast/radar`
```json
{"week":"2026-W38",
 "top_tags":[{"rank":1,"tag_id":"ao-cap-doi","growth_pct":39.6,
              "momentum":0.71,"searches_per_week":412}],
 "radar":{"axes":["Animals","Tech","Tết","Anime","Decor"],"values":[71,44,88,62,39]}}
```
`BR-212` radar **chỉ vẽ danh mục lớn**; tag chi tiết nằm ở danh sách bên dưới.
`BR-213` Momentum Score cần **≥ 100 lượt tìm/tuần** — dưới ngưỡng thì loại khỏi bảng.

### F41 · `GET /api/analytics/forecast/recommendations`
```json
{"shop_id":"shp_00017","generated_at":"...",
 "recommendations":[{"priority":1,"action":"scale",
   "target":{"type":"product_type","id":"tshirt_men","name_vi":"Áo thun nam"},
   "why":["cầu tag ao-cap-doi tăng 39,6%","shop đang xếp hạng 3/42 ở loại này"],
   "expected":"doanh thu tháng tới +40% nếu tăng ngân sách 20%",
   "confidence":"medium"}]}
```
`BR-214` **phải cá nhân hoá** theo lịch sử — không gợi ý loại phôi mà shop có 0% chuyển đổi.
`BR-215` **tối đa 5 khuyến nghị**.
Shop mới chưa có lịch sử → trả khuyến nghị chung toàn sàn, `scope: "platform"`.

### Shop thật ở F32 · F33 · F34 · F36 — thêm 17/10/2026

Shop id là ObjectId của sàn thì 4 endpoint **tính tại chỗ từ DB sàn** (`app/api/v1/_competitor_live.py`),
không đọc `mart_competitor` và không có bảng mới. Shop thật chỉ so với shop thật. Hình dạng `data` giữ nguyên, khác biệt:

- `meta.source.mode = "live"`, `attributed_to_live_shop = true`, `quality.identity_linked = true`.
- `category_id` là slug danh mục **cấp 1** của sàn; kèm tên: `category_names` (F32, F34), `segment_name` (F33).
- F32: mỗi đối thủ kèm `shop_id` để theo dõi ngay trên bảng. `est_sales_90d` = số sản phẩm của đơn
  `DELIVERED` trong 90 ngày, không tính đơn mô phỏng hay dữ liệu mồi (`seed_ref`).
- F32, F34: không truyền `categoryId` thì mở **danh mục chính** (danh mục shop có nhiều sản phẩm nhất), áp dụng cả hai miền.
- `listing_id` của shop thật chính là `product_id` (mở thẳng được trang sức khoẻ sản phẩm F27–F29).
- F33: trục thiếu dữ liệu là `null`, đứng ngoài min–max; `axes_missing` liệt kê trục thiếu của shop mình.
  Mỗi đối thủ kèm `raw` (số thật từng trục, cùng đơn vị `me_raw`) để FE so "bạn vs nhóm" bằng số thật.
- F34: thêm `tag_names` (mã tag -> tên, gồm cả tag của shop mình) và `leader_tags`
  (`[{tag_id, used_by, mine}]`, tối đa 12 tag nhóm dẫn đầu hay dùng).
- F36: danh sách theo dõi **là follow của sàn** (`shop_followers`), tối đa 10. POST/DELETE của shop thật
  do BE ghi; gọi thẳng module AI thì `400`. Cảnh báo = sản phẩm đối thủ đăng trong 7 ngày, trùng tag hoặc
  danh mục, có `listed_at`, `tag_names`, `alerts_computed_at`. `added_at` luôn `null`. Bỏ theo dõi thì
  cảnh báo của shop đó không còn hiện (chưa giữ được BR-204 vì không lưu cảnh báo).
- F35 giữ chế độ `derived` so với catalog tham chiếu. Catalog trống thì so giá thật cùng danh mục trên sàn.

### AI đối thủ (độ giống sản phẩm) — thêm 18/10/2026, chỉ shop thật

Bộ máy `app/api/v1/_doi_thu_ai.py`: TF-IDF (tên + từ khoá có dấu, mô tả nhẹ hơn, cụm ký tự của tên) và độ giống
cosine. Chỉ so **cùng loại hàng** (danh mục lá), khác shop, và phải có ít nhất một từ hiếm chung hoặc giống ≥ 0,35.
Đo chất lượng: `scripts/danh_gia_doi_thu_ai.py`.

- F32 `my_listings[].direct_rivals`: `[{product_id, shop_id, shop_name, title, price_vnd, est_sales_90d,
  similarity (0–1), reasons[]}]`, tối đa 5. `direct_rival_shops`: `[{shop_id, shop_name, overlap, best_similarity}]`,
  tối đa 3 shop trùng nhiều sản phẩm của mình nhất.
- F35 (khi đã chọn `productId`) `ai_price`: `{suggested_vnd, low_vnd, high_vnd, confidence: high|medium|low,
  rival_weight, n_neighbors, avg_similarity, rival_price_min_vnd, rival_price_max_vnd, neighbors[], method}` hoặc
  `null` kèm `ai_price_reason`. Giá = trung vị có trọng số độ giống của tối đa 8 sản phẩm giống nhất, pha với mặt
  bằng cùng loại theo `rival_weight`.
- F36 `alerts[].threat`: `{score 0–100, level high|medium|low, similarity, matched_product_id, matched_title,
  price_gap_pct (> 0 là đối thủ rẻ hơn), shop_strength}`. Điểm = độ giống với sản phẩm khớp nhất của mình (đủ 0,6 là
  tối đa) × sức mạnh shop đối thủ (doanh số 90 ngày so với shop lớn nhất) × áp lực giá (rẻ hơn, tối đa +50%).
  Cảnh báo xếp theo `threat.score` giảm dần. `surging`: `[{shop_id, shop_name, last_week, baseline, ratio, z}]` —
  shop đang theo dõi có tuần gần nhất bán vượt z-score bền ≥ 3 so với 7 tuần trước (cần ≥ 4 tuần có đơn).
- F34 `per_product`: `[{product_id, title, suggestions[{tag_id, score, used_by, better_sellers, popular_in_type}]}]`.
  Gợi ý lai: 0,7 theo sản phẩm giống (độ giống × độ bán chạy) + 0,3 theo độ phổ biến cùng loại.
- F33 `strategic_groups`: `{k, silhouette, clear (≥ 0,25), features[], axes{x, y}, groups[{id, label, size,
  avg_price_vnd, avg_revenue_90d_vnd}], points[{shop_id, shop_name, x, y, group, me}], my_group, best_group (null
  khi sàn chưa có đơn), gaps[{feature, name, mine, theirs}], method}` hoặc `null` kèm `strategic_groups_reason`
  (cần ≥ 6 shop có giá). KMeans trên 5 thông số chuẩn hoá z (giá, điểm sao, thời gian trả lời, số sản phẩm, doanh thu;
  giá/số sản phẩm/doanh thu lấy log), k = 2–5 theo silhouette; PCA 2 chiều, trục tăng theo thông số chính.
  `gaps` chỉ nêu điểm đáng học theo nhóm bán tốt (đánh giá cao hơn, trả lời nhanh hơn, nhiều mẫu hơn; giá để tham khảo).

---

## 5. Ba việc FE làm được NGAY, không cần chờ BE

1. **Dựng trạng thái rỗng cho cả 16 màn hình.** Mọi endpoint đều có thể trả
   `insufficient_data` — và lúc mới deploy thì **phần lớn sẽ trả như vậy**.
   Đây là màn hình sẽ xuất hiện nhiều nhất trong buổi demo đầu.
2. **Dựng khối "Nguồn / Cách tính / Giới hạn"** đọc từ `meta` — dùng chung cho cả 16.
3. **Mock theo đúng JSON ở trên.** Hình dạng đã chốt; chỉ số liệu là chờ.

---

## 6. Sáu chỗ đã chốt — 21/09/2026

Mục này trước đây tên là *"Chỗ chưa chốt — Đạt quyết"*. Đã quyết, ghi lại kèm lý do
để không ai chốt ngược. Chỗ nào chốt khác với tài liệu cũ thì nói rõ tài liệu nào.

| # | Câu hỏi | Chốt | Vì sao |
|---|---|---|---|
| 1 | `est_sales_90d` tính thế nào? | `SUM(order_items.quantity)` nối `orders` trong 90 ngày, tính trên đơn **đã giao thành công** | Đúng đề xuất có sẵn. Đây là cột **bắt buộc** của `mart_competitor`, `BR-188` xếp hạng bằng nó. Mở khoá F32–F36 |
| 2 | Bọc `{data, meta}` hay trải phẳng? | **Bọc** `{"data":…, "meta":…, "error":null}` | FE đọc một chỗ cho cả 16 màn hình. Cài trong `app/api/v1/_template.py` — import là đúng, không phải nhớ |
| 2b | `meta` có đủ 8 trường con ở mọi endpoint? | **Có**, nhưng `status` chỉ còn **một** chỗ | `_template.build_meta()` tự sinh nên chi phí bằng 0. Xem bảng quy đổi bên dưới |
| 3 | F30 đi đường nào? | `GET /api/notifications/alerts` — **theo SRS** | FE sàn đã trỏ theo SRS. Nhất quán thua tương thích |
| 4 | WebSocket cho F30? | **Không làm trong phạm vi này.** Giữ polling | Chưa ai nhận, và không có trong 50 task. Ghi vào mục Hạn chế (QA-06) chứ không im lặng bỏ |
| 5 | `mart_listing_quality` / `mart_competitor` có `date` trong khoá? | **Không.** Giữ `["listing_id"]` | 5.000 listing × 365 ngày = 1,8 triệu dòng trên cụm M0 512 MB **dùng chung cả nhóm**. Lịch sử điểm đã nằm ở `listing_health` (khoá có `date`); hai bảng này là **ảnh chụp hiện tại** của phần đầu vào. Lý do đầy đủ ghi ngay trong `writer.MART_SCHEMA` |

### `status` chỉ nằm một chỗ: `meta.status`

Trước 21/09 ba tài liệu ghi ba kiểu cho cùng một khái niệm — mục 1 của chính file này
để `quality.status` (`ready`/`limited`/`insufficient_data`), mục *"THIẾU ≠ 0"* để
`status` ở gốc, task SPEC-02 để `meta.status`. Ba từ vựng thì FE phải viết ba nhánh.

**Còn hiệu lực: `meta.status` ∈ `ok` · `partial` · `insufficient_data`.**

| Bản cũ | Bản dùng |
|---|---|
| `quality.status: ready` | `meta.status: ok` |
| `quality.status: limited` | `meta.status: partial` |
| `status` ở gốc phản hồi | `meta.status` |

`quality` vẫn còn, giữ `sample_size` · `identity_linked` · `confidence`.

---

## 7. Hai chỗ hợp đồng tự mâu thuẫn — đã xử lý

**1. `mart_listing_daily` không tồn tại và sẽ không tồn tại.**
Mục 3 ở trên từng ghi F26 · F27 · F31 đọc bảng này. Nhưng `app/core/writer.py`
`BLOCKED` **chặn** nó: bảng đó là bản sao 1:1 của `listing_daily` (796.025 dòng, nguồn
đã ở đúng độ mịn nên gộp không giảm được dòng nào). Thử ngày 21/09 làm cụm Atlas M0
vọt lên **526/512 MB và chặn ghi với tất cả mọi người**.

→ **F26 · F27 · F31 đọc thẳng `listing_daily`.** Bốn cột khoá đã backfill, index đã có.
Bảng 16 endpoint ở mục 3 đã sửa theo. Một bảng bị chặn vì lý do **đo được** thì không
mở lại bằng một dòng trong tài liệu.

**2. Dải tin cậy tên là `lo95` / `hi95`, không phải `yhat_lower` / `yhat_upper`.**
`BR-206` và mục 4 (F37) dùng `lo95`/`hi95`. `writer.save_forecast_points()` bản cũ ghi
`yhat_lower`/`yhat_upper` — hai tên cho một thứ, API đọc `lo95` sẽ không thấy gì.
Bản ghi duy nhất đang có trong `forecast_point` mắc đúng lỗi này.

→ Tên chính thức là **`lo95` / `hi95`**. `save_forecast_points()` vẫn nhận tên cũ và tự
đổi kèm cảnh báo, để code đã viết không gãy. `scripts/validate_mart.py` bắt được chỗ này.

---

## 8. Chữ ký xác nhận

Ký nghĩa là: đã đọc hợp đồng, hiểu bảng mình ghi vào và endpoint mình phải trả,
và không thấy chỗ nào mâu thuẫn với phần việc của mình.

| Người | Mảng | Ngày | Ký |
|---|---|---|---|
| Đạt | khung API · F34 · F36 · F37 · F41 | 21/09 | ✔ (người viết) |
| Hiếu | F26 · F27 · F30 · F31 | | |
| Nhi | F32 · F33 · F35 + SPEC-04 (JWT) | | |
| Hưng | F38 · F39 · F40 | | |
| Hạt | F28 · F29 | | |
