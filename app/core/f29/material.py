import json
from functools import cache
from pathlib import Path

from app.core.listing_intel.lexicon import materials as find_materials
from app.core.listing_intel.normalize import fold, norm

NEGATIONS = {"không", "ko", "chẳng", "chả", "no", "not", "non", "khong", "chang", "cha"}
WEAVES = {"thun", "ren", "kaki", "jean", "denim", "nhung", "voan", "chiffon", "kate", "canvas", "nỉ", "dạ", "da pu", "simili"}
LOOKALIKE = {"màu", "giả", "vân"}
PARAMS_PATH = Path(__file__).parent / "price_params.json"
DEFAULT_PARAMS = {"materials": {}, "min_peers": 8, "full_n": 8}
FIBERS = {"cotton", "polyester", "spandex", "lụa", "len", "linen", "lanh", "đũi"}


def _is_negated(tokens: list[str], idx: int) -> bool:
    preceding = tokens[max(0, idx - 3):idx]
    return any(w in NEGATIONS or fold(w) in NEGATIONS for w in preceding) or (idx > 0 and tokens[idx - 1] in LOOKALIKE)


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
    return frozenset(mentions(title, find_materials(title))) if isinstance(title, str) else frozenset()


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
    tokens = norm(text).split()
    folded = [fold(w) for w in tokens]
    hits = []
    for term in terms:
        parts = [fold(p) for p in norm(term).split()]
        n = len(parts)
        if any(folded[i:i + n] == parts and not _is_negated(tokens, i) for i in range(len(tokens) - n + 1)):
            hits.append(term)
    return hits


def has_material(product: dict) -> bool:
    materials = product.get("materials")
    if isinstance(materials, list) and any(isinstance(m, str) and m.strip() for m in materials):
        return True
    text = " ".join(v for v in (product.get("title"), product.get("description")) if isinstance(v, str))
    found = find_materials(text)
    if not found:
        return False
    return bool(mentions(text, found))
