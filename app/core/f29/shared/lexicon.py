import json

from app.core.f29.paths import DATA as _DATA

from .normalize import fold, norm

_LEXICON = json.loads((_DATA / "lexicon.json").read_text("utf-8"))


def _parts(term: str) -> list[tuple[str, str]]:
    return [(u, fold(u)) for u in norm(term).split()]


def _tokens(text) -> list[tuple[str, bool]]:
    tokens = norm(text).split()
    plain = [True] + [t == fold(t) for t in tokens] + [True]
    return [(t, all(plain[i:i + 3])) for i, t in enumerate(tokens)]


def _find(parts, tokens, strict=False) -> list[int]:
    n = len(parts)
    return [
        i
        for i in range(len(tokens) - n + 1)
        if all(t == u or (ok and not strict and t == g) for (t, ok), (u, g) in zip(tokens[i:i + n], parts))
    ]


_MATERIAL_TERMS = [(t, _parts(t)) for t in _LEXICON["material"]]


NEXT_EXCLUDE = {
    "đồng": {"hồ", "nghiệp", "phục", "giá", "thời", "ý", "hành", "đội", "bộ", "nhất", "tiền", "bằng", "tình",
             "điệu", "loạt", "dạng", "minh", "hương", "quê", "ruộng", "bào", "chí", "tâm", "hành"},
    "dạ": {"hội", "quang", "dày", "con"},
}
PREV_EXCLUDE = {"đồng": {"cánh", "đồng", "một", "nghìn", "triệu", "giá"}}


def _excluded(term, i, n, tokens) -> bool:
    nxt = tokens[i + n][0] if i + n < len(tokens) else None
    prev = tokens[i - 1][0] if i > 0 else None
    return nxt in NEXT_EXCLUDE.get(term, ()) or prev in PREV_EXCLUDE.get(term, ())


def _match(terms, tokens) -> list[str]:
    used, hit = set(), set()
    for term, parts in sorted(terms, key=lambda x: -len(x[0])):
        for i in _find(parts, tokens):
            if _excluded(term, i, len(parts), tokens):
                continue
            span = range(i, i + len(parts))
            if used.isdisjoint(span):
                used.update(span)
                hit.add(term)
    return [t for t, _ in terms if t in hit]


def materials(text) -> list[str]:
    return _match(_MATERIAL_TERMS, _tokens(norm(text)))
