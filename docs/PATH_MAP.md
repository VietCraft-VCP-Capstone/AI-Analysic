# Bảng dịch đường dẫn: task Jira ↔ repo thật

> **Đọc file này TRƯỚC khi bắt đầu bất kỳ task nào.**
>
> Task trong Jira mô tả một cấu trúc thư mục **chưa bao giờ được dựng**.
> Repo đi theo cấu trúc khác. Nếu bạn tìm `domain/` mà không thấy thì **không phải
> bạn sai** — bản đồ sai.

---

## 1. Chuyện gì đã xảy ra

Task đầu tiên của Sprint 2 (`Dung khung thu muc domain/ io/ jobs/ tests/`) dự định
dựng cấu trúc này:

```
app/domain/    logic thuần, chỉ được import numpy/pandas/scipy/statsmodels
app/io/        đọc ghi Mongo
app/jobs/      script chạy theo lịch
app/schemas/   kiểu dữ liệu
tests/         kiểm thử
scripts/       tiện ích
```

Thực tế repo đã có sẵn cấu trúc khác từ các sprint trước, và **code được viết vào
cấu trúc cũ** thay vì dựng cấu trúc mới:

```
app/core/       ← tương đương domain/ + io/
app/services/   ← tương đương domain/
app/models/     ← tương đương domain/
app/api/v1/     ← tầng HTTP
app/collectors/ ← thu thập dữ liệu ngoài
app/seed/       ← sinh dữ liệu mồi
```

Hai bên chưa bao giờ được đối chiếu. Hệ quả: **43/44 đường dẫn nhắc trong task
không tồn tại**, và người đọc task tưởng chưa ai làm gì.

---

## 2. Bảng dịch — 12 thứ ĐÃ CÓ

Task bảo "viết X" nhưng X **đã tồn tại dưới tên khác và đã chạy được**.
Đừng viết lại. Mở file thật ra đọc.

| Task Jira bảo viết | File thật trong repo | Dòng | Ghi chú |
|---|---|---|---|
| `domain/calendar_vn.py` | `app/core/calendar_vn.py` | 125 | có `days_to_tet`, bảng Tết tới 2030 |
| `domain/metrics.py` | `app/core/metrics.py` | 199 | MASE, RMSSE |
| `domain/backtest.py` | `app/core/backtest.py` | 197 | `rolling_origin` |
| `domain/seasonality.py` | `app/services/stl_service.py` | 84 | phân rã STL |
| `domain/forecast.py` | `app/models/seasonal_forecast.py` | 291 | bóc hiệu ứng Tết theo trục âm lịch |
| `domain/anomaly.py` | `app/services/zscore_service.py` | 423 | phần dư STL + MAD, ngưỡng 7,0 |
| `domain/health.py` | `app/api/v1/health_score.py` | 162 | đã sửa trọng số 20/09 |
| `domain/gap.py` | `app/core/build_mvp_export.py` | 757 | gồm cả ma trận cung–cầu |
| `domain/baseline.py` | `app/core/compute_baselines.py` | 163 | sinh `baselines.json` |
| `io/writers.py` | `app/core/writer.py` | 160 | `save_model_output()`, đã sửa 20/09 |
| `io/readers.py` | `app/core/loader.py` | 246 | đọc CSV, fallback Mongo |
| `scripts/exit_gate_s3.py` | `plan/exit_gate_s3.py` | 386 | **nằm ngoài repo**, ở thư mục `plan/` |

> Chạy `cd AI-Analysic && .venv/bin/python <đường dẫn thật>` — phần lớn file có
> self-check trong `if __name__ == "__main__"` và sẽ in ra kết quả kiểm tra.

---

## 3. Bảng dịch — 8 thứ THẬT SỰ CHƯA CÓ

| Task Jira bảo viết | Trạng thái | Nên đặt ở đâu |
|---|---|---|
| `jobs/run_seasonal.py` | ❌ chưa có | `app/jobs/run_seasonal.py` |
| `jobs/run_anomaly.py` | ❌ chưa có | `app/jobs/run_anomaly.py` |
| `jobs/run_health.py` | ❌ chưa có | `app/jobs/run_health.py` |
| `jobs/run_gap.py` | ❌ chưa có | `app/jobs/run_gap.py` |
| `tests/test_calendar_vn.py` | ❌ chưa có | `tests/test_calendar_vn.py` |
| `tests/test_backtest.py` | ❌ chưa có | `tests/test_backtest.py` |
| `tests/test_anomaly.py` | ❌ chưa có | `tests/test_anomaly.py` |
| `tests/test_baseline.py` | ❌ chưa có | `tests/test_baseline.py` |

**Về `jobs/`:** đây là tầng còn thiếu quan trọng nhất. Cổng ra Sprint 3 định nghĩa
"xong" là *job tính ra → ghi vào mart → API đọc ra được*. Hiện chưa có job nào.

**Về `tests/`:** repo hiện **không có pytest**. Các file hiện chỉ có self-check
trong `__main__`, không chạy được trong CI và không đo được coverage. Đây là lý do
điều kiện "độ phủ kiểm thử ≥ 80%" của cổng ra đang FAIL.

---

## 4. Tài liệu — 17 file được nhắc, chưa file nào tồn tại

`docs/SPEC_CHANGES.md` · `docs/RUNBOOK.md` · `docs/FINDING_TET.md` ·
`docs/SEED_ACCEPTANCE.md` · `docs/HEALTH_SPEC.md` · `docs/CODING_RULES.md` ·
`docs/EVAL_BASELINE.md` · `docs/MART_SCHEMA.md` · `docs/DATA_LICENSES.md` ·
`docs/WHY_RESIDUAL.md` · `docs/GAP_SPEC.md` · `docs/EXPERT_PANEL.md` ·
`docs/TEST_GAPS.md` · `docs/AUTH_CONTRACT.md` · `docs/DATA_CONTRACT.md` ·
`docs/API_CONTRACT.md` · `docs/F41_SPEC.md` · `docs/UAT_PROTOCOL.md` ·
`docs/UAT_PARTICIPANTS.md` · `docs/REPRODUCIBILITY.md` · `docs/PERF.md`

Thứ **đã có** trong `docs/`:

| File | Nội dung |
|---|---|
| `RESULTS.json` | kết quả backtest, `features` F26–F41, `metrics` |
| `HYBRID_AI_MVP_DATA_CONTRACT.md` | gần với `DATA_CONTRACT.md` |
| `LIVE_ANALYTICS_IDENTITY_CONTRACT.md` | quy ước định danh live vs seed |
| `SEED_PARAMS.md` | gần với `SEED_ACCEPTANCE.md` |
| `PATH_MAP.md` | chính file này |
| `qc/` | báo cáo QC dữ liệu mồi |

---

## 5. Quy tắc từ giờ

1. **Trước khi viết file mới, tra bảng mục 2.** Nhiều thứ đã có rồi.
2. **Đặt file mới theo cấu trúc THẬT** (`app/core/`, `app/services/`, `app/models/`),
   đừng dựng `domain/` song song — sẽ thành hai nơi cùng một việc.
3. **Nếu task nhắc một đường dẫn không tìm thấy**, tra bảng này trước khi hỏi.
   Không có trong bảng thì nó thật sự chưa tồn tại.
4. Quy tắc import mà task đầu Sprint 2 đặt ra vẫn **đáng giữ**, chỉ đổi tên thư mục:
   > File trong `app/core/`, `app/services/`, `app/models/` chỉ được import
   > `numpy`, `pandas`, `scipy`, `statsmodels`.
   > **Cấm** import `pymongo`, cấm import `fastapi`, cấm đọc file, cấm gọi API.
   >
   > Đây là điều kiện để đạt coverage 80% mà không phải viết lại vào tháng 12.

   Hiện `app/core/loader.py` và `writer.py` **có** đụng `pymongo` — đó là tầng I/O,
   đúng vai `io/` trong kế hoạch gốc. Giữ nguyên, nhưng đừng để logic tính toán
   lọt vào hai file đó.

---

*Cập nhật 20/09/2026. Khi cấu trúc repo đổi, sửa file này trước.*
