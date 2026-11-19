import json
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path

from app.api.v1._live import LOC_SP_THAT
from app.core.f29.price_ref import category_of
from app.core.listing_intel.normalize import fold, norm

MODEL_PATH = Path(__file__).with_name("relevance_model.json")
LEXICAL = {"version": "lexical-1", "enabled": False}
MIN_STRENGTH = 0.25


def _tokens(text) -> list:
    return fold(text).split()


def _strengths(query, text, assoc=None) -> list:
    seen = set(_tokens(text))
    rows = assoc or {}
    out = []
    for q in _tokens(query):
        if q in seen:
            out.append(1.0)
        else:
            row = rows.get(q, {})
            out.append(max((row.get(t, 0.0) for t in seen), default=0.0))
    return out


def product_text(product: dict) -> str:
    tags = [t for t in product.get("tags") or [] if isinstance(t, str)]
    return " ".join([product.get("title") or ""] + tags)


def covered(query, text) -> bool:
    s = _strengths(query, text)
    return bool(s) and min(s) == 1.0


def score(query, text, assoc=None) -> float:
    s = _strengths(query, text, assoc)
    return sum(s) / len(s) if s else 0.0


def relevant(query, text, model) -> bool:
    if not (model or {}).get("enabled"):
        return covered(query, text)
    s = _strengths(query, text, model.get("assoc"))
    return bool(s) and min(s) >= MIN_STRENGTH


def train(events) -> dict:
    counts = defaultdict(lambda: defaultdict(float))
    totals = defaultdict(float)
    for query, title, position in events:
        w = 1.0 / (position + 1)
        title_tokens = set(_tokens(title))
        for q in set(_tokens(query)):
            totals[q] += w
            for t in title_tokens:
                counts[q][t] += w
    return {q: {t: round(c / totals[q], 4) for t, c in row.items()} for q, row in counts.items()}


def category_queries(live_db, category, since) -> list:
    logs = list(live_db["search_logs"].find({"created_at": {"$gte": since}}, {"keyword": 1, "clicks": 1}))
    pids = [c["product_id"] for log in logs for c in log.get("clicks") or []]
    cats = {p["_id"]: category_of(p) for p in live_db["products"].find(
        {**LOC_SP_THAT, "_id": {"$in": pids}}, {"categories": 1, "category_ids": 1})}
    grouped = defaultdict(lambda: {"searches": 0, "cats": set(), "raw": Counter()})
    for log in logs:
        key = fold(log.get("keyword"))
        if not key:
            continue
        g = grouped[key]
        g["searches"] += 1
        g["raw"][norm(log.get("keyword"))] += 1
        for c in log.get("clicks") or []:
            if cats.get(c["product_id"]):
                g["cats"].add(cats[c["product_id"]])
    rows = [{"query": g["raw"].most_common(1)[0][0], "searches": g["searches"]}
            for g in grouped.values()
            if g["searches"] >= 2 and g["cats"] and (category is None or category in g["cats"])]
    return sorted(rows, key=lambda r: (-r["searches"], r["query"]))


GENERIC = frozenset("nam nữ unisex bé trẻ em người lớn đẹp cao cấp form rộng size màu đen trắng xanh đỏ hồng vàng nâu xám be set bộ mới hot giá rẻ cho và của thời trang phong cách chính hãng in hình".split())


def about(query, product) -> bool:
    own = set(norm(" ".join([product.get("title") or "", *(product.get("tags") or [])])).split())
    words = own | set(norm(category_of(product) or "").split())
    need = norm(query).split()
    return (any(w in own and w not in GENERIC for w in need)
            and sum(w in words for w in need) * 2 >= len(need))


def zero_result_queries(live_db, product, since, limit=5) -> list:
    logs = live_db["search_logs"].find({"created_at": {"$gte": since}, "result_count": 0}, {"keyword": 1})
    grouped = defaultdict(lambda: {"searches": 0, "raw": Counter()})
    for log in logs:
        key = fold(log.get("keyword"))
        if not key:
            continue
        grouped[key]["searches"] += 1
        grouped[key]["raw"][norm(log.get("keyword"))] += 1
    rows = [{"query": q, "searches": g["searches"]}
            for g in grouped.values() if g["searches"] >= 2
            for q in [g["raw"].most_common(1)[0][0]] if about(q, product)]
    return sorted(rows, key=lambda r: (-r["searches"], r["query"]))[:limit]


@lru_cache(maxsize=4)
def _read(path: Path) -> dict:
    try:
        model = json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        model = None
    return model if isinstance(model, dict) and model.get("enabled") else dict(LEXICAL)


def load_model(path: Path = MODEL_PATH) -> dict:
    return _read(path)
