KEYS = ("image", "description", "tags", "material", "review", "price")

LABELS = {
    "image": "Số ảnh",
    "description": "Độ dài mô tả",
    "tags": "Số tag",
    "material": "Chất liệu",
    "review": "Tỉ lệ đánh giá tốt",
    "price": "Cạnh tranh giá",
}


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


def price_score(price: float | None, ref: float | None,
                full_at: float, zero_at: float) -> float:
    if price is None or ref is None or price <= 0 or ref <= 0:
        return 0.0
    rel = price / ref
    if rel <= full_at:
        return 100.0
    if rel >= zero_at:
        return 0.0
    return (zero_at - rel) / (zero_at - full_at) * 100.0
