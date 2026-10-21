import logging
from datetime import datetime, timedelta, timezone

import pandas as pd

from app.config import SEED_KEYWORDS
from app.core.calendar_vn import upcoming_events

from . import fusion, live_data, store, trend_store
from .intel import analyze
from .output import AXES, jsonable, score_doc
from .trend_axis import informative, cached_season, week_of_year, momentum

GIO_VN = timezone(timedelta(hours=7))
CALENDAR_WEEKS = 12
EVENT_KEYWORDS = 5
MAX_SYNC = 20
STALE = timedelta(weeks=4)
TOPIC = {k: t for k, _, t in SEED_KEYWORDS}
EVENT_TOPICS = {"tet": {"tet"}, "valentine": {"valentine", "couple"}, "8/3": {"womens_day"}, "20/10": {"womens_day"},
                "20/11": {"teachers_day"}, "noel": {"christmas"}, "khai_giang": {"school"}, "1/6": {"family"},
                "trung_thu": {"family", "gift"}, "30/4": {"travel"}, "11/11": {"gift"}, "12/12": {"gift"},
                "black_friday": {"gift"}}
log = logging.getLogger(__name__)

__all__ = ["analyze", "shop_summary", "calendar", "today"]


def today():
    return datetime.now(GIO_VN).date()


def _item(inp, doc) -> dict:
    doc = doc or {}
    return {"product_id": inp.product_id, "title": inp.title, "thumbnail": (inp.image_urls or [None])[0],
            "score": doc.get("score"), "axes": {a: (doc.get("axes") or {}).get(a) for a in AXES},
            "trend_direction": doc.get("trend_direction"), "computed_at": doc.get("computed_at")}


def shop_summary(shop_id) -> dict:
    rows = live_data.shop_listings(shop_id)
    ids, version = [r.product_id for r in rows], fusion.load_bundle().meta["model_version"]
    latest = store.latest_scores(ids, version)
    for inp in [r for r in rows if r.product_id not in latest][:MAX_SYNC]:
        try:
            doc = score_doc(analyze(inp, today(), persist=True))
            latest[inp.product_id] = {**doc, "computed_at": datetime.now(timezone.utc)}
        except Exception:
            log.exception("listing intel failed for %s", inp.product_id)
    return jsonable({"items": [_item(r, latest.get(r.product_id)) for r in rows], "total": len(rows)})


def _momentum(s, at):
    return None if s.dropna().index.max() < pd.Timestamp(at) - STALE else momentum(s, at)


def _event_keywords(series: dict, event, at) -> list[dict]:
    days = [*pd.date_range(event["prep_start"], event["date"], freq="7D"), event["date"]]
    weeks, topics = sorted({week_of_year(d) for d in days}), EVENT_TOPICS.get(event["key"], set())
    kws = [k for k, s in series.items() if TOPIC.get(k) in topics and informative(s)]
    ranked = sorted(((k, cached_season(k, series[k])[weeks].max()) for k in kws), key=lambda x: -x[1])
    return [{"term": k, "momentum": _momentum(series[k], at)} for k, idx in ranked[:EVENT_KEYWORDS] if idx > 1]


def calendar(shop_id, category: str | None) -> dict:
    groups = {live_data.group_of(category)} if category else {r.group for r in live_data.shop_listings(shop_id)}
    groups.discard(None)
    at, series = today(), trend_store.weekly_series()
    events = [e for e in upcoming_events(at, CALENDAR_WEEKS) if not groups or groups & set(e["groups"])]
    return jsonable({"events": [{**e, "keywords": _event_keywords(series, e, at)} for e in events]})
