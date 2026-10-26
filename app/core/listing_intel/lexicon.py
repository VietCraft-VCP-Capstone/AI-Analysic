import json
import re
from pathlib import Path

from .normalize import fold, norm

_DATA = Path(__file__).parent / "data"
_LEXICON = json.loads((_DATA / "lexicon.json").read_text("utf-8"))
_BANNED = json.loads((_DATA / "banned_vi.json").read_text("utf-8"))


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


MATERIALS: list[str] = _LEXICON["material"]
_TERMS = {key: [(t, _parts(t)) for t in terms] for key, terms in _LEXICON.items()}
_BANNED_TERMS = [
    (p, _parts(p), len(fold(p)) <= 2) for p in dict.fromkeys(_BANNED["phrases"] + _BANNED["words"])
]


def _match(terms, tokens) -> list[str]:
    used, hit = set(), set()
    for term, parts in sorted(terms, key=lambda x: -len(x[0])):
        for i in _find(parts, tokens):
            span = range(i, i + len(parts))
            if used.isdisjoint(span):
                used.update(span)
                hit.add(term)
    return [t for t, _ in terms if t in hit]


def attributes(text) -> dict[str, list[str]]:
    tokens = _tokens(re.sub(r"(\d)(cm\b)", r"\1 \2", norm(text)))
    return {key: _match(terms, tokens) for key, terms in _TERMS.items()}


def banned_hits(text) -> list[str]:
    tokens = _tokens(text)
    return [p for p, parts, strict in _BANNED_TERMS if _find(parts, tokens, strict)]
