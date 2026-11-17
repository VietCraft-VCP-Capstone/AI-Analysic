"""
F42 Market Aggregator: dữ liệu sàn VietCraft + từ khóa tìm kiếm Google.

1. Sản phẩm tương tự đang bán trên chính sàn (products + giá thật từ product_variants).
2. Từ khóa liên quan:
   - "google_suggest": gợi ý tự động của Google (suggestqueries) — CHỈ là gợi ý gõ phím,
     không có số liệu tăng trưởng, không được gọi là "Google Trends".
   - "google_trends": từ khóa trong collection trend_keyword / trend_related do
     app/collectors/collect_trends.py thu thập từ Google Trends.

Không còn bảng giá gõ tay theo thương hiệu: mọi mức giá phải đến từ dữ liệu thật
hoặc từ giá vốn seller nhập (spec F42 mục 0.3).
"""

import json
import logging
import re
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Tuple

from app.services.f42 import config
from app.services.f42.pricing_engine import fetch_live_listings, round_price, _percentile
from app.services.f42.vi_text import clean_tokens, normalize_nfc

logger = logging.getLogger(__name__)

# Từ không mang nghĩa loại sản phẩm, bỏ khi dựng truy vấn tìm sản phẩm tương tự
_QUERY_STOPWORDS = {
    "cho", "của", "và", "với", "các", "những", "một", "cái", "chiếc", "bộ", "set", "combo",
    "hàng", "mới", "new", "hot", "sale", "giá", "rẻ", "đẹp", "cao", "cấp", "loại", "mẫu",
    "in", "hình", "theo", "yêu", "cầu", "size", "free", "nam", "nữ",
}


def _query_tokens(title: str) -> List[str]:
    toks = [t for t in clean_tokens(title) if len(t) >= 2 and t not in _QUERY_STOPWORDS and not t.isdigit()]
    return list(dict.fromkeys(toks))


def _title_filter(tokens: List[str]) -> Dict[str, Any]:
    """Mọi token đều phải xuất hiện trong tiêu đề (AND), tránh khớp lỏng 1 từ."""
    return {"$and": [{"title": {"$regex": re.escape(t), "$options": "i"}} for t in tokens]}


class MarketDataAggregator:
    """Bộ thu thập & kết hợp dữ liệu sàn VietCraft + từ khóa tìm kiếm Google."""

    @classmethod
    def fetch_internal_platform_data(
        cls,
        title: str,
        category_name: str,
        db_live: Any,
        cfg=config,
    ) -> Dict[str, Any]:
        """Sản phẩm tương tự đang bán trên sàn VietCraft, mỗi sản phẩm một giá."""
        result: Dict[str, Any] = {
            "found_count": 0,
            "prices": [],
            "p25": 0,
            "p50": 0,
            "p75": 0,
            "sample_titles": [],
            "comparables": [],
            "common_tags": [],
            "summary_text": "Chưa có sản phẩm tương tự trên sàn VietCraft.",
        }
        if db_live is None or not (title or category_name):
            return result

        tokens = _query_tokens(title)
        rows: List[Dict[str, Any]] = []
        try:
            if tokens:
                # Thu hẹp dần: 3 từ đầu → 2 từ đầu. Không nới về 1 từ vì dễ khớp nhầm ngành hàng.
                for n in range(min(cfg.INTERNAL_MATCH_TOKENS, len(tokens)), max(1, min(2, len(tokens))) - 1, -1):
                    rows = fetch_live_listings(db_live, _title_filter(tokens[:n]), limit=60)
                    if len(rows) >= cfg.MIN_SAMPLE_LOW or n <= 2:
                        break
            elif category_name:
                rows = fetch_live_listings(
                    db_live, {"categories": {"$regex": re.escape(category_name), "$options": "i"}}, limit=60
                )
        except Exception as exc:
            logger.warning("f42.internal_platform_failed", extra={"error": str(exc)})
            return result

        prices = sorted(r["price"] for r in rows)
        tags_counter: Dict[str, int] = {}
        for r in rows:
            for tag in r["tags"]:
                tag = tag.strip()
                if len(tag) >= 2:
                    tags_counter[tag] = tags_counter.get(tag, 0) + 1

        result["sample_titles"] = [r["title"] for r in rows[:5]]
        result["comparables"] = [
            {"title": r["title"], "price": int(round(r["price"])), "similarity": None, "source": "Sàn VietCraft"}
            for r in rows[:6]
        ]
        result["common_tags"] = [k for k, _ in sorted(tags_counter.items(), key=lambda kv: kv[1], reverse=True)[:8]]

        if len(prices) >= cfg.MIN_SAMPLE_LOW:
            p25 = round_price(_percentile(prices, 0.25))
            p50 = round_price(_percentile(prices, 0.50))
            p75 = round_price(_percentile(prices, 0.75))
            result.update(
                found_count=len(prices), prices=prices, p25=p25, p50=p50, p75=p75,
                summary_text=(
                    f"{len(prices)} sản phẩm tương tự đang bán trên sàn VietCraft: "
                    f"P25 {p25:,}đ, P50 {p50:,}đ, P75 {p75:,}đ."
                ),
            )
        elif prices:
            result.update(
                found_count=len(prices), prices=prices,
                summary_text=f"Chỉ có {len(prices)} sản phẩm tương tự trên sàn VietCraft, chưa đủ để tính phân vị.",
            )
        return result

    @classmethod
    def fetch_google_trending_data(
        cls,
        query: str,
        category_name: str = "",
        db_data: Any = None,
        cfg=config,
    ) -> Dict[str, Any]:
        """
        Từ khóa liên quan tới sản phẩm. Trả riêng hai nguồn để FE ghi nhãn đúng:
        - suggest_keywords: Google Suggest (gợi ý gõ phím, không có số liệu xu hướng)
        - trend_keywords: dữ liệu Google Trends đã thu thập trong DB
        """
        result: Dict[str, Any] = {
            "suggest_keywords": [],
            "trend_keywords": [],
            "trending_keywords": [],  # giữ tên cũ = hợp của hai nguồn
            "search_signals": [],
            "summary_text": "",
        }
        clean_q = normalize_nfc(query or "").strip()
        if not clean_q:
            return result

        suggest: List[str] = []
        if cfg.GOOGLE_SUGGEST_ENABLED:
            try:
                url = (
                    "https://suggestqueries.google.com/complete/search?client=firefox&hl=vi&gl=vn&q="
                    + urllib.parse.quote_plus(clean_q)
                )
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=cfg.GOOGLE_SUGGEST_TIMEOUT_S) as resp:
                    if resp.status == 200:
                        data = json.loads(resp.read().decode("utf-8"))
                        if isinstance(data, list) and len(data) >= 2 and isinstance(data[1], list):
                            for item in data[1]:
                                kw = normalize_nfc(str(item)).strip()
                                if kw and kw.lower() != clean_q.lower() and kw not in suggest:
                                    suggest.append(kw)
            except Exception as exc:
                logger.debug("f42.google_suggest_unavailable", extra={"error": str(exc)})

        trends: List[str] = []
        if db_data is not None:
            try:
                for t in clean_tokens(clean_q):
                    if len(t) < 3:
                        continue
                    for k in db_data["trend_keyword"].find(
                        {"keyword": {"$regex": re.escape(t), "$options": "i"}}, {"keyword": 1}
                    ).limit(5):
                        kw = str(k.get("keyword", "")).strip()
                        if kw and kw not in trends:
                            trends.append(kw)
                    for r in db_data["trend_related"].find(
                        {"query": {"$regex": re.escape(t), "$options": "i"}}, {"query": 1}
                    ).limit(3):
                        rq = str(r.get("query") or "").strip()
                        if rq and rq not in trends:
                            trends.append(rq)
            except Exception as exc:
                logger.debug("f42.trend_db_unavailable", extra={"error": str(exc)})

        merged = list(dict.fromkeys(trends + suggest))
        result["suggest_keywords"] = suggest[:10]
        result["trend_keywords"] = trends[:10]
        result["trending_keywords"] = merged[:10]

        # Chỉ mô tả điều quan sát được trong chuỗi gợi ý, không suy ra "nhu cầu cao".
        low = " ".join(suggest).lower()
        if "giá" in low:
            result["search_signals"].append("Gợi ý tìm kiếm Google có các cụm hỏi về giá")
        if "màu" in low:
            result["search_signals"].append("Gợi ý tìm kiếm Google có các cụm về màu sắc")

        parts = []
        if trends:
            parts.append("Từ khóa Google Trends đã thu thập: " + ", ".join(f'"{k}"' for k in trends[:3]))
        if suggest:
            parts.append("Gợi ý tìm kiếm Google liên quan: " + ", ".join(f'"{k}"' for k in suggest[:3]))
        result["summary_text"] = ". ".join(parts) + ("." if parts else "")
        return result

    @classmethod
    def deduce_optimal_pricing(
        cls,
        title: str,
        category_name: str,
        internal_data: Dict[str, Any],
        google_trends: Dict[str, Any],
        blank_cost: float = 0.0,
        target_margin: float = None,
        cfg=config,
    ) -> Tuple[int, int, int, str]:
        """
        Giữ lại cho tương thích. Thứ tự: phân vị sản phẩm tương tự trên sàn → Cost-Plus → không gợi ý.
        Đã bỏ bảng giá thương hiệu gõ tay (ốp lưng iPhone từng bị định giá 34.990.000đ).
        """
        if internal_data.get("p50", 0) > 0:
            p25, p50, p75 = internal_data["p25"], internal_data["p50"], internal_data["p75"]
            return p25, p50, p75, (
                f"Định giá dựa trên {internal_data['found_count']} sản phẩm tương tự đang bán trên sàn VietCraft. "
                f"Khoảng giá phổ biến {p25:,}đ – {p75:,}đ, mức giữa {p50:,}đ."
            )
        if blank_cost > 0:
            margin = target_margin if target_margin else cfg.DEFAULT_TARGET_MARGIN
            p50 = round_price(blank_cost * (1 + margin))
            p25 = round_price(blank_cost * cfg.COST_FLOOR_RATIO)
            p75 = round_price(blank_cost * (1 + margin * 1.5))
            return p25, p50, p75, (
                f"Định giá theo giá vốn (Cost-Plus {int(margin * 100)}%) từ {int(blank_cost):,}đ."
            )
        return 0, 0, 0, "Chưa đủ dữ liệu thị trường để đề xuất mức giá."
