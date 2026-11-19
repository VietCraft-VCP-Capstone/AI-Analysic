import logging
from datetime import date, timedelta

import pandas as pd

from app.core.calendar_vn import ALL_GROUPS, SHOPPING_EVENTS

# Lịch riêng của listing intel: chỉ đọc dữ liệu gốc (date_fn, prep_days) của calendar_vn,
# không phụ thuộc dạng kết quả upcoming_events() mà F38 có thể đổi.
_MISSING_LOGGED: set = set()


def _black_friday(year: int) -> date:
    first = date(year, 11, 1)
    return first + timedelta(days=(3 - first.weekday()) % 7 + 22)


EXTRA_EVENTS = [{"key": "black_friday", "name": "Black Friday", "prep_days": 21,
                 "groups": ALL_GROUPS, "date_fn": _black_friday}]


def all_events() -> list:
    keys = {e["key"] for e in SHOPPING_EVENTS}
    return list(SHOPPING_EVENTS) + [e for e in EXTRA_EVENTS if e["key"] not in keys]


def upcoming_events(d: date, weeks: int = 12) -> list:
    d = pd.Timestamp(d).date()
    end = d + timedelta(weeks=weeks)
    found = []
    for ev in all_events():
        for year in (d.year, d.year + 1):
            try:
                when = ev["date_fn"](year)
            except KeyError:
                if (ev["key"], year) not in _MISSING_LOGGED:
                    _MISSING_LOGGED.add((ev["key"], year))
                    logging.getLogger(__name__).warning("Chưa có ngày sự kiện %s cho năm %s", ev["key"], year)
                continue
            if d <= when <= end:
                found.append({"key": ev["key"], "name": ev["name"], "date": when,
                              "prep_start": when - timedelta(days=ev.get("prep_days", 28)),
                              "groups": list(ev["groups"])})
    return sorted(found, key=lambda e: e["date"])
