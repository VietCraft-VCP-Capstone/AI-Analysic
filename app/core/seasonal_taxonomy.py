"""Bộ điều phối Gợi ý Mùa vụ Thông minh (Hybrid Engine):
Kết hợp Tầng 1 (Data-Mining từ MongoDB) và Tầng 2 (Generative AI / LLM).
HOÀN TOÀN KHÔNG DÙNG TỪ ĐIỂN FIX CỨNG.
"""

from functools import lru_cache
from typing import Any, Dict, Optional
from app.services.market_mining_service import MarketMiningService
from app.services.llm_seasonal_service import LLMSeasonalService


_CACHE: Dict[str, Dict[str, Any]] = {}


def get_seasonal_suggestions(
    keyword: str,
    category_slug: Optional[str] = None
) -> Dict[str, Any]:
    """Quy trình 2 tầng Hybrid có cache bộ nhớ khi đã có kết quả từ AI."""
    cache_key = f"{keyword}:{category_slug or ''}"
    if cache_key in _CACHE:
        return _CACHE[cache_key]

    # Tầng 1: Khai phá dữ liệu số thực tế từ sàn
    mined_data = MarketMiningService.mine_seasonal_cluster(keyword, category_slug)

    # Tầng 2: Suy luận gợi ý sản phẩm cụ thể qua AI
    recommendations = LLMSeasonalService.generate_recommendations(keyword, category_slug, mined_data)

    # Chỉ cache nếu đã sinh từ AI thành công
    if recommendations.get("ai_model"):
        _CACHE[cache_key] = recommendations

    return recommendations
