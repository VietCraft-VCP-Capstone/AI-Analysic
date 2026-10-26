from app.core.listing_intel.lexicon import attributes
from app.core.listing_intel.normalize import fold, norm

NEGATIONS = {"không", "ko", "chẳng", "chả", "no", "not", "non", "khong", "chang", "cha"}


def _is_negated(tokens: list[str], idx: int) -> bool:
    preceding = tokens[max(0, idx - 3):idx]
    return any(w in NEGATIONS or fold(w) in NEGATIONS for w in preceding)


def has_material(product: dict) -> bool:
    materials = product.get("materials")
    if isinstance(materials, list) and any(isinstance(m, str) and m.strip() for m in materials):
        return True
    text = " ".join(v for v in (product.get("title"), product.get("description")) if isinstance(v, str))
    found = attributes(text).get("material") or []
    if not found:
        return False
    tokens = norm(text).split()
    for mat in found:
        parts = norm(mat).split()
        n = len(parts)
        for i in range(len(tokens) - n + 1):
            window = tokens[i:i + n]
            if (window == parts or [fold(w) for w in window] == [fold(p) for p in parts]) and not _is_negated(tokens, i):
                return True
    return False
