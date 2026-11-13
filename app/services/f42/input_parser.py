"""
Lọc & phân tích tiêu đề seller nhập TRƯỚC khi định giá và viết tiêu đề (F42).

Seller hay gõ: "🔥HOT🔥 [FREESHIP] Combo 2 ốp lưng iphone 18 promax 256 gb hàng mới về giá rẻ".
Nếu đưa nguyên câu đó đi so giá thì chữ quảng cáo làm lệch kết quả tìm kiếm, "combo 2" bị so với
giá 1 cái, "promax" không khớp "Pro Max". Module này:
  1. làm sạch: bỏ emoji, nhãn quảng cáo trong ngoặc, cụm câu khách; chuẩn hoá đơn vị & cách viết liền;
  2. tách thuộc tính: số lượng (combo/set/bộ), tình trạng (mới/cũ), dung lượng, thể tích, kích cỡ, màu, chất liệu;
  3. nêu vấn đề cho seller sửa: tiêu đề quá mơ hồ, cam kết cần chứng nhận, hàng cũ, combo.
Không tự bịa thông tin: chỉ lấy những gì seller đã gõ.
"""

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from app.services.f42.pricing_engine import detect_material
from app.services.f42.vi_text import clean_tokens, normalize_nfc, strip_accents

# Cụm câu khách / quảng cáo: không mô tả sản phẩm, chỉ làm lệch so khớp (so trên bản không dấu)
_NOISE_PHRASES = [
    "hang moi ve", "moi ve", "hang moi", "hang co san", "co san", "san hang", "gia re nhat", "gia re", "gia tot",
    "sieu re", "re nhat", "giam gia", "sale off", "flash sale", "sale soc", "gia soc", "sieu sale", "sale", "freeship", "free ship", "mien phi van chuyen",
    "hot trend", "hot", "new arrival", "loai 1", "loai mot", "cao cap nhat", "ban chay", "best seller",
    "chat luong cao", "uy tin", "dep long lanh", "xa kho", "thanh ly", "mua 1 tang 1", "qua tang", "tang kem",
]
# Nhãn trong ngoặc mang tính quảng cáo: [VOUCHER 30K], (FREESHIP), 【HOT】
_PROMO_BRACKET = re.compile(r"[\[\(【「](?=[^\]\)】」]*(?:voucher|freeship|free ship|sale|hot|giam|giảm|mua|tang|tặng|deal|qua|quà))[^\]\)】」]*[\]\)】」]",
                            re.IGNORECASE)
_EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿️‍]")
# Cam kết cần chứng nhận — trùng danh sách kiểm duyệt nội dung, chỉ nhắc seller
_RISKY = ["chinh hang", "hang hieu", "authentic", "auth", "bao hanh tron doi", "tot nhat", "so 1", "100% cotton",
          "da that 100%", "organic", "huu co"]

_QTY_RE = re.compile(r"\b(?:combo|set|bo|lo|goi|pack)\s*(\d{1,3})\b|\b(\d{1,3})\s*(?:cai|chiec|mon|san pham|sp)\b|\bx\s*(\d{1,3})\b")
_STORAGE_RE = re.compile(r"\b(\d{2,4})\s*(gb|tb)\b", re.IGNORECASE)
_VOLUME_RE = re.compile(r"\b(\d{2,5})\s*(ml|l|lit|lít)\b", re.IGNORECASE)
_SIZE_RE = re.compile(r"\bsize\s*([0-9]{1,2}|xs|s|m|l|xl|xxl|xxxl|2xl|3xl|free\s*size)\b", re.IGNORECASE)
_DIM_RE = re.compile(r"\b(\d{1,3}(?:[.,]\d)?)\s*(cm|mm|inch|in)\b", re.IGNORECASE)
_USED = ["da qua su dung", "hang cu", "like new", "2nd", "second hand", "secondhand", "99%", "98%", "95%", "cu dep",
         "do cu", "may cu", "ban cu"]
# Từ chỉ hàng cũ phải so CÓ dấu: "cũ" ≠ "củ" (củ cải), "xài rồi"
_USED_EXACT = ["cũ", "xài rồi", "đã dùng"]
_COLORS = ["đen", "trắng", "xám", "ghi", "be", "kem", "nâu", "đỏ", "đỏ đô", "hồng", "cam", "vàng", "xanh lá", "xanh dương",
           "xanh navy", "xanh rêu", "xanh", "tím", "bạc", "vàng gold", "titan", "trong suốt"]
_JOINED = {"promax": "Pro Max", "prm": "Pro Max", "proplus": "Pro Plus"}


@dataclass
class ParsedInput:
    raw_title: str
    clean_title: str                       # tiêu đề sạch: dùng cho Gemini và hiển thị
    pricing_query: str                     # tiêu đề để so giá 1 sản phẩm (bỏ combo/tình trạng)
    quantity: int = 1
    condition: str = "new"                 # new | used
    attributes: Dict[str, str] = field(default_factory=dict)
    removed: List[str] = field(default_factory=list)   # cụm đã bỏ (cho seller thấy)
    issues: List[str] = field(default_factory=list)    # điều seller nên sửa

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def attribute_text(self) -> str:
        """Thuộc tính dạng câu cho Gemini — chỉ những gì seller đã nêu."""
        return "; ".join(f"{k}: {v}" for k, v in self.attributes.items())


def _remove_phrase(text: str, phrase_noacc: str, exact: bool = False):
    """
    Bỏ 1 cụm khỏi text, giữ nguyên dấu phần còn lại. Trả (text mới, cụm gốc đã bỏ) hoặc None.
    So không dấu; exact=True thì so CÓ dấu (phân biệt "cũ" với "củ").
    """
    toks = text.split()
    norm = (lambda t: t.lower().strip(",.;:!-")) if exact else (lambda t: strip_accents(t).lower().strip(",.;:!-"))
    seq = [norm(t) for t in toks]
    p = phrase_noacc.split()
    for i in range(len(toks) - len(p) + 1):
        if seq[i:i + len(p)] == p:
            return " ".join(toks[:i] + toks[i + len(p):]), " ".join(toks[i:i + len(p)])
    return None


def parse_seller_input(title: str, material: str = "") -> ParsedInput:
    raw = normalize_nfc(title or "").strip()
    text = _EMOJI.sub(" ", raw)
    removed: List[str] = []

    for m in _PROMO_BRACKET.finditer(text):
        removed.append(m.group(0))
    text = _PROMO_BRACKET.sub(" ", text)
    text = re.sub(r"[!?*~#=|_]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip(" -–,.;:")

    # cụm câu khách (dài trước để "giá rẻ nhất" không bị cắt thành "nhất")
    for ph in sorted(_NOISE_PHRASES, key=len, reverse=True):
        while True:
            out = _remove_phrase(text, ph)
            if out is None:
                break
            text, original = out
            removed.append(original)   # hiện đúng chữ seller gõ

    # chuẩn hoá cách viết
    text = " ".join(_JOINED.get(w.lower(), w) for w in text.split())
    text = re.sub(r"\b(\d+)\s*(gb|tb)\b", lambda m: f"{m.group(1)}{m.group(2).upper()}", text, flags=re.IGNORECASE)
    text = re.sub(r"\b(\d+)\s*(ml)\b", r"\1ml", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip(" -–,.;:")

    noacc = strip_accents(text).lower()
    attrs: Dict[str, str] = {}
    issues: List[str] = []

    # số lượng
    qty = 1
    m = _QTY_RE.search(noacc)
    if m:
        qty = int(next(g for g in m.groups() if g))
        if 2 <= qty <= 100:
            attrs["Số lượng"] = f"{qty} sản phẩm/đơn"
        else:
            qty = 1

    # tình trạng
    used_hits = [u for u in _USED if f" {u} " in f" {noacc} "]
    used_exact = [u for u in _USED_EXACT if re.search(rf"(?<!\w){re.escape(u)}(?!\w)", text.lower())]
    condition = "used" if used_hits or used_exact else "new"
    if condition == "used":
        attrs["Tình trạng"] = "Đã qua sử dụng"
        issues.append("Hàng đã qua sử dụng: dữ liệu giá thị trường chủ yếu là hàng mới nên giá tham khảo sẽ CAO hơn "
                      "giá bán thực tế của hàng cũ — nên đặt thấp hơn mức gợi ý.")

    if (s := _STORAGE_RE.search(text)):
        attrs["Dung lượng"] = f"{s.group(1)}{s.group(2).upper()}"
    if (v := _VOLUME_RE.search(text)):
        attrs["Thể tích"] = f"{v.group(1)}{v.group(2).lower()}"
    if (z := _SIZE_RE.search(text)):
        attrs["Kích cỡ"] = z.group(1).upper()
    elif (d := _DIM_RE.search(text)):
        attrs["Kích thước"] = f"{d.group(1)}{d.group(2)}"
    low = text.lower()
    for c in sorted(_COLORS, key=len, reverse=True):
        if re.search(rf"(?<!\w)(?:màu\s+)?{re.escape(c)}(?!\w)", low):
            attrs["Màu"] = c
            break
    mat = (material or "").strip() or detect_material(text)
    if mat:
        attrs["Chất liệu"] = mat

    # tiêu đề để so giá: bỏ cụm số lượng & tình trạng (so giá 1 sản phẩm mới, rồi nhân/ghi chú sau)
    pricing = text
    if qty > 1 and m:
        for ph in [f"combo {qty}", f"set {qty}", f"bo {qty}", f"lo {qty}", f"goi {qty}", f"pack {qty}",
                   f"{qty} cai", f"{qty} chiec", f"{qty} mon", f"x{qty}", f"x {qty}"]:
            out = _remove_phrase(pricing, ph)
            pricing = out[0] if out else pricing
    if condition == "used":
        for u in sorted(_USED, key=len, reverse=True):
            out = _remove_phrase(pricing, u)
            pricing = out[0] if out else pricing
        for u in _USED_EXACT:
            out = _remove_phrase(pricing, u, exact=True)
            pricing = out[0] if out else pricing

    # vấn đề cần seller sửa
    words = [t for t in clean_tokens(pricing) if not t.isdigit()]
    if len(words) < 2:
        issues.append("Tiêu đề quá ngắn — ghi rõ loại sản phẩm, thương hiệu/mẫu, chất liệu, kích thước để có giá gợi ý sát hơn.")
    risky = [r for r in _RISKY if f" {r} " in f" {noacc} "]
    if risky:
        issues.append(f"Tiêu đề có cam kết cần chứng nhận ({', '.join(risky)}): chỉ giữ nếu có giấy tờ chứng minh.")
    if qty > 1:
        issues.append(f"Đây là combo {qty} sản phẩm: giá thị trường được tính cho 1 sản phẩm rồi nhân {qty}.")
    if removed:
        issues.append("Đã bỏ các cụm quảng cáo không mô tả sản phẩm khi so giá: " + ", ".join(dict.fromkeys(removed)) + ".")

    return ParsedInput(raw_title=raw, clean_title=text or raw, pricing_query=pricing.strip() or text or raw,
                       quantity=qty, condition=condition, attributes=attrs, removed=list(dict.fromkeys(removed)),
                       issues=issues)
