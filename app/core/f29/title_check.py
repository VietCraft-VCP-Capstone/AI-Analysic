import re
from collections import Counter
from typing import List

from app.core.f29.constants import MAX_TITLE_LENGTH, MIN_TITLE_LENGTH

SCRAPED = re.compile(
    r"icon[\s_-]*(?:arrow|chevron|caret|close|heart|star|share|cart|search)"
    r"(?:[\s_-]*(?:left|right|up|down))?(?:[\s_-]*(?:bold|outline|filled|fill|thin|regular|solid))?"
    r"|\b(?:share|chia sẻ)\s*:"
    r"|\b(?:favorite|yêu thích|lượt thích)\s*\(\s*[\d.,]+\s*k?\s*\)"
    r"|\bđã bán\s*[\d.,]+\s*k?\b"
    r"|\b(?:mua ngay|thêm vào giỏ hàng|thêm vào giỏ|add to cart|buy now|xem thêm)\b"
    r"|https?://\S+|www\.\S+",
    re.IGNORECASE,
)
CONTACT = re.compile(
    r"(?:\b(?:liên hệ|lh|sđt|sdt|hotline)\s*:?\s*)?(?:(?<!\d)0(?:[\s.-]?\d){9}(?!\d)|\bzalo\b|\b(?:fb|facebook)\.com\S*)",
    re.IGNORECASE,
)
EDGE = " -–|:,·.;/"


def _clean(title: str) -> str:
    text = CONTACT.sub(" ", SCRAPED.sub(" ", title))
    return re.sub(r"\s+", " ", text).strip(EDGE)


def _short(parts: List[str]) -> str:
    return ", ".join(f"“{p.strip()[:30]}”" for p in dict.fromkeys(parts))


def _stuffed(title: str) -> str | None:
    words = re.findall(r"\w+", title.lower())
    pairs = Counter(" ".join(words[i:i + 2]) for i in range(len(words) - 1))
    top = pairs.most_common(1)
    return top[0][0] if top and top[0][1] >= 3 else None


def _shouting(title: str) -> bool:
    letters = [c for c in title if c.isalpha()]
    return len(letters) >= 15 and sum(c.isupper() for c in letters) / len(letters) >= 0.8


def check(title: str) -> List[dict]:
    hints: List[dict] = []
    scraped = [m.group(0) for m in SCRAPED.finditer(title)]
    contact = [m.group(0) for m in CONTACT.finditer(title)]
    cleaned = _clean(title)
    suggestion = cleaned if cleaned != title.strip() and len(cleaned) >= MIN_TITLE_LENGTH else None
    if scraped:
        hints.append({"type": "warning", "field": "title", "target": suggestion,
                      "message": f"Tên sản phẩm có chữ thừa copy từ trang khác: {_short(scraped)}"})
    if contact:
        hints.append({"type": "warning", "field": "title", "target": suggestion,
                      "message": f"Tên sản phẩm chứa thông tin liên hệ ({_short(contact)}), sàn không cho phép"})
    if not scraped and (len(title) < MIN_TITLE_LENGTH or len(title) > MAX_TITLE_LENGTH):
        hints.append({"type": "info", "field": "title", "message":
                      f"Tên sản phẩm dài {len(title)} ký tự, nên trong khoảng {MIN_TITLE_LENGTH}-{MAX_TITLE_LENGTH} ký tự"})
    stuffed = _stuffed(title)
    if stuffed:
        hints.append({"type": "info", "field": "title",
                      "message": f"Tên lặp lại cụm “{stuffed}” nhiều lần, nên viết gọn để khách dễ đọc"})
    if _shouting(title):
        hints.append({"type": "info", "field": "title",
                      "message": "Tên viết hoa toàn bộ, nên chỉ viết hoa chữ cái đầu cho dễ đọc"})
    return hints
