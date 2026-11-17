from app.core.listing_intel.lexicon import materials as find_materials
from app.core.listing_intel.normalize import fold, norm

NEGATIONS = {"không", "ko", "chẳng", "chả", "no", "not", "non", "khong", "chang", "cha"}
WEAVES = {"thun", "ren", "kaki", "jean", "denim", "nhung", "voan", "chiffon", "kate", "canvas", "nỉ", "dạ", "da pu", "simili"}
FIBERS = {"cotton", "polyester", "spandex", "lụa", "len", "linen", "lanh", "đũi"}


def _is_negated(tokens: list[str], idx: int) -> bool:
    preceding = tokens[max(0, idx - 3):idx]
    return any(w in NEGATIONS or fold(w) in NEGATIONS for w in preceding)


def _declared(product: dict) -> frozenset:
    raw = product.get("materials")
    raw = [raw] if isinstance(raw, str) else raw if isinstance(raw, list) else []
    declared = [m for m in raw if isinstance(m, str) and m.strip()]
    if not declared:
        return frozenset()
    text = f" {norm(' , '.join(declared))} "
    exact = [t for t in find_materials(text) if f" {norm(t)} " in text]
    return frozenset(exact or [norm(m) for m in declared])


def _titled(product: dict) -> frozenset:
    title = product.get("title")
    return frozenset(find_materials(title)) if isinstance(title, str) else frozenset()


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


MATERIAL_PRICE_WEIGHTS: dict[str, float] = {
    "da that": 2.2,
    "da bo": 2.2,
    "da cuu": 2.3,
    "da": 1.6,
    "lua": 1.8,
    "to tam": 1.9,
    "silk": 1.8,
    "gam": 1.5,
    "cashmere": 1.8,
    "len": 1.45,
    "wool": 1.45,
    "linen": 1.35,
    "lanh": 1.35,
    "dui": 1.3,
    "nhung": 1.3,
    "velvet": 1.3,
    "denim": 1.2,
    "jean": 1.2,
    "canvas": 1.15,
    "kaki": 1.1,
    "khaki": 1.1,
    "ren": 1.15,
    "voan": 1.05,
    "chiffon": 1.05,
    "kate": 1.0,
    "ni": 1.1,
    "cotton": 1.0,
    "thun": 0.95,
    "da pu": 0.9,
    "pu": 0.9,
    "simili": 0.85,
    "polyester": 0.85,
    "poly": 0.85,
    "spandex": 0.9,
    "nylon": 0.85,
}


def material_price_factor(materials) -> float:
    if not materials:
        return 1.0
    if isinstance(materials, str):
        mats = [materials]
    else:
        mats = list(materials)
    factors = []
    for m in mats:
        m_norm = fold(str(m)).strip()
        matched = False
        for k, factor in MATERIAL_PRICE_WEIGHTS.items():
            if k == m_norm or f" {k} " in f" {m_norm} ":
                factors.append(factor)
                matched = True
                break
        if not matched and m_norm in MATERIAL_PRICE_WEIGHTS:
            factors.append(MATERIAL_PRICE_WEIGHTS[m_norm])
    if not factors:
        return 1.0
    return round(float(max(factors)), 2)


def has_material(product: dict) -> bool:
    materials = product.get("materials")
    if isinstance(materials, list) and any(isinstance(m, str) and m.strip() for m in materials):
        return True
    text = " ".join(v for v in (product.get("title"), product.get("description")) if isinstance(v, str))
    found = find_materials(text)
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
