import json
import sys

from app.core.listing_intel import trend_store


def snapshot(series: dict) -> dict:
    return {k: {d.strftime("%Y-%m-%d"): round(float(v), 4) for d, v in s.items()} for k, s in sorted(series.items())}


def main() -> None:
    series = trend_store._to_series(trend_store._from_mongo())
    if not series:
        sys.exit(f"no weekly trend data in {trend_store.MONGO_DB}.trend_interest")
    data = snapshot(series)
    trend_store.SNAPSHOT.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), "utf-8")
    weeks = max(len(s) for s in data.values())
    print(f"wrote {trend_store.SNAPSHOT} ({len(data)} keywords, up to {weeks} weeks)")


if __name__ == "__main__":
    main()
