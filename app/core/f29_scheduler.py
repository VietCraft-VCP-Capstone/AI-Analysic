"""
f29_scheduler.py — Job quét F29 (§5, BR-181): chấm lại điểm sức khoẻ khi dữ liệu đổi.

Hai job, DÙNG CHUNG MỘT ENGINE (`HealthScoreCalculator`) với API `/health` và
`/listings/health/preview` — batch, chấm lại khi sửa và preview không được phép
lệch công thức nhau (§5):

  - `scan_changed_products()` — quét mỗi 60 giây: `products` / `product_variants`
    có `updated_at` > mốc quét trước. BR-181 cam kết ĐỘ TRỄ "≤ 1 phút" giữa lúc
    seller sửa và lúc điểm cập nhật — không phải lịch chạy đúng từng giây.
  - `nightly_full_rescan()` — quét lúc 0h UTC mỗi 24h, chấm TOÀN BỘ listing hợp
    lệ kể cả sản phẩm `updated_at` không đổi. Bù cho các đường ghi không chạm
    `products.updated_at` (ví dụ duyệt tag nằm ở collection `tags`, không phải
    `products`).

Mốc "lần quét trước" lưu ở `vietcraft.scheduler_state` (một bản ghi mỗi job,
khoá bằng `_id`) — KHÔNG lưu file cục bộ trên máy chạy service: máy demo khởi
động lại bất cứ lúc nào, và nếu sau này chạy nhiều hơn một tiến trình AI thì
mọi tiến trình phải thấy cùng một mốc.

Idempotency: mỗi lần chấm xong đều `save()` qua `HealthScoreCalculator`, upsert
theo khoá `{product_id, date}` — chạy `scan_changed_products()` hay
`nightly_full_rescan()` hai lần liên tiếp cho cùng dữ liệu chỉ ghi đè cùng một
bản ghi, không insert trùng (xem `tests/f29/test_persistence.py`).
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, List, Optional

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.api.v1._live import db_live, LOC_SP_THAT
from app.core.f29.calculator import HealthScoreCalculator

# ---------------------------------------------------------------------------
# TRẠNG THÁI LẦN QUÉT GẦN NHẤT
# ---------------------------------------------------------------------------

STATE_COLLECTION = "scheduler_state"
STATE_ID_MINUTE_SCAN = "f29_minute_scan"
STATE_ID_NIGHTLY = "f29_nightly_rescan"

# Chưa từng quét lần nào thì quét lùi ngần này phút cho job phút, để lần chạy
# đầu tiên của service vẫn bắt được các sản phẩm vừa sửa gần đây — không phải
# quét lại TOÀN SÀN ngay (đó là việc của nightly_full_rescan).
DEFAULT_LOOKBACK_MINUTES = 24 * 60


def _get_last_scan_time(job_id: str, default_lookback_minutes: int = DEFAULT_LOOKBACK_MINUTES) -> datetime:
    """Mốc lần quét trước của một job, hoặc mốc lùi mặc định nếu chưa từng chạy."""
    db = db_live()
    doc = db[STATE_COLLECTION].find_one({"_id": job_id})
    if doc and doc.get("last_scan_time"):
        ts = doc["last_scan_time"]
        if isinstance(ts, datetime) and ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts
    return datetime.now(timezone.utc) - timedelta(minutes=default_lookback_minutes)


def _set_last_scan_time(job_id: str, ts: datetime) -> None:
    db = db_live()
    db[STATE_COLLECTION].update_one(
        {"_id": job_id},
        {"$set": {"last_scan_time": ts, "updated_at": datetime.now(timezone.utc)}},
        upsert=True,
    )


def _recalculate_and_save(
    product_ids: Iterable, calculator: Optional[HealthScoreCalculator] = None
) -> int:
    """Chấm lại và lưu cho từng product_id. Một sản phẩm lỗi không được chặn cả
    lượt quét — log rồi đi tiếp. Trả số sản phẩm đã chấm VÀ lưu thành công.
    """
    calc = calculator or HealthScoreCalculator()
    n_ok = 0
    for pid in product_ids:
        try:
            result = calc.calculate(str(pid))
            if result is not None:
                calc.save(result)
                n_ok += 1
        except Exception as e:  # noqa: BLE001
            print(f"[f29_scheduler] Loi cham diem product_id={pid}: "
                  f"{type(e).__name__}: {e}", flush=True)
    return n_ok


# ---------------------------------------------------------------------------
# HAI JOB
# ---------------------------------------------------------------------------

def scan_changed_products() -> int:
    """BR-181: quét `products` / `product_variants` có `updated_at` mới hơn lần
    quét trước, chấm lại điểm và lưu. Trả số sản phẩm đã chấm.
    """
    db = db_live()
    scan_started_at = datetime.now(timezone.utc)
    last_scan_time = _get_last_scan_time(STATE_ID_MINUTE_SCAN)

    changed_ids = {
        p["_id"] for p in db["products"].find(
            {**LOC_SP_THAT, "updated_at": {"$gt": last_scan_time}}, {"_id": 1}
        )
    }

    changed_variant_product_ids = list({
        v["product_id"] for v in db["product_variants"].find(
            {"updated_at": {"$gt": last_scan_time}}, {"product_id": 1}
        )
    })
    # Lượt xem và đơn mới không chạm `products.updated_at`, nhưng làm đổi trục tỉ lệ
    # mua và tiến độ "đã có X/100 lượt xem" mà seller đang nhìn.
    activity_product_ids = {
        e["product_id"] for e in db["product_events"].find(
            {"event_type": "view", "created_at": {"$gt": last_scan_time}}, {"product_id": 1}
        )
    }
    for o in db["orders"].find({"created_at": {"$gt": last_scan_time}}, {"items.product_id": 1}):
        activity_product_ids |= {i.get("product_id") for i in (o.get("items") or []) if i.get("product_id")}

    related_ids = list(set(changed_variant_product_ids) | activity_product_ids)
    if related_ids:
        changed_ids |= {
            p["_id"] for p in db["products"].find(
                {**LOC_SP_THAT, "_id": {"$in": related_ids}}, {"_id": 1}
            )
        }

    n_ok = _recalculate_and_save(changed_ids) if changed_ids else 0

    # Lưu mốc lúc BẮT ĐẦU quét, không phải lúc xong: việc chấm điểm có thể mất
    # vài giây, và một thay đổi xảy ra đúng lúc đó vẫn phải nằm SAU mốc để lần
    # quét kế tiếp bắt được — tránh lọt mất thay đổi giữa hai lần quét.
    _set_last_scan_time(STATE_ID_MINUTE_SCAN, scan_started_at)
    return n_ok


def nightly_full_rescan() -> int:
    """Quét TOÀN BỘ sản phẩm hợp lệ mỗi 24h (0h UTC), kể cả sản phẩm có
    `updated_at` không đổi — bù cho các đường ghi không cập nhật
    `products.updated_at` (duyệt tag, đổi category, …).
    """
    db = db_live()
    scan_started_at = datetime.now(timezone.utc)

    all_ids = [p["_id"] for p in db["products"].find(LOC_SP_THAT, {"_id": 1})]
    n_ok = _recalculate_and_save(all_ids) if all_ids else 0

    _set_last_scan_time(STATE_ID_NIGHTLY, scan_started_at)
    # Job đêm vừa quét toàn sàn, nên job phút không cần chấm lại ngay những sản
    # phẩm không đổi gì thêm — đẩy luôn mốc quét-theo-phút lên để khỏi trùng.
    _set_last_scan_time(STATE_ID_MINUTE_SCAN, scan_started_at)
    return n_ok


# ---------------------------------------------------------------------------
# ĐĂNG KÝ VÀO APSCHEDULER (gọi từ `app/main.py::lifespan`)
# ---------------------------------------------------------------------------

_scheduler = None


def start_scheduler():
    """Đăng ký 2 job: quét thay đổi mỗi 60 giây, quét toàn sàn 0h UTC mỗi ngày.

    Gọi MỘT LẦN trong `lifespan` của `app/main.py`. An toàn gọi nhiều lần (trả
    lại scheduler đã có, không đăng ký trùng job) — phòng khi lifespan chạy lại
    trong test với TestClient.
    """
    global _scheduler
    if _scheduler is not None:
        return _scheduler

    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger

    scheduler = BackgroundScheduler(timezone=timezone.utc)
    scheduler.add_job(
        scan_changed_products,
        "interval",
        seconds=60,
        id="f29_scan_changed",
        max_instances=1,
        coalesce=True,
        next_run_time=datetime.now(timezone.utc),  # chạy ngay lần đầu, không đợi 60s
    )
    scheduler.add_job(
        nightly_full_rescan,
        CronTrigger(hour=0, minute=0, timezone=timezone.utc),
        id="f29_nightly_rescan",
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    _scheduler = scheduler
    return scheduler


def stop_scheduler() -> None:
    """Tắt scheduler lúc service dừng (lifespan shutdown)."""
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None


if __name__ == "__main__":
    print("Quét thay đổi (F29 BR-181)...", flush=True)
    n = scan_changed_products()
    print(f"Đã chấm lại {n} sản phẩm thay đổi.", flush=True)
