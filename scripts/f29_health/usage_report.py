from collections import defaultdict
from datetime import timedelta

from app.core.f29.constants import MODEL_VERSION

CLICK = "open"
IMPL_WINDOW = timedelta(days=14)
RETURN_DAYS = 7
VN_SHIFT = timedelta(hours=7)
NO_DATA = "chưa có dữ liệu"
EVENT_FIELDS = {"_id": 0, "product_id": 1, "shop_id": 1, "recommendation_id": 1, "action": 1, "created_at": 1}
DOC_FIELDS = {"_id": 0, "product_id": 1, "date": 1, "recommendations.id": 1, "search.queries": 1}


def group_by_product(docs):
    groups = defaultdict(list)
    for d in docs:
        groups[d["product_id"]].append(d)
    for ds in groups.values():
        ds.sort(key=lambda d: d["date"])
    return groups


def rec_ids(doc):
    return {r["id"] for r in doc.get("recommendations") or []}


def covered_count(doc):
    return sum(1 for q in (doc.get("search") or {}).get("queries") or [] if q.get("covered"))


def first_clicks(events):
    first = {}
    for e in events:
        if e["action"] == CLICK:
            key = (e["product_id"], e["recommendation_id"])
            first[key] = min(first.get(key, e["created_at"]), e["created_at"])
    return first


def click_rate(events, docs):
    shown = {(d["product_id"], rid) for d in docs for rid in rec_ids(d)}
    return len(set(first_clicks(events)) & shown), len(shown)


def implementation(events, docs):
    by_product = group_by_product(docs)
    done = total = 0
    for (pid, rid), t0 in first_clicks(events).items():
        ds = by_product.get(pid, [])
        before = [d for d in ds if d["date"] <= t0]
        after = [d for d in ds if t0 < d["date"] <= t0 + IMPL_WINDOW]
        if not before or not after or rid not in rec_ids(before[-1]):
            continue
        total += 1
        if rid not in rec_ids(after[-1]):
            done += 1
    return done, total


def coverage_rise(docs):
    rose = eligible = 0
    for ds in group_by_product(docs).values():
        if len(ds) < 2:
            continue
        eligible += 1
        if covered_count(ds[-1]) > covered_count(ds[0]):
            rose += 1
    return rose, eligible


def gap_within(days):
    return any((b - a).days <= RETURN_DAYS for a, b in zip(days, days[1:]))


def returning_shops(events):
    days = defaultdict(set)
    for e in events:
        days[e["shop_id"]].add((e["created_at"] + VN_SHIFT).date())
    return sum(1 for ds in days.values() if gap_within(sorted(ds))), len(days)


def metrics(events, docs):
    return {
        "events": len(events),
        "click": click_rate(events, docs),
        "impl": implementation(events, docs),
        "coverage": coverage_rise(docs),
        "return": returning_shops(events),
    }


def _fmt(label, pair):
    num, den = pair
    value = f"{num}/{den} = {100 * num / den:.1f}%" if den else NO_DATA
    return f"{label}: {value}"


def lines(m):
    return [
        f"Số sự kiện hành động: {m['events'] or NO_DATA}",
        _fmt("Tỉ lệ bấm gợi ý (cặp sản phẩm+gợi ý đã bấm / đã hiển thị)", m["click"]),
        _fmt("Tỉ lệ làm theo (gợi ý bị bấm rồi biến mất ở doc sau trong 14 ngày / bấm có doc sau)", m["impl"]),
        _fmt("Sản phẩm có số truy vấn được phủ tăng (doc đầu → mới nhất / có ≥2 doc)", m["coverage"]),
        _fmt("Seller quay lại trong 7 ngày (có ≥2 ngày hoạt động / seller có sự kiện)", m["return"]),
    ]


def main():
    from app.api.v1._live import db_live

    db = db_live()
    events = list(db["health_action_events"].find({}, EVENT_FIELDS))
    docs = list(db["listing_health_scores"].find({"model_version": MODEL_VERSION}, DOC_FIELDS))
    print(f"Báo cáo sử dụng gợi ý sức khoẻ ({MODEL_VERSION})")
    print("\n".join(lines(metrics(events, docs))))


if __name__ == "__main__":
    main()
