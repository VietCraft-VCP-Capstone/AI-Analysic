import json
import logging
import os
import threading
import time
from pathlib import Path

import pandas as pd
from pymongo import MongoClient
from pymongo.errors import PyMongoError

from app.config import settings

MONGO_URI = os.environ.get("LI_TREND_MONGO_URI") or settings.MONGO_URI or "mongodb://127.0.0.1:27017"
MONGO_DB = os.environ.get("LI_TREND_DB", "data-collection")
PARQUET = Path(__file__).resolve().parents[4] / "vc-data" / "trends" / "trend_interest.parquet"
SNAPSHOT = Path(__file__).parent / "data" / "trend_weekly.json"
TTL = 3600
COLS = ["keyword", "observed_on", "scaled"]
log = logging.getLogger(__name__)
_cache: dict = {"at": 0.0, "data": None}
_lock = threading.Lock()


MIN_DAYS_PER_WEEK = 4
ANCHOR_LEVEL_WEEKS = 8


def _anchor_keyword() -> str:
    try:
        from app.collectors import config as collector_cfg
        return collector_cfg.ANCHOR
    except Exception:  # noqa: BLE001
        return "quà sinh nhật"


def _week_start_sunday(ts: pd.Series) -> pd.Series:
    """Nhãn tuần giống Google Trends: ngày Chủ Nhật mở đầu tuần."""
    d = pd.to_datetime(ts).dt.normalize()
    return d - pd.to_timedelta((d.dt.dayofweek + 1) % 7, unit="D")


def extend_weekly_with_daily(weekly: pd.DataFrame, daily: pd.DataFrame, anchor: str) -> pd.DataFrame:
    """
    Nối các tuần mới từ bản theo ngày vào sau tuần cuối của bản theo tuần.

    Bản theo tuần (5 năm) chỉ được thu một lần khi nạp lịch sử, còn bản theo ngày (90 ngày) được
    cron thu 2 lần/ngày. Hai bản có thang điểm khác nhau nên quy đổi qua từ khóa neo (ổn định quanh năm):
    hệ số = mức neo của các tuần cuối bản theo tuần / mức neo của các tuần đầu phần nối thêm.
    Chỉ nhận tuần có đủ MIN_DAYS_PER_WEEK ngày; không có từ khóa neo thì không nối.
    """
    if daily is None or daily.empty or weekly is None or weekly.empty:
        return weekly
    w = weekly.copy()
    w["observed_on"] = pd.to_datetime(w["observed_on"])
    last_week = w["observed_on"].max()
    d = daily.dropna(subset=["scaled"]).copy()
    d["week"] = _week_start_sunday(d["observed_on"])
    d = d[d["week"] > last_week]
    if d.empty:
        return weekly
    agg = d.groupby(["keyword", "week"])["scaled"].agg(["mean", "count"]).reset_index()
    agg = agg[agg["count"] >= MIN_DAYS_PER_WEEK]
    anchor_new = agg[agg["keyword"] == anchor].sort_values("week")["mean"].head(ANCHOR_LEVEL_WEEKS)
    anchor_old = w[w["keyword"] == anchor].sort_values("observed_on")["scaled"].tail(ANCHOR_LEVEL_WEEKS)
    if anchor_new.empty or anchor_old.empty or float(anchor_new.mean()) <= 0:
        return weekly
    factor = float(anchor_old.mean()) / float(anchor_new.mean())
    ext = pd.DataFrame({
        "keyword": agg["keyword"],
        "observed_on": agg["week"],
        "scaled": (agg["mean"] * factor).round(2),
    })
    return pd.concat([w, ext], ignore_index=True)


def _from_mongo() -> pd.DataFrame:
    with MongoClient(MONGO_URI, serverSelectionTimeoutMS=2000) as client:
        col = client[MONGO_DB]["trend_interest"]
        proj = {"_id": 0, **dict.fromkeys(COLS, 1)}
        weekly = pd.DataFrame(list(col.find({"granularity": "weekly"}, proj)), columns=COLS)
        daily = pd.DataFrame(list(col.find({"granularity": "daily"}, proj)), columns=COLS)
    return extend_weekly_with_daily(weekly, daily, _anchor_keyword())


def _from_parquet() -> pd.DataFrame:
    df = pd.read_parquet(PARQUET, columns=COLS + ["granularity"])
    return extend_weekly_with_daily(df[df["granularity"] == "weekly"][COLS], df[df["granularity"] == "daily"][COLS], _anchor_keyword())


def _from_snapshot() -> pd.DataFrame:
    data = json.loads(SNAPSHOT.read_text("utf-8"))
    return pd.DataFrame([(k, d, v) for k, s in data.items() for d, v in s.items()], columns=COLS)


def _to_series(df: pd.DataFrame) -> dict:
    df = df.dropna(subset=["scaled"]).copy()
    df["observed_on"] = pd.to_datetime(df["observed_on"], utc=True).dt.tz_localize(None)
    return {
        kw: g.set_index("observed_on")["scaled"].astype(float).sort_index()
        for kw, g in df.groupby("keyword")
    }


def _load() -> dict:
    try:
        data = _to_series(_from_mongo())
    except PyMongoError as exc:
        log.warning("trend_interest mongo unavailable, using parquet or snapshot: %s", exc)
        data = {}
    if not data and PARQUET.exists():
        data = _to_series(_from_parquet())
    if not data and SNAPSHOT.exists():
        data = _to_series(_from_snapshot())
    if not data:
        log.warning("trend_interest: no weekly trend data found")
    return data


def weekly_series() -> dict:
    with _lock:
        if _cache["data"] is None or time.monotonic() - _cache["at"] > TTL:
            _cache.update(data=_load(), at=time.monotonic())
        return _cache["data"]
