import re
from typing import Any, Dict, List

from app.core.f29.factors_v3 import has_size
from app.core.f29.material import mentions

REASONS = {
    "process": ("làm tay", "thủ công", "handmade", "chạm khắc", "chạm tay", "khắc tay", "đan tay", "thêu tay",
                "vẽ tay", "dệt tay", "nung thủ công"),
    "origin": ("làng nghề", "bát tràng", "vạn phúc", "chu đậu", "phù lãng", "bàu trúc", "kim bồng", "nghệ nhân",
               "xuất xứ"),
    "warranty": ("bảo hành", "chứng nhận", "kiểm định", "ocop"),
}
MEASURE = re.compile(r"\b\d+(?:[.,]\d+)?\s*(?:mm|cm|m|g|kg|ml|l)\b", re.IGNORECASE)


def _text(product: Dict[str, Any], duplicate: bool) -> str:
    parts = [product.get("title")] + ([] if duplicate else [product.get("description")])
    return " ".join(p for p in parts if isinstance(p, str))


def price_reasons(product: Dict[str, Any], duplicate: bool = False) -> List[str]:
    text = _text(product, duplicate)
    found = [k for k, terms in REASONS.items() if mentions(text, terms)]
    if has_size(product, "") or MEASURE.search(text):
        found.append("size")
    return found
