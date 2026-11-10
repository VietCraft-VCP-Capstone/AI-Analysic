"""Từ điển chất liệu: đưa cách người bán gõ tay ("bông", "100% cotton", "vải thun cotton") về tên chuẩn để so và gom giá.

Thêm cách gõ mới thì chỉ sửa TU_DIEN. Cách gõ có dấu "!" chỉ khớp khi gõ đúng dấu, vì bỏ dấu sẽ trùng từ khác
(gốm/gồm, lanh/lạnh, bông/bóng, da/đa).
"""

import re
import unicodedata
from functools import lru_cache
from typing import Any, Iterable, List, Set, Tuple

TU_DIEN = {
    "cotton": ["cotton", "coton", "!bông", "!sợi bông"],
    "polyester": ["polyester", "polyeste", "poly"],
    "spandex": ["spandex", "elastane", "lycra"],
    "linen": ["linen", "!lanh", "vải lanh"],
    "đũi": ["!đũi"],
    "lụa": ["!lụa", "silk", "tơ tằm"],
    "satin": ["satin"],
    "len": ["!len", "wool", "cashmere", "len lông cừu"],
    "nỉ": ["!nỉ", "fleece", "nỉ bông"],
    "kaki": ["kaki", "khaki"],
    "jean": ["jean", "jeans", "denim", "vải bò"],
    "canvas": ["canvas", "vải bố", "!bố"],
    "thun lạnh": ["thun lạnh"],
    "nylon": ["nylon", "nilon", "vải dù", "!dù"],
    "rayon": ["rayon", "viscose", "modal", "tencel"],
    "tre": ["!tre", "bamboo", "sợi tre"],
    "da thật": ["da thật", "da bò", "leather", "genuine leather"],
    "da PU": ["da pu", "pu", "simili", "giả da", "da tổng hợp"],
    "da": ["!da"],
    "gốm sứ": ["gốm sứ", "sành sứ", "!gốm", "!sứ", "!sành", "ceramic", "porcelain"],
    "thủy tinh": ["thủy tinh", "thuỷ tinh", "glass"],
    "pha lê": ["pha lê", "crystal"],
    "inox": ["inox", "thép không gỉ", "stainless", "stainless steel"],
    "nhôm": ["nhôm", "aluminum", "aluminium"],
    "đồng": ["!đồng", "brass", "copper"],
    "bạc": ["!bạc", "silver"],
    "kim loại": ["kim loại", "metal", "hợp kim", "thép", "!sắt", "steel"],
    "nhựa": ["nhựa", "plastic", "pp", "abs", "pvc"],
    "mica": ["mica", "acrylic"],
    "silicone": ["silicone", "silicon"],
    "cao su": ["cao su", "rubber"],
    "gỗ": ["!gỗ", "wood", "mdf", "plywood", "gỗ thông"],
    "giấy": ["giấy", "paper", "kraft", "giấy mỹ thuật"],
}


def _bo_dau(s: str) -> str:
    s = unicodedata.normalize("NFD", s.replace("đ", "d").replace("Đ", "D"))
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def _mau() -> List[Tuple[str, "re.Pattern[str]", bool]]:
    ra = []
    for ten, cach_go in TU_DIEN.items():
        for c in cach_go:
            dau = c.startswith("!")
            c = unicodedata.normalize("NFC", c.lstrip("!").lower())
            ra.append((ten, re.compile(rf"(?<!\w){re.escape(c if dau else _bo_dau(c))}(?!\w)"), dau, len(c)))
    # Cụm dài khớp trước rồi bị xoá khỏi chuỗi: "nỉ bông" không bị đọc thêm thành cotton, "thun lạnh" không thành linen.
    return [(t, rx, d) for t, rx, d, _ in sorted(ra, key=lambda x: -x[3])]


_MAU = _mau()


@lru_cache(maxsize=8192)
def chuan_hoa(m: Any) -> Tuple[str, ...]:
    """Các tên chuẩn có trong một chất liệu gõ tay; rỗng là không nhận ra (không đủ căn cứ để so)."""
    co_dau = unicodedata.normalize("NFC", str(m or "").lower())
    khong_dau = _bo_dau(co_dau)
    if len(khong_dau) != len(co_dau):       # ký tự lạ làm lệch vị trí: chỉ còn khớp không dấu
        co_dau = khong_dau
    a, b = list(co_dau), list(khong_dau)
    tim: Set[str] = set()
    for ten, rx, dau in _MAU:
        for mt in rx.finditer("".join(a if dau else b)):
            tim.add(ten)
            a[mt.start():mt.end()] = b[mt.start():mt.end()] = " " * (mt.end() - mt.start())
    return tuple(sorted(tim))


def tap_chuan(ds: Iterable[Any]) -> Set[str]:
    """Hợp các tên chuẩn của mọi chất liệu một sản phẩm ghi."""
    return {t for m in ds or [] for t in chuan_hoa(m)}
