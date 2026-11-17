"""
F42: lọc thẻ (tag) gợi ý cho bài đăng — gom từ mọi nguồn (AI, tin tương đồng, thẻ trên sàn, Google)
rồi chỉ giữ thẻ NGẮN và ĐÚNG sản phẩm seller đang đăng.

Trước đây thẻ lẫn cụm cắt dở ("tròn nam", "pt cổ tròn"), thẻ toàn sàn không liên quan ("set áo váy"
cho nến thơm) và cụm Google dài ("ốp lưng iphone 17 pro max cho iphone 14 pro max").

Một thẻ được giữ khi:
  - ngắn: tối đa MAX_WORDS từ, MAX_CHARS ký tự;
  - không chứa con số / đời máy mà seller không ghi ("iphone 14" khi đăng iPhone 17);
  - và đúng sản phẩm: chứa tên loại sản phẩm ("nến thơm ...", "ốp lưng ..."), hoặc là thuộc tính
    seller tự ghi trong tên (chất liệu, màu, kiểu dáng: "sáp đậu nành", "cổ tròn"), hoặc là thương hiệu.
"""

import re
from typing import Iterable, List, Optional

from app.services.f42.comparable_pricing import _EDGE_STOP, _RISKY_TAG, _contains, _head_tokens, _prep
from app.services.f42.pricing_engine import MATERIAL_KEYWORDS

MAX_WORDS = 6            # đủ cho "ốp lưng iphone 17 pro max"; MAX_CHARS mới là giới hạn chính
MAX_CHARS = 30
MAX_TAGS = 10

# Thuộc tính hay gặp: chỉ nhận khi seller ghi đúng cụm đó trong tên/chất liệu
_ATTRIBUTE_PHRASES = [
    # màu
    "đen", "trắng", "đỏ", "xanh", "xanh navy", "xanh dương", "xanh lá", "vàng", "hồng", "tím", "nâu", "be",
    "xám", "kem", "cam", "bạc",
    # kiểu dáng / đối tượng
    "cổ tròn", "cổ tim", "cổ bẻ", "cổ lọ", "tay ngắn", "tay dài", "tay lỡ", "sát nách", "oversize", "form rộng",
    "unisex", "nam", "nữ", "trẻ em", "men rạn", "men lam", "chống sốc", "trong suốt", "handmade", "thủ công",
    "quà tặng",
]
_ATTRIBUTES = {_prep(p) for p in (*_ATTRIBUTE_PHRASES, *MATERIAL_KEYWORDS)}
# Thuộc tính đứng một mình quá chung để làm thẻ ("nam", "đen" → không ai tìm như vậy)
_TOO_GENERIC_ALONE = {_prep(p) for p in ("nam", "nữ", "đen", "trắng", "đỏ", "xanh", "vàng", "hồng", "be", "kem", "cam", "bạc", "nâu", "xám", "tím")}


def normalize_tag(tag: str) -> str:
    t = re.sub(r"\s+", " ", (tag or "").replace("#", " ")).strip(" ,.;:-_/|").strip()
    return t.lower()


def _is_short(t: str) -> bool:
    return 2 <= len(t) <= MAX_CHARS and len(t.split()) <= MAX_WORDS


def _numbers(prep: str) -> set:
    return {w for w in prep.split() if any(ch.isdigit() for ch in w)}


def _display(title: str, material: Optional[str], attr_prep: str) -> str:
    """Lấy nguyên cách viết có dấu của cụm thuộc tính trong tên/chất liệu seller ghi."""
    words = f"{title or ''} {material or ''}".split()
    n = len(attr_prep.split())
    for i in range(len(words) - n + 1):
        chunk = " ".join(words[i:i + n])
        if _prep(chunk) == attr_prep:
            return normalize_tag(chunk)
    return attr_prep


def curate_tags(
    candidates: Iterable[str],
    title: str,
    product: Optional[str] = None,
    material: Optional[str] = None,
    brand: Optional[str] = None,
    banned: Iterable[str] = (),
    max_tags: int = MAX_TAGS,
) -> List[str]:
    """Giữ thẻ ngắn, đúng sản phẩm, theo thứ tự ưu tiên của `candidates`; bỏ trùng."""
    title_prep = _prep(f"{title or ''} {material or ''}")
    head_toks = _head_tokens(_prep(title or ""))
    heads = {h for h in (_prep(product or ""), " ".join(head_toks)) if h}
    brand_prep = _prep(brand or "")
    allowed_numbers = _numbers(title_prep)
    banned_prep = {_prep(b) for b in banned if b}

    # Thẻ dựng từ chính tên seller nhập (chỉ ghép những gì seller đã ghi): tên đầy đủ nếu đủ ngắn,
    # "loại + thuộc tính" ("ví da handmade", "áo thun cổ tròn") — xếp sau thẻ từ AI/thị trường
    own: List[str] = [title or ""]
    head_text = normalize_tag(" ".join((title or "").split()[:len(head_toks)])) if head_toks else ""
    for attr in sorted(_ATTRIBUTES, key=len, reverse=True):
        if attr not in _TOO_GENERIC_ALONE and _contains(title_prep, attr) and not _contains(" ".join(head_toks), attr):
            if head_text and not set(attr.split()) & set(head_toks):     # tránh "ví da da bò"
                own.append(f"{head_text} {_display(title, material, attr)}")
            own.append(_display(title, material, attr))

    out: List[str] = []
    seen = {}
    for raw in [*candidates, *own]:
        tag = normalize_tag(raw)
        p = _prep(tag)
        if p in seen:
            # Cùng thẻ: giữ bản có dấu ("bình hoa gốm" thay cho "binh hoa gom" của tin đăng viết không dấu)
            if out[seen[p]] == p and tag != p:
                out[seen[p]] = tag
            continue
        if not p or not _is_short(tag):
            continue
        words = p.split()
        if p not in _ATTRIBUTES and (words[0] in _EDGE_STOP or words[-1] in _EDGE_STOP):   # "cho iphone", "dành cho"
            continue
        if any(_contains(p, r) for r in _RISKY_TAG) or any(_contains(p, b) for b in banned_prep):
            continue
        if _numbers(p) - allowed_numbers:                                 # đời máy/số đo seller không ghi
            continue
        is_head = any(_contains(p, h) for h in heads)
        is_attr = p in _ATTRIBUTES and p not in _TOO_GENERIC_ALONE and _contains(title_prep, p)
        is_brand = bool(brand_prep) and p == brand_prep
        if not (is_head or is_attr or is_brand):
            continue
        if len(words) == 1 and is_head and not is_attr and len(head_toks) >= 2:   # "bình" khi đăng "bình hoa"
            continue
        seen[p] = len(out)
        out.append(tag)
    return out[:max_tags]
