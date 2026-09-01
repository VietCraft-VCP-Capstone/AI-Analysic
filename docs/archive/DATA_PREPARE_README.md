# VietCraft — tầng thu thập dữ liệu

Thu thập tín hiệu thị trường thật cho module AI Product Analytics. Không cào gì, chỉ dùng API chính thức.

## Cài đặt

```bash
pip install trendspy pandas pymongo dnspython requests python-dotenv
cp .env.example .env      # mở ra điền MONGODB_URI
python preflight.py       # <-- CHẠY CÁI NÀY TRƯỚC, không tốn quota
```

`preflight.py` kiểm tra: package đã cài đủ chưa, `.env` hợp lệ không, Atlas kết nối **và ghi được** không (bắt được lỗi thiếu quyền `readWrite` trên đúng database), `config.py` có mâu thuẫn gì không, anchor trong DB có khớp config không, rồi in ngân sách HTTP.

Mọi lỗi ở đây đều là lỗi mà nếu không kiểm tra trước, bạn chỉ phát hiện khi backfill đã chạy nửa chừng — lúc request đã mất rồi.

## Ngân sách request — đọc trước khi chạy

Đã kiểm chứng bằng cách đếm `session.get`: **một lần gọi = 2 HTTP request**. Google Trends dùng "token dance" — request đầu lấy token từ `/embed/explore/TIMESERIES`, request sau mới lấy dữ liệu từ `/api/widgetdata/multiline`.

| Lệnh | Số call | HTTP thật | Thời gian |
|---|---|---|---|
| `--backfill weekly` | 11 | **22** | ~4 phút |
| `--backfill daily` | 11 | **22** | ~4 phút |
| `--daily` (cron) | 11 | **22** | ~4 phút |
| `--related` | 44 | **88** | ~15 phút |

Mỗi collector in ra số HTTP đã dùng khi chạy xong. Dùng con số đó, đừng ước lượng.

Bị 429 thì **chờ 30–60 phút**, đừng chạy lại ngay — chạy lại ngay chỉ làm block kéo dài. Batch đã lấy được lưu trong `.checkpoints/`, chạy lại đúng lệnh cũ sẽ bỏ qua phần đã có.

## Chạy local, theo thứ tự

```bash
# 0. Kiểm tra môi trường  (0 HTTP)
python preflight.py

# 1. Weekly 5 năm  (22 HTTP)  -> nuôi STL / mùa vụ
python collect_trends.py --backfill weekly --mongo --out ./data

# 2. DỪNG, kiểm tra  (0 HTTP)
python verify_data.py --integrity --quality

# 3. Daily 90 ngày  (22 HTTP)  -> nuôi ARIMA
python collect_trends.py --backfill daily --mongo --out ./data

# 4. Đánh dấu keyword nào đủ điều kiện chạy mô hình  (0 HTTP)
python verify_data.py --eligibility --write-eligibility

# 5. Rising queries  (88 HTTP)  -> nuôi Emerging Niche Radar
python collect_trends.py --related --mongo --out ./data

# 6. Cổng quyết định: có đáng làm discovery không?  (0 HTTP)
python verify_data.py --discovery-stats

# 7. Giá vốn  (Printify, không đụng quota Google)
python collect_printify.py --mongo --out ./data
```

Bước 2 và 6 là hai chỗ phải dừng lại đọc kết quả trước khi đi tiếp.

Ở bước 2, nếu bảng tóm tắt báo `Anchor looks too popular`: sửa `config.ANCHOR` sang từ khoá trầm hơn, xoá `.checkpoints/`, chạy lại bước 1. Phát hiện sớm đỡ tốn hơn nhiều so với phát hiện sau khi đã chạy hết bước 5.

## Kiểm tra, không tốn quota

```bash
python verify_data.py --all
python collect_trends.py --mongo-health
```

| Lệnh | Trả lời câu hỏi |
|---|---|
| `--integrity` | Phép quy đổi `raw → scaled` có đúng không? |
| `--quality` | Thiếu ngày, trùng lặp, bao nhiêu chuỗi toàn số 0? |
| `--eligibility` | Keyword nào đủ tín hiệu để chạy ARIMA/STL? |
| `--discovery-stats` | Có đủ rising query để xây discovery không? |

## Sửa config rồi thì làm gì

Danh sách keyword mà collector dùng nằm trong **Atlas**, không phải `config.py`. Nhưng nó tự đồng bộ với `config.py` trước mỗi lần thu thập, nên sửa xong chỉ cần chạy lại là khớp.

Muốn dọn dữ liệu của keyword đã bỏ:

```bash
python collect_trends.py --sync --purge --mongo
```

`--sync` tắt keyword không còn trong config và gỡ `is_anchor` khỏi anchor cũ. `--purge` xoá các điểm dữ liệu của keyword đã tắt. Tách riêng vì xoá dữ liệu nên là hành động có chủ đích.

## Hai điều bắt buộc nhớ khi dựng mô hình

**Chỉ dùng `scaled`, không dùng `raw`.** Google chuẩn hoá 0–100 riêng trong từng request, nên hai keyword lấy ở hai request khác nhau nằm trên hai thang khác nhau. `scaled` đã quy đổi về chung một mốc qua anchor. Gap Score so sánh tốc độ tăng *giữa* các keyword — dùng `raw` thì sai hoàn toàn mà biểu đồ vẫn vẽ ra đẹp.

**Đừng đánh giá forecasting trên keyword discover được.** Chúng được chọn *vì* đang tăng, nên backtest trên chúng là chọn mẫu theo kết quả. Chỉ báo cáo MAE/MASE trên seed set — tập được chọn trước khi quan sát kết quả.

## Cron

`.github/workflows/collect.yml` — chạy 05:00 và 17:00 giờ VN, cộng discovery sáng chủ nhật.

Hai mốc **không phải để lấy thêm dữ liệu** (Trends chỉ có 1 điểm/ngày ở timeframe này) mà để lần sau vá cho lần trước nếu gặp 429 hoặc bị GitHub hoãn.

Cần làm trên GitHub:

1. Settings → Secrets and variables → Actions → thêm secret `MONGODB_URI`
2. Atlas → Network Access → thêm `0.0.0.0/0` (máy ảo GitHub có IP ngẫu nhiên, whitelist IP nhà bạn là cron timeout)
3. Tab Actions → Run workflow → chạy tay để kiểm tra, đừng đợi 5 giờ sáng

`MONGODB_DB` đã đặt sẵn `data-collection` trong file workflow. Đổi tên database thì sửa ở đó.

**Không commit `.env`.** `.gitignore` đã chặn. Kiểm tra trước khi push:

```bash
git ls-files | grep -c "^\.env$"   # phải ra 0
```

## File

| File | Việc |
|---|---|
| `preflight.py` | Kiểm tra môi trường trước khi chạy |
| `config.py` | Từ khoá, anchor, ngân sách, từ vựng lọc |
| `collect_trends.py` | Thu thập Google Trends |
| `collect_printify.py` | Giá vốn |
| `store_mongo.py` | Tầng ghi Atlas |
| `verify_data.py` | Kiểm tra dữ liệu, không tốn quota |
| `MONGO_SCHEMA.md` | Cấu trúc collection + code nạp vào STL/ARIMA |
| `FEATURE_COVERAGE.md` | Đối chiếu với 47 feature trong report |
