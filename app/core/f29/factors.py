import re

KEYS = ("image", "description", "tags", "review", "price")

LABELS = {
    "image": "Hình ảnh",
    "description": "Mô tả",
    "tags": "Tag",
    "review": "Đánh giá",
    "price": "Giá bán",
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
