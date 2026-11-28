"""Danh sách từ khóa ứng viên cho bảng "Từ khóa cơ hội" của Seasonal, gom từ dữ liệu thu thật.

Trước đây bảng chỉ lấy từ catalog thu một lần cộng danh sách viết sẵn, nên mùa nào cũng như nhau.
Giờ ứng viên đến từ các nguồn được thu định kỳ, mỗi từ khóa ghi lại vì sao nó có mặt (`origins`):

- catalog_occasion: sản phẩm đang bán trên Tiki/Etsy/Printify gắn đúng dịp (thu hằng ngày)
- trends_seasonal: từ khóa Google Trends có lượt tìm tăng mạnh đúng dịp này ở các năm trước
- trends_rising: truy vấn liên quan đang tăng trên Google (thu hằng tuần)
- onsite_search: người dùng VietCraft đang tìm trong 30 ngày gần nhất
- market_crawl: từ khóa crawler giá F42 đang theo dõi trên Tiki/Etsy (2 lần/ngày)
- occasion_seed: từ khóa chuẩn của dịp (luôn có để bảng không trống)
- catalog_general: từ khóa bán chạy của ngành, chỉ để lấp chỗ trống
"""
from __future__ import annotations

import hashlib
import re
from datetime import date
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

import pandas as pd

GENERIC_WORDS: Set[str] = {
    "quà", "tặng", "áo", "trang", "trí", "cho", "set", "bộ", "hộp", "in", "thun", "mẫu", "đồ",
    "phông", "nam", "nữ", "sản", "phẩm", "mua", "và", "của", "dịp", "mùa",
}
MIN_TERM_LEN = 4
MIN_ONSITE_SEARCHES = 3
SEASONAL_LIFT_MIN = 1.5
MIN_WINDOW_LEVEL = 5.0  # dưới mức này chuỗi Trends quá thưa, tỷ lệ tăng chỉ là nhiễu

ORIGIN_LABELS: Dict[str, str] = {
    "catalog_occasion": "Đang bán đúng dịp trên sàn khác",
    "trends_seasonal": "Google Trends tăng mạnh đúng dịp các năm trước",
    "trends_rising": "Truy vấn đang tăng trên Google",
    "onsite_search": "Người dùng VietCraft đang tìm",
    "market_crawl": "Đang theo dõi giá trên Tiki/Etsy",
    "occasion_seed": "Từ khóa chuẩn của dịp",
    "catalog_general": "Bán chạy trong ngành",
}


# Tên gọi đặc trưng của từng dịp, dùng để nhận ra từ khóa thuộc dịp nào (không phải số liệu)
OCCASION_MARKERS: Dict[str, List[str]] = {
    "tet_duong_lich": ["năm mới", "tết dương"],
    "tet": ["tết", "lì xì", "xuân"],
    "valentine": ["valentine", "14/2", "14 2"],
    "8/3": ["8/3", "8 3", "phụ nữ"],
    "30/4": ["30/4", "30 4", "đi biển"],
    "ngay_cua_me": ["ngày của mẹ"],
    "1/6": ["1/6", "thiếu nhi"],
    "ngay_cua_cha": ["ngày của cha"],
    "khai_giang": ["khai giảng", "tựu trường"],
    "trung_thu": ["trung thu"],
    "20/10": ["20/10", "20 10", "phụ nữ"],
    "halloween": ["halloween"],
    "20/11": ["20/11", "20 11", "thầy cô", "nhà giáo"],
    "noel": ["noel", "giáng sinh", "christmas"],
}


def occasion_markers(camp_id: str) -> Set[str]:
    return set(OCCASION_MARKERS.get(camp_id, []))


def foreign_markers(camp_id: str) -> Set[str]:
    ours = occasion_markers(camp_id)
    return {m for k, ms in OCCASION_MARKERS.items() if k != camp_id for m in ms} - ours


def normalize_kw(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


def stable_id(prefix: str, camp_id: str, text: str) -> str:
    """ID theo nội dung (không theo vị trí) để ý tưởng/từ khóa đã lưu không bị trỏ nhầm khi danh sách đổi."""
    camp = re.sub(r"[^a-z0-9_-]", "-", normalize_kw(camp_id))
    digest = hashlib.sha1(normalize_kw(text).encode("utf-8")).hexdigest()[:10]
    return f"{prefix}_{camp}_{digest}"


def occasion_terms(seeds: Iterable[str]) -> Set[str]:
    """Cụm từ đặc trưng của dịp (bỏ chữ chung như "quà", "áo") dùng để lọc truy vấn liên quan."""
    terms: Set[str] = set()
    for seed in seeds:
        s = normalize_kw(seed)
        tokens = s.split()
        distinct = [t for t in tokens if t not in GENERIC_WORDS]
        if not distinct:
            continue
        core = " ".join(distinct)
        if len(core) >= MIN_TERM_LEN:
            terms.add(core)
        else:
            terms.add(s)  # vd "quà 8/3": phần riêng quá ngắn thì giữ cả cụm
    return terms


def is_relevant(query: str, terms: Set[str]) -> bool:
    q = normalize_kw(query)
    return any(t in q for t in terms)


def seasonal_lift(series: pd.Series, past_event_dates: Sequence[date], window_days: int = 28) -> Optional[float]:
    """Lượt tìm trung bình trong `window_days` trước lễ so với trung bình cả năm, lấy trung bình qua các năm."""
    if series is None or len(series) == 0:
        return None
    ratios: List[float] = []
    for d in past_event_dates:
        end = pd.Timestamp(d)
        win = series[(series.index >= end - pd.Timedelta(days=window_days)) & (series.index <= end)]
        year = series[(series.index > end - pd.Timedelta(days=365)) & (series.index <= end)]
        if len(win) == 0 or len(year) < 26 or float(year.mean()) <= 0 or float(win.mean()) < MIN_WINDOW_LEVEL:
            continue
        ratios.append(float(win.mean()) / float(year.mean()))
    return sum(ratios) / len(ratios) if ratios else None


def seasonal_trend_keywords(series_by_kw: Dict[str, pd.Series], past_event_dates: Sequence[date],
                            min_lift: float = SEASONAL_LIFT_MIN) -> List[Tuple[str, float]]:
    """Từ khóa Trends đang theo dõi có lượt tìm tăng rõ đúng dịp, xếp theo mức tăng."""
    out: List[Tuple[str, float]] = []
    for kw, s in (series_by_kw or {}).items():
        lift = seasonal_lift(s, past_event_dates)
        if lift is not None and lift >= min_lift:
            out.append((normalize_kw(kw), round(lift, 2)))
    return sorted(out, key=lambda x: -x[1])


def build_keyword_pool(
    *,
    terms: Set[str],
    foreign_terms: Set[str] = frozenset(),
    catalog_occasion: Sequence[str],
    seeds: Sequence[str],
    seasonal_trends: Sequence[str],
    rising_related: Sequence[str],
    onsite_queries: Sequence[Tuple[str, int]],
    f42_keywords: Sequence[str],
    catalog_general: Sequence[str],
    limit: int = 15,
) -> List[Dict[str, Any]]:
    """
    Gom ứng viên theo thứ tự ưu tiên nguồn, khử trùng, ghi lại mọi nguồn chứa từ khóa.
    Từ khóa của dịp khác (vd "lì xì tết" khi xem Noel) bị loại, trừ khi nằm trong catalog gắn đúng dịp hoặc là từ khóa chuẩn của dịp.
    """
    pool: Dict[str, Dict[str, Any]] = {}

    def add(tag: str, origin: str, *, may_open: bool = True) -> None:
        t = normalize_kw(tag)
        if len(t) < 3:
            return
        trusted = origin in ("catalog_occasion", "occasion_seed")
        if not trusted and foreign_terms and is_relevant(t, set(foreign_terms)) and not is_relevant(t, terms):
            return
        if t in pool:
            if origin not in pool[t]["origins"]:
                pool[t]["origins"].append(origin)
            return
        if may_open and len(pool) < limit:
            pool[t] = {"tag": t, "origins": [origin]}

    for t in catalog_occasion:
        add(t, "catalog_occasion")
    for t in seasonal_trends:
        add(t, "trends_seasonal")
    for t in rising_related:
        if is_relevant(t, terms):
            add(t, "trends_rising")
    for q, n in onsite_queries:
        if n >= MIN_ONSITE_SEARCHES and is_relevant(q, terms):
            add(q, "onsite_search")
    for t in f42_keywords:
        if is_relevant(t, terms):
            add(t, "market_crawl")
    for t in seeds:
        add(t, "occasion_seed")
    for t in catalog_general:
        add(t, "catalog_general")
    return list(pool.values())


def f42_signals_for(tag: str, listings: Sequence[Dict[str, Any]], skip_ids: Set[str]) -> Dict[str, Any]:
    """Tín hiệu bán thật của một từ khóa từ crawler F42 (`market_price_listing`)."""
    t = normalize_kw(tag)
    out: Dict[str, Any] = {"tiki_hits": 0, "tiki_sold": 0, "etsy_hits": 0, "etsy_reviews": 0, "prices": [], "ids": []}
    for ml in listings:
        ml_id = str(ml.get("_id") or ml.get("external_id") or "")
        if ml_id and ml_id in skip_ids:
            continue
        kws = {normalize_kw(k) for k in (ml.get("keywords") or [])}
        if ml.get("keyword"):
            kws.add(normalize_kw(ml["keyword"]))
        title = normalize_kw(ml.get("title") or "")
        if t not in kws and not (len(t) >= MIN_TERM_LEN and t in title):
            continue
        src = str(ml.get("source") or "").lower()
        if src == "etsy":
            out["etsy_hits"] += 1
            out["etsy_reviews"] += int(ml.get("review_count") or 0)
        else:
            out["tiki_hits"] += 1
            out["tiki_sold"] += int(ml.get("sold") or 0)
        price = int(ml.get("price") or 0)
        if price > 0:
            out["prices"].append(price)
        if ml_id:
            out["ids"].append(ml_id)
    return out
