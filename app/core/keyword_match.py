"""So khớp từ khóa với sản phẩm của shop (cho nút "Gắn thẻ" ở bảng Từ khóa hot).

Quy tắc:
- So theo NGUYÊN TỪ, không theo đoạn chữ: "in" không khớp "printing".
- Giữ dấu khi so. Chỉ khi một trường (tên/thẻ/danh mục/mô tả) được viết KHÔNG DẤU thì mới so
  bằng bản bỏ dấu: "Ao hoodie" khớp "áo hoodie". Bỏ dấu mọi lúc sẽ khớp nhầm hàng loạt vì tiếng
  Việt nhiều âm tiết trùng nhau khi bỏ dấu ("phông"/"phong", "đôi"/"đội", "mũ"/"mù").
- Hiểu một số nhóm từ đồng nghĩa phổ biến của hàng POD ("áo phông" ≈ "áo thun"); biến thể đồng
  nghĩa phải xuất hiện NGUYÊN CỤM.
- Tên, thẻ tag, danh mục: khớp khi có nguyên cụm từ khóa, hoặc (chỉ với từ khóa gốc) khi gộp
  lại có ≥ 75% số từ.
- Mô tả: chỉ khớp khi có nguyên cụm (≥ 2 từ), vì mô tả dài dễ chứa từ lẻ không liên quan, và
  bỏ qua chỗ gợi ý phối đồ ("dễ phối với áo thun").

Các hàm đều thuần để kiểm thử không cần MongoDB.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, List, Optional, Sequence, Tuple

TOKEN_COVERAGE_MIN = 0.75
MAX_TARGET_PRODUCTS = 100   # API gắn thẻ nhận tối đa 100 sản phẩm mỗi lần
DESCRIPTION_MAX_CHARS = 3000

# Mỗi nhóm là các cách gọi cùng một loại sản phẩm. Cụm dài được ưu tiên khi thay thế.
SYNONYM_GROUPS: Tuple[Tuple[str, ...], ...] = (
    ("áo thun", "áo phông", "t-shirt", "tshirt", "tee"),
    ("áo nỉ", "sweater", "sweatshirt"),
    ("áo hoodie", "hoodie", "áo nỉ có mũ"),
    ("áo đồng phục", "áo lớp", "áo nhóm", "áo team"),
    ("áo cặp đôi", "áo đôi", "áo couple"),
    ("áo gia đình", "áo family"),
    ("cốc", "ly", "mug"),
    ("túi tote", "tote bag", "túi vải"),
    ("móc khóa", "keychain"),
    ("ốp lưng", "phone case"),
    ("bình giữ nhiệt", "tumbler"),
)

_TAG_RE = re.compile(r"<[^>]+>")
_SENTENCE_SPLIT_RE = re.compile(r"[.!?;\n•]+")
_WORD_RE = re.compile(r"[^\W_]+")

# Hai cách bỏ dấu thanh khác nhau ("khóa"/"khoá") → đưa về một dạng
_TONE_PLACEMENT = {"oá": "óa", "oà": "òa", "oả": "ỏa", "oã": "õa", "oạ": "ọa",
                   "uý": "úy", "uỳ": "ùy", "uỷ": "ủy", "uỹ": "ũy", "uỵ": "ụy",
                   "oé": "óe", "oè": "òe", "oẻ": "ỏe", "oẽ": "õe", "oẹ": "ọe"}


def _lower_nfc(text: Any) -> str:
    s = unicodedata.normalize("NFC", str(text or "")).lower()
    for old, new in _TONE_PLACEMENT.items():
        s = s.replace(old, new)
    return s


def strip_accents(text: str) -> str:
    """Bỏ dấu tiếng Việt (đ → d). Đầu vào đã là chữ thường."""
    nfd = unicodedata.normalize("NFD", text.replace("đ", "d"))
    return "".join(c for c in nfd if unicodedata.category(c) != "Mn")


def tokens(text: Any) -> Tuple[str, ...]:
    """Tách nguyên từ (giữ dấu, chữ thường), bỏ thẻ HTML."""
    return tuple(_WORD_RE.findall(_lower_nfc(_TAG_RE.sub(" ", str(text or "")))))


def _plain(toks: Sequence[str]) -> Tuple[str, ...]:
    return tuple(strip_accents(t) for t in toks)


def _find(seq: Sequence[str], sub: Sequence[str]) -> int:
    """Vị trí đầu tiên của dãy từ `sub` liền nhau trong `seq`, -1 nếu không có."""
    n, m = len(seq), len(sub)
    if m == 0 or m > n:
        return -1
    first = sub[0]
    for i in range(n - m + 1):
        if seq[i] == first and tuple(seq[i:i + m]) == tuple(sub):
            return i
    return -1


_GROUP_TOKENS: List[List[Tuple[Tuple[str, ...], str]]] = [
    [(tokens(member), member) for member in group] for group in SYNONYM_GROUPS
]


def keyword_variants(keyword: str) -> List[Tuple[Tuple[str, ...], Optional[str]]]:
    """Từ khóa gốc + các biến thể thay cụm đồng nghĩa. Phần tử: (dãy từ có dấu, cụm đồng nghĩa | None)."""
    base = tokens(keyword)
    if not base:
        return []
    out: List[Tuple[Tuple[str, ...], Optional[str]]] = [(base, None)]
    seen = {base}
    base_plain = _plain(base)

    # Tìm các cụm đồng nghĩa có trong từ khóa (so bỏ dấu để nhận cả từ khóa gõ không dấu);
    # cụm dài thắng, không chồng lấn nhau
    found = []
    for gi, group in enumerate(_GROUP_TOKENS):
        for member_toks, _label in group:
            i = _find(base_plain, _plain(member_toks))
            if i >= 0:
                found.append((len(member_toks), i, gi, member_toks))
    found.sort(key=lambda f: -f[0])
    used: set = set()
    for length, i, gi, member_toks in found:
        span = set(range(i, i + length))
        if span & used:
            continue
        used |= span
        for alt_toks, alt_label in _GROUP_TOKENS[gi]:
            if alt_toks == member_toks:
                continue
            variant = base[:i] + alt_toks + base[i + length:]
            if variant not in seen:
                seen.add(variant)
                out.append((variant, alt_label))
    return out


def _field_texts(value: Any) -> List[str]:
    """Danh sách thẻ/danh mục có thể là chuỗi hoặc dict {name}."""
    if not value:
        return []
    if isinstance(value, (str, bytes)):
        value = [value]
    out = []
    for v in value:
        if isinstance(v, dict):
            v = v.get("name") or v.get("title") or ""
        if v:
            out.append(str(v))
    return out


def _field(text: str) -> Tuple[Tuple[str, ...], bool]:
    """(dãy từ, viết không dấu?). Trường không dấu thì lưu sẵn dạng bỏ dấu để so."""
    toks = tokens(text)
    plain = _plain(toks)
    return (plain, True) if plain == toks else (toks, False)


def build_product_index(shop_products: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Chuẩn hóa sản phẩm một lần để so với nhiều từ khóa."""
    index = []
    for p in shop_products or []:
        title = str(p.get("title") or p.get("name") or "")
        tag_texts = _field_texts(p.get("tags"))
        title_f = _field(title)
        tag_f = [_field(t) for t in tag_texts]
        cat_f = [_field(c) for c in _field_texts(p.get("categories"))]
        strong_acc: set = set()
        strong_plain: set = set()
        for toks, is_plain in [title_f, *tag_f, *cat_f]:
            (strong_plain if is_plain else strong_acc).update(toks)
        index.append({
            "id": str(p.get("_id") or p.get("id") or ""),
            "title": title,
            "title_f": title_f,
            "tag_f": tag_f,
            "cat_f": cat_f,
            "desc_f": [
                _field(sentence)
                for sentence in _SENTENCE_SPLIT_RE.split(
                    _TAG_RE.sub(". ", str(p.get("description") or "")[:DESCRIPTION_MAX_CHARS])
                )
                if sentence.strip()
            ],
            "strong_acc": strong_acc,
            "strong_plain": strong_plain,
            "tags_exact": {_squash(_lower_nfc(t)) for t in tag_texts},
        })
    return index


def _in_field(field: Tuple[Tuple[str, ...], bool], variant: Tuple[str, ...], variant_plain: Tuple[str, ...]) -> bool:
    toks, is_plain = field
    return _find(toks, variant_plain if is_plain else variant) >= 0


# Mô tả hay nhắc loại sản phẩm khác để gợi ý phối đồ ("dễ phối với áo thun", "khoác ngoài váy hay
# áo thun"). Lần xuất hiện nào có các từ này trong 3 từ đứng trước thì không tính.
_PAIRING_WORDS = {"phối", "với", "cùng", "kết", "hợp", "mix", "ngoài", "trong", "bên", "hay", "hoặc"}
_PAIRING_WORDS_PLAIN = {strip_accents(w) for w in _PAIRING_WORDS}
_PAIRING_WINDOW = 3


def _in_description(field: Tuple[Tuple[str, ...], bool], variant: Tuple[str, ...], variant_plain: Tuple[str, ...]) -> bool:
    toks, is_plain = field
    sub = variant_plain if is_plain else variant
    stop = _PAIRING_WORDS_PLAIN if is_plain else _PAIRING_WORDS
    m = len(sub)
    for i in range(len(toks) - m + 1):
        if tuple(toks[i:i + m]) == tuple(sub):
            if not any(t in stop for t in toks[max(0, i - _PAIRING_WINDOW):i]):
                return True
    return False


def _match_where(variant: Tuple[str, ...], item: Dict[str, Any], allow_coverage: bool) -> Optional[str]:
    """Trả nơi khớp ("tên" / "thẻ" / "danh mục" / "tên + thẻ" / "mô tả") hoặc None."""
    vp = _plain(variant)
    if _in_field(item["title_f"], variant, vp):
        return "tên"
    if any(_in_field(f, variant, vp) for f in item["tag_f"]):
        return "thẻ"
    if any(_in_field(f, variant, vp) for f in item["cat_f"]):
        return "danh mục"
    if allow_coverage:
        significant = [(t, p) for t, p in zip(variant, vp) if len(p) > 1]
        if len(significant) >= 2:
            hit = sum(1 for t, p in significant if t in item["strong_acc"] or p in item["strong_plain"])
            if hit / len(significant) >= TOKEN_COVERAGE_MIN:
                return "tên + thẻ"
    if len(variant) >= 2 and any(_in_description(s, variant, vp) for s in item["desc_f"]):
        return "mô tả"
    return None


def _has_exact_tag(keyword: str, tags_exact: set) -> bool:
    """Sản phẩm đã có ĐÚNG thẻ này (có dấu, không phân biệt hoa/thường và khoảng trắng thừa).

    Thẻ dài hơn như "áo thun nam" chưa tính là thẻ "áo thun": API gắn thẻ so theo đúng thẻ
    nên vẫn sẽ thêm thẻ mới; báo "Đã gắn" lúc đó là giấu mất hành động có ích.
    """
    kw = _squash(_lower_nfc(keyword))
    return bool(kw) and kw in tags_exact


def _squash(text: str) -> str:
    return " ".join(text.split())


def keyword_shop_coverage(
    keyword: str,
    shop_products: List[Dict[str, Any]],
    index: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Shop đã có bao nhiêu sản phẩm phù hợp với từ khóa → quyết định nút Tạo sản phẩm / Gắn thẻ."""
    total = len(shop_products or [])
    variants = keyword_variants(keyword)
    if not variants:
        return {"matching": 0, "total": total, "gap": True, "product_ids": [], "products": [], "already_tagged": False}
    if index is None:
        index = build_product_index(shop_products)

    matched: List[Dict[str, Any]] = []
    tagged_hits = 0
    for item in index:
        reason = None
        for variant, synonym in variants:
            where = _match_where(variant, item, allow_coverage=synonym is None)
            if where:
                reason = where if synonym is None else f"{where}, đồng nghĩa «{synonym}»"
                break
        if reason is None:
            continue
        matched.append({"id": item["id"], "title": item["title"], "matched_by": reason})
        if _has_exact_tag(keyword, item["tags_exact"]):
            tagged_hits += 1

    targets = matched[:MAX_TARGET_PRODUCTS]
    return {
        "matching": len(matched),
        "total": total,
        "gap": len(matched) == 0,
        "product_ids": [m["id"] for m in targets],
        "products": targets,
        "already_tagged": len(matched) > 0 and tagged_hits == len(matched),
    }
