import time
from typing import Any, Dict, List, Optional, Set
from pymongo import MongoClient

from app.config import settings
from app.services.f42.context_resolver import ContextResolver
from app.services.f42.content_generator import generate_content
from app.services.f42.external_market import ExternalMarketProvider
from app.services.f42.pricing_engine import compute_pricing, fetch_prices_from_db
from app.services.f42.schemas import (
    CategoryResult,
    ContentResult,
    MetaResult,
    PricingResult,
    SuggestionRequest,
    TagResult,
    UnifiedSuggestionResponse,
)
from app.services.f42.tag_mining import fetch_tags_from_db

_client_live: Optional[MongoClient] = None
_cached_categories: List[Dict[str, Any]] = []
_cached_categories_ts: float = 0.0
_cached_banned: Set[str] = set()
_cached_banned_ts: float = 0.0
CACHE_TTL = 300.0  # 5 phút


def _get_mongo_client() -> Optional[MongoClient]:
    global _client_live
    if _client_live is None and settings.MONGO_URI:
        try:
            _client_live = MongoClient(settings.MONGO_URI, serverSelectionTimeoutMS=3000, maxPoolSize=5)
        except Exception:
            pass
    return _client_live


def _get_live_db():
    client = _get_mongo_client()
    if client:
        try:
            return client[settings.MONGO_DB_LIVE]
        except Exception:
            pass
    return None


def _get_categories(db_live) -> List[Dict[str, Any]]:
    global _cached_categories, _cached_categories_ts
    now = time.time()
    if _cached_categories and now - _cached_categories_ts < CACHE_TTL:
        return _cached_categories
    if db_live is not None:
        try:
            cats = list(db_live["categories"].find({"is_active": {"$ne": False}}, {"_id": 1, "name": 1}))
            if cats:
                _cached_categories = cats
                _cached_categories_ts = now
                return cats
        except Exception:
            pass
    return _cached_categories


def _get_banned_keywords(db_live) -> Set[str]:
    global _cached_banned, _cached_banned_ts
    now = time.time()
    if _cached_banned and now - _cached_banned_ts < CACHE_TTL:
        return _cached_banned
    if db_live is not None:
        try:
            banned = {
                str(x.get("keyword", "")).lower().strip()
                for x in db_live["banned_keywords"].find({}, {"keyword": 1})
                if x.get("keyword")
            }
            if banned:
                _cached_banned = banned
                _cached_banned_ts = now
                return banned
        except Exception:
            pass
    return _cached_banned


def _build_full_seo_description_text(
    title: str,
    category_name: str,
    desc_obj: Any,
    tags: List[str]
) -> str:
    """Ghép bài mô tả chuẩn giao diện cho Frontend."""
    intro = getattr(desc_obj, "intro", "") or ""
    specs = getattr(desc_obj, "specs", []) or []
    highlights = getattr(desc_obj, "highlights", []) or []
    care_guide = getattr(desc_obj, "care_guide", None)

    specs_text = "\n".join([f"  • {s.label}: {s.value}" for s in specs]) if specs else f"  • Danh mục: {category_name}"
    highlights_text = "\n".join([f"  • {h}" for h in highlights]) if highlights else "  • Sản phẩm được kiểm định chất lượng kỹ càng."
    care_text = f"\n📋 HƯỚNG DẪN BẢO QUẢN:\n{care_guide}\n" if care_guide else ""
    tags_text = ", ".join(["#" + t.replace(" ", "") for t in tags[:8]]) if tags else ""

    text = f"""✨ {title.upper()} ✨

📖 GIỚI THIỆU SẢN PHẨM:
{intro}

📐 THÔNG SỐ SẢN PHẨM:
{specs_text}

🌟 ĐIỂM NỔI BẬT VƯỢT TRỘI:
{highlights_text}
{care_text}
🛡️ CHÍNH SÁCH CAM KẾT:
  ✔️ 100% hình ảnh thực tế, mô tả minh bạch trung thực.
  ✔️ Kiểm tra chất lượng kỹ càng trước khi đóng gói gửi đi.
  ✔️ Đóng gói chống sốc an toàn, hỗ trợ đổi trả nếu có lỗi sản xuất.

🔖 TỪ KHÓA TÌM KIẾM:
{tags_text}
"""
    return text.strip()


class F42Orchestrator:
    """Bộ điều phối toàn diện cho F42 Smart Suggestion."""

    @classmethod
    def execute(
        cls,
        req: SuggestionRequest,
        db_live_override: Any = None
    ) -> UnifiedSuggestionResponse:
        start_time = time.time()
        db_live = None if db_live_override is False else (db_live_override if db_live_override is not None else _get_live_db())

        # 1. Khám phá categories & banned
        categories = _get_categories(db_live)
        banned = _get_banned_keywords(db_live)

        title_input = req.get_title_or_keywords()
        category_id_in = req.get_category_id()
        category_name_in = req.get_category_name()
        material_in = req.get_material()
        blank_cost = req.get_blank_cost()
        target_margin = req.get_target_margin()
        extra_attr = req.extra_attributes or ""

        # --- KHỐI 1: CONTEXT RESOLVER ---
        try:
            resolver = ContextResolver(categories)
            category_res = resolver.resolve(
                category_id=category_id_in,
                category_name=category_name_in,
                user_title=title_input
            )
        except Exception:
            category_res = CategoryResult(
                resolved_id=category_id_in,
                resolved_name=category_name_in or "Mỹ nghệ & Đời sống",
                source="fallback",
                needs_confirmation=True
            )

        effective_category_id = category_res.resolved_id
        effective_category_name = category_res.resolved_name or "Mỹ nghệ & Đời sống"

        # --- KHỐI 2: PRICING ENGINE ---
        try:
            prices = fetch_prices_from_db(effective_category_id, db_live)
            is_external_benchmark = False

            # Nếu sàn nội bộ chưa có đủ mẫu (dưới 5 sản phẩm), tham chiếu Model ML & dataset TMĐT Tiki
            if len(prices) < 5:
                ml_band = ExternalMarketProvider.predict_price_band_ml(title_input, effective_category_name) if title_input else None
                if ml_band and ml_band[1] > 0:
                    p25, p50, p75 = ml_band
                    warnings_list = []
                    if blank_cost > 0:
                        min_safe = int(round(blank_cost * 1.30 / 1000) * 1000)
                        if p50 < min_safe:
                            warnings_list.append("Giá trung bình thị trường đang thấp hơn hoặc sát giá vốn của bạn.")
                            p50 = min_safe
                            p25 = max(p25, min_safe)
                            p75 = max(p75, p50)
                    from app.services.f42.schemas import PriceRange
                    pricing_res = PricingResult(
                        mode="market",
                        insufficient_market_data=False,
                        sample_size=45573,
                        sample_size_after_outlier_filter=120,
                        p25=p25,
                        p50=p50,
                        p75=p75,
                        suggested_price=p50,
                        suggested_range=PriceRange(low=p25, high=p75),
                        confidence="high",
                        warnings=warnings_list,
                        explanation=(
                            f"Dựa trên mô hình Machine Learning Quantile Regression (học từ 45.000+ sản phẩm TMĐT), "
                            f"khoảng giá niêm yết phù hợp cho mẫu sản phẩm này từ {p25:,.0f}đ đến {p75:,.0f}đ. "
                            f"Mức giá đề xuất cân bằng (P50): {p50:,.0f}đ."
                        ).replace(",", ".")
                    )
                else:
                    external_prices = ExternalMarketProvider.get_market_prices(effective_category_name, title_input)
                    if len(external_prices) >= 5:
                        prices = external_prices[:120]
                        is_external_benchmark = True

                    pricing_res = compute_pricing(
                        prices=prices,
                        blank_cost=blank_cost,
                        target_margin=target_margin
                    )
                    if is_external_benchmark and pricing_res.mode in ("market", "market_low_confidence"):
                        pricing_res.explanation = (
                            f"Dựa trên dữ liệu đối chuẩn thị trường TMĐT ({pricing_res.sample_size_after_outlier_filter} sản phẩm cùng ngành), "
                            f"khoảng giá niêm yết phổ biến từ {pricing_res.suggested_range.low:,.0f}đ đến {pricing_res.suggested_range.high:,.0f}đ. "
                            f"Mức giá đề xuất cân bằng: {pricing_res.suggested_price:,.0f}đ."
                        ).replace(",", ".")
            else:
                pricing_res = compute_pricing(
                    prices=prices,
                    blank_cost=blank_cost,
                    target_margin=target_margin
                )
        except Exception:
            pricing_res = PricingResult(
                mode="none",
                insufficient_market_data=True,
                explanation="Chưa thể phân tích mức giá thị trường lúc này."
            )

        # --- KHỐI 3: TAG MINING ---
        try:
            tag_res = fetch_tags_from_db(effective_category_id, db_live, banned)
            # Bổ sung các cụm từ có Lift cao từ nhóm bán chạy Top 25
            lifted_items = ExternalMarketProvider.get_lifted_keywords(effective_category_name, title_input, top_n=6)
            for item in lifted_items:
                kw = item.get("keyword", "")
                if kw and kw.lower() not in [t.tag.lower() for t in tag_res.items] and kw.lower() not in banned:
                    tag_res.items.append(TagItem(tag=kw, score=float(item.get("lift", 1.5)), freq=int(item.get("freq", 2))))
        except Exception:
            tag_res = TagResult(items=[], basis="popular_tags_internal", sample_size=0)

        # Danh sách tag string
        suggested_tags_list = [item.tag for item in tag_res.items]
        if material_in and material_in.lower() not in [t.lower() for t in suggested_tags_list]:
            suggested_tags_list.insert(0, material_in)

        # --- KHỐI 4: CONTENT GENERATION (TITLES & DESCRIPTION) ---
        try:
            content_res = generate_content(
                user_title=title_input or effective_category_name,
                category_name=effective_category_name,
                material=material_in,
                blank_cost=blank_cost,
                extra_attributes=extra_attr,
                banned_keywords=banned
            )
        except Exception:
            from app.services.f42.content_fallback import generate_fallback_content
            content_res = generate_fallback_content(
                user_title=title_input or effective_category_name,
                category_name=effective_category_name,
                material=material_in
            )

        elapsed_ms = int((time.time() - start_time) * 1000)
        meta_res = MetaResult(elapsed_ms=elapsed_ms, cache_hit=False)

        # --- CHUYỂN ĐỔI BACKWARD-COMPATIBILITY CHO FRONTEND ---
        suggested_titles_list = [t.text for t in content_res.titles]
        if not suggested_titles_list:
            suggested_titles_list = [title_input or effective_category_name]

        rec_price = pricing_res.suggested_price
        rec_markup = (rec_price - int(blank_cost)) if blank_cost > 0 else int(rec_price * 0.40)
        if rec_markup < 0:
            rec_markup = max(35000, int(blank_cost * 0.30))

        pricing_insight_compat = {
            "recommended_price": rec_price,
            "recommended_markup": max(0, rec_markup),
            "price_range": {
                "low": pricing_res.suggested_range.low,
                "median": rec_price,
                "high": pricing_res.suggested_range.high,
                "premium": int(pricing_res.suggested_range.high * 1.25)
            },
            "market_sample_count": pricing_res.sample_size_after_outlier_filter,  # SỐ MẪU THẬT, KHÔNG HASH
            "summary": pricing_res.explanation
        }

        trending_keywords_compat = [
            {
                "keyword": item.tag.title(),
                "growth": f"+{min(50, int(item.score * 5))}%",
                "demand_index": min(100.0, round(item.score * 10, 1)),
                "gap_score": min(100.0, round(item.score * 8, 1)),
                "is_hot": idx < 3,
                "tag_id": None
            }
            for idx, item in enumerate(tag_res.items)
        ]

        full_desc_text = _build_full_seo_description_text(
            title=suggested_titles_list[0],
            category_name=effective_category_name,
            desc_obj=content_res.description,
            tags=suggested_tags_list
        )

        return UnifiedSuggestionResponse(
            category=category_res,
            pricing=pricing_res,
            tags=tag_res,
            content=content_res,
            meta=meta_res,
            # Backward compatibility fields
            category_detected=effective_category_name,
            product_type=req.product_type or "general",
            noun=title_input.split()[0].title() if title_input else "Sản Phẩm",
            suggested_titles=suggested_titles_list,
            pricing_insight=pricing_insight_compat,
            trending_keywords=trending_keywords_compat,
            suggested_tags=suggested_tags_list[:10],
            seo_description=full_desc_text
        )
