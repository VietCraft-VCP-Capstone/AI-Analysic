import numpy as np

from .axes import issue
from .normalize import fold, ngrams, norm
from .tags_axis import tag_report
from .trend_axis import LO, HI, momentum
from .types import AxisResult

UP = 0.1
MIN_TAGS = 3
MAX_KEYWORDS = 10
TAG_ISSUES = {
    "duplicate": ("duplicate_tag", "Có tag trùng lặp, nên xoá bớt và thay bằng từ khoá khác."),
    "pending": ("pending_tag", "Có tag đang chờ duyệt, chưa giúp khách tìm thấy sản phẩm."),
    "weak": ("weak_tag", "Có tag ít xuất hiện ở sản phẩm bán chạy cùng nhóm."),
}


def percentile(value: float, others: list[float]):
    if not others:
        return None
    a = np.asarray(others, dtype=float)
    return float(100 * (np.sum(a < value) + 0.5 * np.sum(a == value)) / len(a))


def direction(m):
    if m is None:
        return None
    return "up" if m > UP else "down" if m < -UP else "flat"


def rising(ctx) -> list[str]:
    return [k for k, s in ctx.trend_series.items() if momentum(s, ctx.at) > 0]


def tag_raw(inp, ctx, terms, pending) -> float:
    return tag_report(inp.tags, inp.title, inp.group, ctx.lift, terms, pending, None, None, suggest=False)[0]


def tags_axis(inp, peer_raws, ctx, pending, approved=frozenset()):
    raw, verdicts, suggestions = tag_report(inp.tags, inp.title, inp.group, ctx.lift, rising(ctx), pending,
                                            None, None, approved)
    pct = percentile(raw, peer_raws)
    found = {v["verdict"] for v in verdicts}
    issues = [issue(*TAG_ISSUES[k]) for k in TAG_ISSUES if k in found]
    if not inp.tags:
        issues.append(issue("no_tags", "Chưa có tag nào, thêm 3–5 tag về chất liệu, phong cách và dịp dùng."))
    elif len(inp.tags) < MIN_TAGS:
        issues.append(issue("few_tags", "Nên có ít nhất 3 tag về chất liệu, phong cách và dịp dùng."))
    score = raw * 100 if pct is None else pct
    res = AxisResult(score=score, features={"raw": raw, "n_tags": len(inp.tags)}, issues=issues)
    return res, verdicts, suggestions


def trend_axis(h: float, ms: list, feats: dict, peer_h: list[float]) -> AxisResult:
    pct = percentile(h, peer_h)
    score = (h - LO) / (HI - LO) * 100 if pct is None else pct
    issues = [] if ms else [issue("no_trend_keyword", "Tiêu đề chưa chứa từ khoá nào đang được tìm kiếm nhiều.")]
    metrics = {"demand_factor": h, "matches": len(ms), "momentum_max": feats.get("trend_momentum_max")}
    return AxisResult(score=score, features=metrics, issues=issues)


def keywords(inp, ms, ctx) -> list[dict]:
    table = ctx.lift.get(inp.group) or {}
    title = f" {fold(inp.title)} "
    out = {}
    for k, _ in ms:
        out[k] = {"term": k, "lift": table.get(norm(k)), "trend": direction(momentum(ctx.trend_series[k], ctx.at)),
                  "in_title": f" {fold(k)} " in title}
    for g in sorted({g for g in ngrams(inp.title) if g in table}, key=lambda g: -abs(table[g])):
        out.setdefault(g, {"term": g, "lift": table[g], "trend": None, "in_title": True})
    return list(out.values())[:MAX_KEYWORDS]
