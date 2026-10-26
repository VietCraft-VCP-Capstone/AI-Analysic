import re
import unicodedata

_MARKS = "̣̀́̉̃"
_TONE_FIX = {
    unicodedata.normalize("NFC", f"{a}{b}{m}"): unicodedata.normalize("NFC", f"{a}{m}{b}")
    for a, b in ("oa", "oe", "uy")
    for m in _MARKS
}
_TONE_RE = re.compile(r"(?<!q)(" + "|".join(_TONE_FIX) + r")(?!\w)")
_APOSTROPHE = re.compile(r"(?<=[^\W\d_])['’ʼ`´](?=[^\W\d_])")


def norm(text) -> str:
    text = unicodedata.normalize("NFC", str(text or "")).lower()
    text = _APOSTROPHE.sub("", text)
    text = _TONE_RE.sub(lambda m: _TONE_FIX[m.group(1)], text)
    return re.sub(r"[\W_]+", " ", text).strip()


def fold(text) -> str:
    decomposed = unicodedata.normalize("NFD", norm(text))
    plain = "".join(c for c in decomposed if not unicodedata.combining(c))
    return plain.replace("đ", "d")


def ngrams(text, n=(1, 2)) -> list[str]:
    tokens = norm(text).split()
    return [" ".join(tokens[i:i + k]) for k in n for i in range(len(tokens) - k + 1)]


def tokens(text) -> list[str]:
    return norm(text).split()
