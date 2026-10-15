# Cấu trúc dữ liệu trên MongoDB Atlas

Database: `data-sale` (đặt trong `.env` qua `MONGODB_DB`)

Collection được tạo tự động lúc ghi document đầu tiên. Index cũng tự tạo — `ensure_indexes()` chạy mỗi lần collector ghi dữ liệu, gọi lại nhiều lần vô hại.

---

## Các collection

### `trend_keyword` — danh sách từ khoá

```js
{
  keyword:      "áo tết",
  product_type: "tshirt",      // tshirt | mug | poster | tote | generic
  topic:        "tet",         // nhóm để tính Gap Score
  is_anchor:    false,
  active:       true
}
```

Index: `keyword` (unique)

### `trend_interest` — chuỗi thời gian, bảng quan trọng nhất

Một document cho mỗi điểm dữ liệu.

```js
{
  keyword:      "áo tết",
  observed_on:  ISODate("2026-02-01T00:00:00Z"),
  granularity:  "weekly",      // weekly | daily
  geo:          "VN",
  raw:          88.0,          // Google trả về, chuẩn hoá TRONG batch
  scaled:       90.2,          // đã quy đổi, so sánh được giữa mọi từ khoá
  topic:        "tet",
  product_type: "tshirt",
  is_anchor:    false,
  batch_id:     "ab12cd34",
  collected_at: ISODate(...)
}
```

Index:
- `(keyword, observed_on, granularity, geo)` unique — làm cho upsert idempotent, chạy lại cron không sinh bản trùng
- `(keyword, granularity, observed_on)` — dạng truy vấn dùng nhiều nhất
- `topic`

**Dùng `scaled`, không dùng `raw`.** Google chuẩn hoá 0–100 riêng trong từng request, nên hai từ khoá lấy ở hai request khác nhau nằm trên hai thang khác nhau. `scaled` đã quy đổi về chung một mốc qua từ khoá anchor.

**Riêng anchor có `raw: null` và `batch_id: "anchor-mean"`.** Anchor xuất hiện trong mọi batch nên có N bản sao nhiễu. Thay vì lưu bản của batch đầu tiên (nhân theo hệ số của riêng batch đó — tự mâu thuẫn), collector lấy trung bình các bản đã quy đổi. Đó chính là mức tham chiếu, và mọi keyword khác giờ đều tương đối so với nó. Khi truy vấn `raw`, lọc `is_anchor: false`.

### `trend_related` — truy vấn liên quan

```js
{
  seed_keyword: "áo thun anime",
  query:        "áo thun jujutsu kaisen",
  kind:         "rising",      // top | rising
  value:        250.0,         // rising: % tăng. top: điểm 0-100
  observed_on:  ISODate(...),
  geo:          "VN"
}
```

### `printify_variant` — giá vốn

```js
{
  blueprint_id: 6,
  blueprint_title: "Unisex Heavy Cotton Tee",
  print_provider_id: 29,
  variant_id: 18100,
  variant_title: "Black / S",
  color: "Black",
  size: "S",
  cost_cents: 1992,            // 19.92 USD trả cho nhà in
  product_type: "tshirt"
}
```

### `collector_run` — nhật ký chạy

```js
{
  job: "trends_daily",
  started_at: ISODate(...),
  finished_at: ISODate(...),
  status: "ok",                // ok | partial | failed | running
  rows_written: 4860,
  note: "0 batches failed"
}
```

Đây là bằng chứng pipeline chạy liên tục thật. Lúc bảo vệ, truy vấn ra hơn trăm dòng đều đặn từ tháng 8 thuyết phục hơn nhiều so với ảnh chụp màn hình một lần chạy tay.

---

## Nạp dữ liệu vào model

Đây là phần bạn cần ngay cho bước tiếp theo.

### Lấy chuỗi một từ khoá thành DataFrame

```python
import pandas as pd
from store_mongo import get_db

db = get_db()

def series(keyword, granularity="weekly", column="scaled"):
    """Trả về pandas Series đã sắp theo ngày, sẵn sàng cho STL/ARIMA."""
    cur = db.trend_interest.find(
        {"keyword": keyword, "granularity": granularity, "geo": "VN"},
        {"observed_on": 1, column: 1, "_id": 0},
    ).sort("observed_on", 1)

    df = pd.DataFrame(list(cur))
    if df.empty:
        raise ValueError(f"Chưa có dữ liệu cho '{keyword}' ({granularity})")
    df = df.set_index("observed_on")[column]
    df.index = pd.DatetimeIndex(df.index)
    return df.asfreq("W" if granularity == "weekly" else "D")
```

`asfreq` quan trọng: statsmodels cần index có tần suất rõ ràng, thiếu nó STL sẽ báo lỗi hoặc suy ra sai.

### STL — feature 38, mùa vụ

```python
from statsmodels.tsa.seasonal import STL

s = series("áo tết", "weekly").interpolate()
result = STL(s, period=52, robust=True).fit()   # 52 tuần = 1 năm

result.seasonal    # thành phần mùa vụ
result.trend       # xu hướng dài hạn
result.resid       # phần dư -> bất thường nằm ở đây
```

Đỉnh của `result.seasonal` cho bạn **tuần nào trong năm nhu cầu lên cao nhất**. Trừ đi lead time là ra ngày nên đăng sản phẩm — chính là content calendar trong bản đăng ký.

### ARIMA — feature 37, dự báo

```python
from pmdarima import auto_arima

s = series("áo thun anime", "daily").interpolate()
model = auto_arima(s, seasonal=False, information_criterion="aic",
                   suppress_warnings=True)
pred, ci = model.predict(n_periods=30, return_conf_int=True, alpha=0.05)
```

`ci` là khoảng tin cậy 95% mà bản đăng ký yêu cầu hiển thị.

### Gap Score — feature 39, tốc độ tăng theo topic

```python
from datetime import datetime, timedelta, timezone

now = datetime.now(timezone.utc)
pipeline = [
    {"$match": {"granularity": "daily", "geo": "VN",
                "observed_on": {"$gte": now - timedelta(days=60)},
                "is_anchor": False}},
    {"$project": {
        "topic": 1, "scaled": 1,
        "recent": {"$gte": ["$observed_on", now - timedelta(days=30)]},
    }},
    {"$group": {
        "_id": {"topic": "$topic", "recent": "$recent"},
        "avg": {"$avg": "$scaled"},
    }},
]
for row in db.trend_interest.aggregate(pipeline):
    print(row)
```

Chia trung bình 30 ngày gần nhất cho 30 ngày trước đó ra tốc độ tăng — vế "search volume growth rate" trong công thức Gap Score.

### Emerging Niche Radar — feature 40

```python
top = db.trend_related.find(
    {"kind": "rising", "geo": "VN"}
).sort("value", -1).limit(20)
```

### Sàn giá theo loại sản phẩm — feature 35

```python
floor = db.printify_variant.aggregate([
    {"$match": {"cost_cents": {"$ne": None}}},
    {"$group": {"_id": "$product_type",
                "min_cost": {"$min": "$cost_cents"},
                "avg_cost": {"$avg": "$cost_cents"}}},
])
```

Mọi giá gợi ý phải nằm trên `min_cost`, không thì seller lỗ mỗi đơn.

### Kiểm tra pipeline

```python
for run in db.collector_run.find().sort("started_at", -1).limit(10):
    print(run["started_at"], run["job"], run.get("status"))
```

Hoặc ngắn hơn:

```bash
python collect_trends.py --mongo-health
```

---

## Về PostgreSQL

Bản đăng ký của bạn ghi PostgreSQL cho users, orders, products, transactions — tầng thương mại điện tử, dựng sau, schema hoàn toàn khác.

Tầng thu thập này nằm trọn trên MongoDB. Không có code Postgres nào trong repo.
