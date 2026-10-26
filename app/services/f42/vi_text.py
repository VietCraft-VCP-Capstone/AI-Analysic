import re
import unicodedata
from typing import List, Set


def normalize_nfc(text: str) -> str:
    """Chuẩn hóa chuỗi Unicode sang NFC."""
    if not text:
        return ""
    return unicodedata.normalize("NFC", str(text)).strip()


def strip_accents(text: str) -> str:
    """Bỏ dấu tiếng Việt phục vụ so khớp mềm."""
    if not text:
        return ""
    t = normalize_nfc(text)
    t = t.replace("đ", "d").replace("Đ", "D")
    nfd = unicodedata.normalize("NFD", t)
    return "".join(c for c in nfd if unicodedata.category(c) != "Mn").lower().strip()


def clean_tokens(text: str) -> List[str]:
    """Tách từ đơn thuần túy loại bỏ ký tự đặc biệt."""
    norm = normalize_nfc(text).lower()
    cleaned = re.sub(r"[^\w\s]", " ", norm, flags=re.UNICODE)
    tokens = [w.strip() for w in cleaned.split() if len(w.strip()) >= 1]
    return tokens


def get_ngrams(tokens: List[str], n: int = 2) -> List[str]:
    """Sinh n-gram từ danh sách token."""
    if not tokens:
        return []
    res = list(tokens)
    if n >= 2 and len(tokens) >= 2:
        for i in range(len(tokens) - 1):
            res.append(f"{tokens[i]} {tokens[i+1]}")
    return res


def contains_phrase_boundary(text: str, phrase: str) -> bool:
    """
    Kiểm tra phrase có nằm trong text theo ranh giới từ tiếng Việt chuẩn.
    Không dùng \\b thuần vì Python regex \\b bị lỗi với ký tự Unicode có dấu.
    """
    if not text or not phrase:
        return False
    t_norm = f" {normalize_nfc(text).lower()} "
    p_norm = normalize_nfc(phrase).lower()
    
    # Ranh giới: trước và sau phrase không được là ký tự chữ cái/chữ số
    pattern = rf"(?<![\w]){re.escape(p_norm)}(?![\w])"
    return bool(re.search(pattern, t_norm, flags=re.UNICODE))


def contains_phrase_lenient(text: str, phrase: str) -> bool:
    """
    Kiểm tra cả có dấu lẫn không dấu để bắt triệt để.
    """
    if contains_phrase_boundary(text, phrase):
        return True
    t_stripped = f" {strip_accents(text)} "
    p_stripped = strip_accents(phrase)
    pattern = rf"(?<![\w]){re.escape(p_stripped)}(?![\w])"
    return bool(re.search(pattern, t_stripped))
