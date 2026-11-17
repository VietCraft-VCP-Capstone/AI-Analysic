from app.core.listing_intel.normalize import norm

MIN_NAME_LEN = 4
TYPE_WINDOW = 4
BUNDLE_WORDS = {"set", "combo", "bộ"}


def _find(words: list[str], name: list[str]) -> int | None:
    n = len(name)
    return next((i for i in range(len(words) - n + 1) if words[i:i + n] == name), None)


def better_category(title: str, current: str | None, names: list[str]) -> str | None:
    if not current or not isinstance(title, str):
        return None
    words, cur = norm(title).split(), norm(current).split()
    if not cur or _find(words, cur) is not None or BUNDLE_WORDS & set(words) or "+" in title:
        return None
    hits = set()
    for name in names:
        nw = norm(name).split()
        if len(" ".join(nw)) < MIN_NAME_LEN or nw == cur or nw[0] == cur[0]:
            continue
        at = _find(words, nw)
        if at is not None and at < TYPE_WINDOW:
            hits.add(name)
    return hits.pop() if len(hits) == 1 else None
