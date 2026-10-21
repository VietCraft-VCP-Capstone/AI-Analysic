import json
import logging
import os
import time
from pathlib import Path

import pandas as pd
from pymongo import MongoClient
from pymongo.errors import PyMongoError

from app.config import settings

MONGO_URI = os.environ.get("LI_TREND_MONGO_URI") or settings.MONGO_URI or "mongodb://127.0.0.1:27017"
MONGO_DB = os.environ.get("LI_TREND_DB", "data-collection")
PARQUET = Path(__file__).resolve().parents[4] / "vc-data" / "trends" / "trend_interest.parquet"
SNAPSHOT = Path(__file__).parent / "model" / "reference" / "trend_weekly.json"
TTL = 3600
COLS = ["keyword", "observed_on", "scaled"]
log = logging.getLogger(__name__)
_cache: dict = {"at": 0.0, "data": None}


def _from_mongo() -> pd.DataFrame:
    with MongoClient(MONGO_URI, serverSelectionTimeoutMS=2000) as client:
        rows = client[MONGO_DB]["trend_interest"].find({"granularity": "weekly"}, {"_id": 0, **dict.fromkeys(COLS, 1)})
        return pd.DataFrame(list(rows), columns=COLS)


def _from_parquet() -> pd.DataFrame:
    df = pd.read_parquet(PARQUET, columns=COLS + ["granularity"])
    return df[df["granularity"] == "weekly"][COLS]


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
    if _cache["data"] is None or time.monotonic() - _cache["at"] > TTL:
        _cache.update(data=_load(), at=time.monotonic())
    return _cache["data"]
