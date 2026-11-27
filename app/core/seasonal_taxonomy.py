"""Bộ điều phối Gợi ý Mùa vụ Thông minh (Hybrid Engine):
Kết hợp Tầng 1 (Data-Mining từ MongoDB) và Tầng 2 (Generative AI / LLM).
HOÀN TOÀN KHÔNG DÙNG TỪ ĐIỂN FIX CỨNG.
"""

import time
from typing import Any, Dict, Optional
from app.services.market_mining_service import MarketMiningService
from app.services.llm_seasonal_service import LLMSeasonalService


_CACHE: Dict[str, Dict[str, Any]] = {}
_FALLBACK_TTL_S = 6 * 3600
_FALLBACK_CACHE: Dict[str, Any] = {}


def get_seasonal_suggestions(
    keyword: str,
    category_slug: Optional[str] = None,
    use_llm: bool = True,
) -> Dict[str, Any]:
    """Quy trình 2 tầng Hybrid có cache bộ nhớ khi đã có kết quả từ AI.

    `use_llm=False`: chỉ tổng hợp từ dữ liệu sàn (không tốn lượt gọi LLM), cache 6 giờ.
    """
    cache_key = f"{keyword}:{category_slug or ''}"
    if cache_key in _CACHE:
        return _CACHE[cache_key]
    if not use_llm:
        hit = _FALLBACK_CACHE.get(cache_key)
        if hit and hit[0] > time.time():
            return hit[1]

    # Tầng 1: Khai phá dữ liệu số thực tế từ sàn
    mined_data = MarketMiningService.mine_seasonal_cluster(keyword, category_slug)

    # Tầng 2: Suy luận gợi ý sản phẩm cụ thể qua AI
    recommendations = LLMSeasonalService.generate_recommendations(keyword, category_slug, mined_data, use_llm=use_llm)

    # Chỉ cache nếu đã sinh từ AI thực thụ thành công (không cache fallback)
    ai_model = recommendations.get("ai_model", "")
    if ai_model and not ai_model.startswith("VietCraft Market Mining"):
        _CACHE[cache_key] = recommendations
    elif not use_llm:
        _FALLBACK_CACHE[cache_key] = (time.time() + _FALLBACK_TTL_S, recommendations)

    return recommendations


def clear_seasonal_cache() -> None:
    """Xóa bộ nhớ đệm gợi ý mùa vụ."""
    _CACHE.clear()
    _FALLBACK_CACHE.clear()
