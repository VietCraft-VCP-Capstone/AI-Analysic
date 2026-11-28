import json
import re
import unicodedata
from collections import Counter
from functools import cache
from pathlib import Path
from typing import List

from app.core.f29.paths import CONFIG, DATA
from app.core.f29.constants import MAX_TITLE_LENGTH, MIN_TITLE_LENGTH
from app.core.f29.shared.lexicon import materials as li_materials
from app.core.f29.shared.normalize import fold, norm as li_norm


MATERIALS: dict[str, list[str]] = json.loads(
    (DATA / "materials.json").read_text("utf-8"))
AMBIGUOUS = {"len", "lua", "da", "go", "su", "tre", "may", "gom"}
CONTEXT = ("vai", "soi", "chat lieu", "ao")
NEGATIONS = ("không phải", "không dùng", "không có", "không chứa", "ko phải", "chẳng phải")
EXCLUDED = ("sứ mệnh", "lên đến", "tăng lên", "gỗ ghề", "đồng hồ", "đồng phục", "đồng giá", "trẻ em")
LABEL = re.compile(r"(?:chất liệu|chat lieu)[ \t]*:[ \t]*(?:\n[ \t]*)?([^\n.!?;]*)[.!?;\n]?", re.IGNORECASE)


def norm(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text or "").lower().split())


def strip_accents(text: str) -> str:
    plain = "".join(c for c in unicodedata.normalize("NFD", text or "") if not unicodedata.combining(c))
    return plain.replace("đ", "d").replace("Đ", "D")


def sentences(text: str) -> list[str]:
    parts = re.split(r"[.!?;\n]", unicodedata.normalize("NFC", text or ""))
    cleaned = (re.sub(r"^\s*[-•*]+", "", p).strip() for p in parts)
    return [p for p in cleaned if p]


def material_line(text: str) -> tuple[str | None, str]:
    text = unicodedata.normalize("NFC", text or "").replace("\r\n", "\n")
    m = LABEL.search(text)
    if not m:
        return None, text
    rest = " ".join(p for p in (text[:m.start()].strip(), text[m.end():].strip()) if p)
    return norm(m.group(1)) or None, rest


def _words(text: str) -> tuple[str, ...]:
    return tuple(re.findall(r"\w+", norm(text)))


NEG_TERMS = [_words(n) for n in NEGATIONS]
EXCLUDED_TERMS = [_words(e) for e in EXCLUDED]
TERMS = sorted(((cls, _words(w)) for cls, ws in MATERIALS.items() for w in ws),
               key=lambda t: -len(" ".join(t[1])))


def _same(token: str, word: str) -> bool:
    return token in (word, strip_accents(word))


def _at(tokens, i: int, words) -> bool:
    return i + len(words) <= len(tokens) and all(_same(t, w) for t, w in zip(tokens[i:], words))


def _has_context(tokens, i: int) -> bool:
    before = " ".join(strip_accents(t) for t in tokens[max(0, i - 2):i])
    return any(before == c or before.endswith(" " + c) for c in CONTEXT)


def _blocked(tokens, i: int, words, plain: bool) -> bool:
    return (plain and len(words) == 1 and strip_accents(words[0]) in AMBIGUOUS
            and not _has_context(tokens, i))


def _negated(tokens, i: int) -> bool:
    return any(_at(tokens, j, neg) for neg in NEG_TERMS
               for j in range(max(0, i - 3 - len(neg)), i - len(neg) + 1))


def _drop_excluded(tokens: tuple[str, ...]) -> list[str]:
    drop = set()
    for words in EXCLUDED_TERMS:
        for i in range(len(tokens)):
            if _at(tokens, i, words):
                drop.update(range(i, i + len(words)))
    return [t for k, t in enumerate(tokens) if k not in drop]


def _clause_hits(text: str, plain: bool) -> list[tuple[int, str]]:
    tokens = _drop_excluded(_words(text))
    used, hits = set(), []
    for cls, words in TERMS:
        for i in range(len(tokens) - len(words) + 1):
            span = set(range(i, i + len(words)))
            if span & used or not _at(tokens, i, words) or _blocked(tokens, i, words, plain):
                continue
            used |= span
            if not _negated(tokens, i):
                hits.append((i, cls))
    return hits


def find_materials(text: str) -> list[str]:
    plain = norm(text) == strip_accents(norm(text))
    found = []
    for sentence in sentences(text):
        for clause in sentence.split(","):
            found += [cls for _, cls in sorted(_clause_hits(clause, plain))]
    return list(dict.fromkeys(found))


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


MATERIAL_NEGATIONS = {"không", "ko", "chẳng", "chả", "no", "not", "non", "khong", "chang", "cha"}
WEAVES = {"thun", "ren", "kaki", "jean", "denim", "nhung", "voan", "chiffon", "kate", "canvas", "nỉ", "dạ", "da pu", "simili"}
LOOKALIKE = {"màu", "giả", "vân"}
PARAMS_PATH = CONFIG / "price_params.json"
DEFAULT_PARAMS = {"materials": {}, "min_peers": 8, "full_n": 8}
FIBERS = {"cotton", "polyester", "spandex", "lụa", "len", "linen", "lanh", "đũi"}


def _is_negated(tokens: list[str], idx: int) -> bool:
    preceding = tokens[max(0, idx - 3):idx]
    return any(w in MATERIAL_NEGATIONS or fold(w) in MATERIAL_NEGATIONS for w in preceding) or (idx > 0 and tokens[idx - 1] in LOOKALIKE)


def _declared(product: dict) -> frozenset:
    raw = product.get("materials")
    raw = [raw] if isinstance(raw, str) else raw if isinstance(raw, list) else []
    declared = [m for m in raw if isinstance(m, str) and m.strip()]
    if not declared:
        return frozenset()
    text = f" {li_norm(' , '.join(declared))} "
    exact = [t for t in li_materials(text) if f" {li_norm(t)} " in text]
    return frozenset(exact or [li_norm(m) for m in declared])


def _titled(product: dict) -> frozenset:
    title = product.get("title")
    return frozenset(mentions(title, li_materials(title))) if isinstance(title, str) else frozenset()


def _compatible(a: str, b: str) -> bool:
    wa, wb = set(fold(a).split()), set(fold(b).split())
    if wa <= wb or wb <= wa:
        return True
    return (a in WEAVES and b in FIBERS) or (a in FIBERS and b in WEAVES)


def _conflict(declared: frozenset, titled: frozenset) -> bool:
    return bool(declared and titled and not any(_compatible(d, t) for d in declared for t in titled))


def material_conflict(product: dict) -> tuple[list[str], list[str]] | None:
    declared, titled = _declared(product), _titled(product)
    return (sorted(declared), sorted(titled)) if _conflict(declared, titled) else None


def materials_of(product: dict) -> frozenset:
    declared, titled = _declared(product), _titled(product)
    return frozenset() if _conflict(declared, titled) else declared or titled


@cache
def price_params(path: Path = PARAMS_PATH) -> dict:
    try:
        loaded = json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        loaded = {}
    return DEFAULT_PARAMS | loaded


def material_price_factor(materials) -> float:
    if not materials:
        return 1.0
    mats = [materials] if isinstance(materials, str) else list(materials)
    known = price_params()["materials"]
    found = [known[k] for k in (fold(str(m)).strip() for m in mats) if k in known]
    return round(float(max(found)), 3) if found else 1.0


def mentions(text: str, terms) -> list[str]:
    tokens = li_norm(text).split()
    folded = [fold(w) for w in tokens]
    hits = []
    for term in terms:
        parts = [fold(p) for p in li_norm(term).split()]
        n = len(parts)
        if any(folded[i:i + n] == parts and not _is_negated(tokens, i) for i in range(len(tokens) - n + 1)):
            hits.append(term)
    return hits


GARMENT_NAME = re.compile(r"\báo thun\b")


def has_material(product: dict) -> bool:
    materials = product.get("materials")
    if isinstance(materials, list) and any(isinstance(m, str) and m.strip() for m in materials):
        return True
    raw = " ".join(v for v in (product.get("title"), product.get("description")) if isinstance(v, str))
    text = GARMENT_NAME.sub(" ", li_norm(raw))
    found = li_materials(text)
    if not found:
        return False
    return bool(mentions(text, found))
