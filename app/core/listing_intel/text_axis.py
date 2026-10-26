from .lexicon import attributes, banned_hits
from .normalize import ngrams, norm
from .types import ListingInput

NAN = float("nan")
MATERIAL_GROUPS = {"fashion", "bags", "shoes", "accessories"}
VARIANT_GROUPS = {"fashion", "shoes"}


def _full_text(inp: ListingInput) -> str:
    parts = [inp.title, *(inp.tags or []), *(inp.materials or []), inp.description]
    return " ".join(p or "" for p in parts)


def _lift(inp: ListingInput, lift) -> dict[str, float]:
    table = (lift or {}).get(inp.group or "")
    if not table:
        return {"kw_lift_sum": NAN, "kw_lift_max": NAN, "kw_lift_terms": NAN}
    values = [table[g] for g in dict.fromkeys(ngrams(inp.title)) if g in table]
    return {
        "kw_lift_sum": float(sum(values)),
        "kw_lift_max": float(max(values, default=0.0)),
        "kw_lift_terms": float(len(values)),
    }


def text_features(inp: ListingInput, lift) -> dict[str, float]:
    title, description = inp.title or "", inp.description or ""
    tokens = norm(title).split()
    letters = [c for c in title if c.isalpha()]
    attrs = attributes(_full_text(inp))
    feats = {
        "title_len": float(len(title.strip())),
        "title_words": float(len(tokens)),
        "title_upper_ratio": sum(c.isupper() for c in letters) / len(letters) if letters else 0.0,
        "title_repeat_ratio": 1 - len(set(tokens)) / len(tokens) if tokens else 0.0,
        "title_banned": float(len(banned_hits(title))),
        "desc_len": float(len(description.strip())),
        "desc_words": float(len(norm(description).split())),
    }
    feats.update({f"attr_{k}": float(len(attrs[k])) for k in ("material", "color", "size", "occasion", "use")})
    feats.update(_lift(inp, lift))
    return feats


def _issue(code: str, message: str, field: str) -> dict:
    return {"code": code, "message": message, "field": field}


def text_issues(inp: ListingInput, feats: dict[str, float]) -> list[dict]:
    issues = []
    if feats["title_len"] < 20:
        issues.append(_issue("title_short", "Tiêu đề quá ngắn (dưới 20 ký tự).", "title"))
    if feats["title_len"] > 120:
        issues.append(_issue("title_long", "Tiêu đề quá dài (trên 120 ký tự).", "title"))
    if feats["title_repeat_ratio"] > 0.3:
        issues.append(_issue("keyword_stuffing", "Tiêu đề lặp từ khoá quá nhiều.", "title"))
    hits = banned_hits(f"{inp.title or ''} {inp.description or ''}")
    if hits:
        issues.append(_issue("banned_word", "Có từ bị cấm: " + ", ".join(hits) + ".", "title"))
    if inp.group in MATERIAL_GROUPS and not inp.materials and not feats["attr_material"]:
        issues.append(_issue("missing_material", "Chưa nêu chất liệu sản phẩm.", "materials"))
    if inp.group in VARIANT_GROUPS and not feats["attr_color"]:
        issues.append(_issue("missing_color", "Chưa nêu màu sắc.", "description"))
    if inp.group in VARIANT_GROUPS and not feats["attr_size"]:
        issues.append(_issue("missing_size", "Chưa nêu kích cỡ.", "description"))
    if feats["desc_len"] < 150:
        issues.append(_issue("desc_short", "Mô tả quá ngắn (dưới 150 ký tự).", "description"))
    return issues
