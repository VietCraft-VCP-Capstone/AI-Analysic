"""
Tín hiệu nhu cầu từ Google Trends cho gợi ý giá.

Google Trends KHÔNG có giá. Nó chỉ cho biết mức quan tâm tìm kiếm đang lên hay xuống, nên chỉ
được dùng để dịch giá đề xuất BÊN TRONG khoảng giá thị trường thật (P25–P75), không bao giờ
đẩy giá ra ngoài khoảng đó:
  - nhu cầu 4 tuần gần nhất cao hơn 8 tuần trước đó >= 20%  → nhích về giữa P50 và P75;
  - thấp hơn >= 20%                                         → nhích về giữa P25 và P50;
  - còn lại                                                 → giữ P50.
Dữ liệu lấy từ trend_interest (daily) do app/collectors/collect_trends.py thu thập hằng ngày.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from app.services.f42.vi_text import clean_tokens, strip_accents

RECENT_DAYS = 28
PREVIOUS_DAYS = 56
MIN_POINTS = 60          # đủ ~2/3 số ngày của 12 tuần mới tính
MIN_PREV_MEAN = 5.0      # từ khoá quá ít người tìm (thang 0–100) thì tỉ lệ chỉ là nhiễu
UP, DOWN = 1.20, 0.80


def _key(text: str) -> List[str]:
    return [strip_accents(t) for t in clean_tokens(text)]


def match_keyword(query: str, keywords: List[str]) -> Optional[str]:
    """
    Từ khoá Trends dài nhất xuất hiện NGUYÊN CỤM liền nhau trong tiêu đề. Chỉ cần đủ từ (không liền)
    thì "Áo thun cotton in hình" bị khớp nhầm với "in áo thun" (dịch vụ in áo).
    """
    q = f" {' '.join(_key(query))} "
    best = None
    for kw in keywords:
        toks = _key(kw)
        if toks and f" {' '.join(toks)} " in q and (best is None or len(toks) > len(_key(best))):
            best = kw
    return best


def momentum_from_series(points: List[Dict[str, Any]], today: datetime) -> Optional[Dict[str, float]]:
    """Tỉ lệ trung bình 28 ngày gần nhất / 56 ngày trước đó. None nếu dữ liệu thưa hoặc quá ít người tìm."""
    if len(points) < MIN_POINTS:
        return None
    cut = today - timedelta(days=RECENT_DAYS)
    start = cut - timedelta(days=PREVIOUS_DAYS)
    recent = [float(p["scaled"]) for p in points if p["observed_on"] >= cut]
    prev = [float(p["scaled"]) for p in points if start <= p["observed_on"] < cut]
    if not recent or not prev:
        return None
    prev_mean = sum(prev) / len(prev)
    if prev_mean < MIN_PREV_MEAN:
        return None
    recent_mean = sum(recent) / len(recent)
    return {"recent_mean": round(recent_mean, 1), "prev_mean": round(prev_mean, 1),
            "momentum": round(recent_mean / prev_mean, 2)}


def demand_signal(db_data: Any, query: str, today: Optional[datetime] = None) -> Optional[Dict[str, Any]]:
    """Tín hiệu nhu cầu cho tiêu đề seller nhập, hoặc None nếu không có từ khoá Trends phù hợp/đủ dữ liệu."""
    if db_data is None or not query:
        return None
    try:
        keywords = [d["keyword"] for d in db_data["trend_keyword"].find({}, {"keyword": 1}) if d.get("keyword")]
        kw = match_keyword(query, keywords)
        if not kw:
            return None
        today = today or datetime.now(timezone.utc).replace(tzinfo=None)
        since = today - timedelta(days=RECENT_DAYS + PREVIOUS_DAYS)
        points = list(db_data["trend_interest"].find(
            {"keyword": kw, "granularity": "daily", "geo": "VN", "observed_on": {"$gte": since}},
            {"observed_on": 1, "scaled": 1, "_id": 0},
        ))
        m = momentum_from_series(points, today)
        return {"keyword": kw, **m} if m else None
    except Exception:  # noqa: BLE001 — thiếu tín hiệu thì giữ P50, không làm hỏng gợi ý
        return None


def apply_demand(p25: int, p50: int, p75: int, signal: Optional[Dict[str, Any]], round_fn) -> Dict[str, Any]:
    """Giá đề xuất sau khi xét nhu cầu, luôn nằm trong [p25, p75]."""
    if not signal or not (p25 <= p50 <= p75):
        return {"price": p50, "direction": "flat", "note": ""}
    m = signal["momentum"]
    pct = int(round(abs(m - 1) * 100))
    if m >= UP:
        price = round_fn((p50 + p75) / 2)
        note = (f" Nhu cầu tìm kiếm \"{signal['keyword']}\" trên Google Trends 4 tuần gần đây tăng {pct}% so với "
                f"8 tuần trước nên giá đề xuất nhích về phía trên khoảng giá.")
        direction = "up"
    elif m <= DOWN:
        price = round_fn((p25 + p50) / 2)
        note = (f" Nhu cầu tìm kiếm \"{signal['keyword']}\" trên Google Trends 4 tuần gần đây giảm {pct}% so với "
                f"8 tuần trước nên giá đề xuất nhích về phía dưới khoảng giá để dễ bán.")
        direction = "down"
    else:
        return {"price": p50, "direction": "flat",
                "note": f" Nhu cầu tìm kiếm \"{signal['keyword']}\" trên Google Trends đang ổn định."}
    return {"price": min(max(price, p25), p75), "direction": direction, "note": note}
