import re

KEYS = ("image", "description", "tags", "material", "review", "price")

LABELS = {
    "image": "Số ảnh",
    "description": "Số từ mô tả",
    "tags": "Số tag",
    "material": "Chất liệu",
    "review": "Tỉ lệ đánh giá tốt",
    "price": "Cạnh tranh giá",
}


def desc_words(text: str | None) -> int:
    if not text or not isinstance(text, str):
        return 0
    return len({t for t in re.findall(r"\w+", text.lower()) if len(t) >= 2 and not t.isdigit()})


def ratio_score(value: float | None, target: float) -> float:
    if value is None or value <= 0:
        return 0.0
    if value >= target:
        return 100.0
    return value / target * 100.0


def review_score(n_good: int, n: int, p0: float, m: float) -> float:
    if n <= 0:
        return 0.0
    return (n_good + m * p0) / (n + m) * 100.0


def price_score(price: float | None, ref: float | None, pc: dict) -> float:
    if price is None or ref is None or price <= 0 or ref <= 0:
        return 0.0
    rel = price / ref
    low_full = float(pc["low_full"])
    full_at = float(pc["full_at"])
    zero_at = float(pc["zero_at"])
    floor_at = float(pc["floor_at"])
    if rel < floor_at:
        return 50.0
    if rel < low_full:
        return 50.0 + (rel - floor_at) / (low_full - floor_at) * 50.0
    if rel <= full_at:
        return 100.0
    if rel < zero_at:
        return (zero_at - rel) / (zero_at - full_at) * 100.0
    return 0.0
