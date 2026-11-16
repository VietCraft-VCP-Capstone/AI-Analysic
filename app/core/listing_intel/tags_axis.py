from functools import cache
from itertools import islice

import numpy as np

from .lexicon import attributes
from .normalize import fold, norm

WEIGHTS = {"lift": 0.35, "trend": 0.25, "cos": 0.20, "attr": 0.20}
ATTR_GROUPS = ("material", "occasion", "use")
SUGGEST_GROUPS = ("material", "occasion", "use", "color")
FACT_GROUPS = ("material", "color")
PRODUCT_HEADS = tuple(fold(h) for h in (
    "áo", "quần", "váy", "chân váy", "đầm", "set", "đồ bộ", "giày", "dép", "túi", "ví", "balo", "mũ", "nón", "khăn",
    "thắt lưng", "vòng", "nhẫn", "dây chuyền", "bông tai", "đồng hồ", "kính", "tranh", "ly", "cốc", "bình", "phụ kiện"))
GROUP_LABEL = {"fashion": "Thời trang", "bags": "Túi xách", "shoes": "Giày dép", "accessories": "Phụ kiện",
               "home": "Đồ gia dụng", "sport": "Thể thao"}


def _verdict(folded, seen, pending, lift, trending):
    if folded in seen:
        return "duplicate", "Trùng với tag đã nhập phía trên"
    if folded in pending:
        return "pending", "Tag chưa được xác nhận trong danh mục từ khoá"
    if lift is not None and lift < 0 and not trending:
        return "weak", "Từ khoá ít xuất hiện ở sản phẩm bán chạy cùng nhóm"
    return "keep", "Tag phù hợp"


@cache
def _in_lexicon(term) -> bool:
    found = attributes(term)
    return norm(term) in {norm(h) for g in SUGGEST_GROUPS for h in found[g]}


@cache
def _fact_term(term) -> bool:
    found = attributes(term)
    return norm(term) in {norm(h) for g in FACT_GROUPS for h in found[g]}


def _product_type(term) -> bool:
    folded = fold(term)
    return any(folded == h or folded.startswith(f"{h} ") for h in PRODUCT_HEADS)


def suggestible(term, approved_norm=frozenset()) -> bool:
    return _in_lexicon(term) or (norm(term) in approved_norm and not _product_type(term))


def _suggest(group, table, title, folded_tags, approved, facts=""):
    text = "|".join(f" {x} " for x in [fold(title), *folded_tags])
    known = f" {fold(f'{title} {facts}')} "
    approved_norm = {norm(a) for a in approved}
    ranked, label = sorted(table.items(), key=lambda kv: -kv[1]), GROUP_LABEL.get(group, group)
    picks = (
        {"tag": t, "kind": "fact" if _fact_term(t) else "context",
         "reason": f"Từ khoá nổi bật ở sản phẩm bán chạy nhóm {label} (độ lift {v:.2f})".replace(".", ",")}
        for t, v in ranked
        if v > 0 and len(t.split()) <= 3 and f" {fold(t)} " not in text and suggestible(t, approved_norm)
        and (not _fact_term(t) or f" {fold(t)} " in known)
    )
    return list(islice(picks, 3))


def _attr_coverage(tags):
    found = attributes(" ".join(tags))
    return sum(1 for g in ATTR_GROUPS if found.get(g)) / len(ATTR_GROUPS)


def _mean_cos(tag_vecs, ref_vec):
    if tag_vecs is None or ref_vec is None:
        return None
    cos = [float(np.dot(v, ref_vec)) for v in tag_vecs if v is not None]
    return float(np.mean(np.clip(cos, 0.0, 1.0))) if cos else None


def tag_report(tags, title, group, lift, trend_terms, pending, tag_vecs, ref_vec,
               approved=frozenset(), suggest=True, facts=""):
    table = (lift or {}).get(group)
    folded = [fold(t) for t in tags]
    pend = {fold(p) for p in pending}
    trend = {fold(t) for t in trend_terms}
    suggestions = _suggest(group, table, title, folded, approved, facts) if table and suggest else []
    if not tags:
        return 0.0, [], suggestions
    seen, verdicts, lifts, trending = set(), [], [], []
    for tag, f in zip(tags, folded):
        lf = table.get(norm(tag), 0.0) if table is not None else None
        is_trend = f in trend
        verdict, reason = _verdict(f, seen, pend, lf, is_trend)
        verdicts.append({"tag": tag, "verdict": verdict, "reason": reason})
        seen.add(f)
        trending.append(is_trend)
        if lf is not None:
            lifts.append(float(np.clip(lf, 0.0, 2.0)) / 2)
    parts = {
        "lift": float(np.mean(lifts)) if lifts else None,
        "trend": float(np.mean(trending)),
        "cos": _mean_cos(tag_vecs, ref_vec),
        "attr": _attr_coverage(tags),
    }
    used = {k: v for k, v in parts.items() if v is not None}
    weight = sum(WEIGHTS[k] for k in used)
    raw = sum(WEIGHTS[k] * v for k, v in used.items()) / weight
    n_dup = sum(v["verdict"] == "duplicate" for v in verdicts)
    n_pend = sum(v["verdict"] == "pending" for v in verdicts)
    return float(np.clip(raw - 0.1 * n_dup - 0.05 * n_pend, 0.0, 1.0)), verdicts, suggestions
