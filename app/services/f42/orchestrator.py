"""
F42 Smart Suggestion — điều phối 4 khối: danh mục, giá, tag, nội dung.

Nguyên tắc giá (spec F42): mọi mức giá phải có căn cứ dữ liệu thật.
  1. Sản phẩm tương đồng (kNN TF-IDF trên tập TMĐT + sản phẩm đang bán trên sàn)
  2. Sản phẩm có tên tương tự đang bán trên sàn VietCraft (giá thật từ product_variants)
  3. Phân vị giá cả danh mục trên sàn
  4. Cost-Plus từ giá vốn seller nhập
  5. Không gợi ý (nói rõ thiếu dữ liệu)
Gemini KHÔNG định giá; chỉ viết tiêu đề / mô tả / tag và mọi nội dung đều qua content_validator.
"""

import logging
import time
from typing import Any, Dict, List, Optional, Set
from pymongo import MongoClient

from app.config import settings
from app.services.f42 import config
from app.services.f42.ai_engine import MarketAIAdvisor
from app.services.f42.comparable_pricing import ComparableEstimate, ComparableIndex
from app.services.f42.content_validator import validate_content
from app.services.f42.context_resolver import ContextResolver
from app.services.f42.external_market import ExternalMarketProvider
from app.services.f42.pricing_engine import (
    compute_pricing,
    detect_material,
    fetch_prices_from_db,
    pricing_from_comparables,
)
from app.services.f42.vi_text import contains_phrase_lenient, strip_accents
from app.services.f42.schemas import (
    CategoryCandidate,
    CategoryResult,
    ComparableItem,
    ContentResult,
    DescriptionStructure,
    MetaResult,
    PriceRange,
    PricingResult,
    SpecItem,
    SuggestionRequest,
    TagItem,
    TagResult,
    TitleItem,
    UnifiedSuggestionResponse,
)
from app.services.f42.market_aggregator import MarketDataAggregator
from app.services.f42.tag_mining import fetch_tags_from_db

logger = logging.getLogger(__name__)

_client_live: Optional[MongoClient] = None
_cached_categories: List[Dict[str, Any]] = []
_cached_categories_ts: float = 0.0
_cached_banned: Set[str] = set()
_cached_banned_ts: float = 0.0
CACHE_TTL = 300.0  # 5 phút
DEFAULT_CATEGORY_NAME = "Sản phẩm"


def _get_mongo_client() -> Optional[MongoClient]:
    global _client_live
    if _client_live is None and settings.MONGO_URI:
        try:
            _client_live = MongoClient(settings.MONGO_URI, serverSelectionTimeoutMS=3000, maxPoolSize=5)
        except Exception as exc:
            logger.warning("f42.mongo_connect_failed", extra={"error": str(exc)})
    return _client_live


def _get_live_db():
    client = _get_mongo_client()
    if client:
        try:
            return client[settings.MONGO_DB_LIVE]
        except Exception:
            pass
    return None


def _get_data_db():
    client = _get_mongo_client()
    if client:
        try:
            return client[settings.MONGO_DB_DATA]
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
    """Ghép bài mô tả cho FE. Chỉ gồm những gì đã có — không chèn cam kết/chính sách mặc định."""
    intro = getattr(desc_obj, "intro", "") or ""
    specs = getattr(desc_obj, "specs", []) or []
    highlights = getattr(desc_obj, "highlights", []) or []
    care_guide = getattr(desc_obj, "care_guide", None)

    sections: List[str] = [title.strip()]
    if intro:
        sections.append(f"THÔNG TIN SẢN PHẨM:\n{intro}")
    spec_lines = [f"  • {s.label}: {s.value}" for s in specs] or ([f"  • Danh mục: {category_name}"] if category_name else [])
    if spec_lines:
        sections.append("THÔNG SỐ SẢN PHẨM:\n" + "\n".join(spec_lines))
    if highlights:
        sections.append("ĐẶC ĐIỂM NỔI BẬT:\n" + "\n".join(f"  • {h}" for h in highlights))
    if care_guide:
        sections.append(f"HƯỚNG DẪN BẢO QUẢN:\n{care_guide}")
    if tags:
        sections.append("TỪ KHÓA TÌM KIẾM:\n" + ", ".join("#" + t.replace(" ", "") for t in tags[:8]))
    return "\n\n".join(sections).strip()


def _vote_category_from_comparables(
    est: Optional[ComparableEstimate], categories: List[Dict[str, Any]]
) -> Optional[CategoryResult]:
    """Khi tên danh mục không khớp tiêu đề, dùng danh mục của các sản phẩm tương đồng đang bán trên sàn."""
    if est is None or not est.category_votes:
        return None
    names = {str(c.get("_id")): c.get("name", "") for c in categories}
    votes = {cid: v for cid, v in est.category_votes.items() if cid in names}
    if not votes:
        return None
    total = sum(votes.values()) or 1.0
    ranked = sorted(votes.items(), key=lambda kv: kv[1], reverse=True)[:3]
    top_id, top_v = ranked[0]
    share = top_v / total
    if share < 0.5:
        return None
    return CategoryResult(
        resolved_id=top_id,
        resolved_name=names[top_id],
        source="comparables",
        candidates=[CategoryCandidate(id=cid, name=names[cid], score=round(v / total, 3)) for cid, v in ranked],
        needs_confirmation=share < 0.75,
    )


def _resolve_pricing(
    comp_est: Optional[ComparableEstimate],
    internal_market: Dict[str, Any],
    category_id: Optional[str],
    db_live: Any,
    blank_cost: float,
    target_margin: Optional[float],
    material: Optional[str],
) -> PricingResult:
    """Một đường định giá duy nhất cho mọi nhánh (có hay không có Gemini)."""
    # 1. Sản phẩm tương đồng
    if comp_est is not None and comp_est.usable and comp_est.p50 > 0 and len(comp_est.comparables) >= 2:
        return pricing_from_comparables(comp_est, blank_cost=blank_cost)

    # 2. Sản phẩm cùng tên trên sàn VietCraft
    prices = internal_market.get("prices") or []
    if len(prices) >= config.MIN_SAMPLE_LOW:
        res = compute_pricing(prices, blank_cost=blank_cost, target_margin=target_margin)
        if res.method == "category_market":
            n = res.sample_size_after_outlier_filter
            res.method = "internal_similar"
            res.confidence = "medium" if n >= config.MIN_SAMPLE_HIGH else "low"
            res.mode = "market" if n >= config.MIN_SAMPLE_HIGH else "market_low_confidence"
            res.warnings = [w for w in res.warnings if "toàn bộ danh mục" not in w]
            if n < config.MIN_SAMPLE_HIGH:
                res.warnings.append("Số mẫu ít, độ tin cậy thấp.")
            res.explanation = res.explanation.replace(
                "sản phẩm cùng danh mục trên sàn", "sản phẩm có tên tương tự đang bán trên sàn VietCraft"
            )
            res.source_label = f"{n} sản phẩm tương tự trên sàn VietCraft"
        return res

    # 3. Cả danh mục trên sàn → 4. Cost-Plus → 5. Không gợi ý (compute_pricing tự rẽ nhánh)
    cat_prices = fetch_prices_from_db(category_id, db_live, material) if category_id and db_live is not None else []
    return compute_pricing(cat_prices, blank_cost=blank_cost, target_margin=target_margin)


_ENGINE_LABELS = {
    "comparables": "Đối chiếu từ sản phẩm tương đồng",
    "internal_similar": "Thống kê sản phẩm tương tự trên sàn VietCraft",
    "category_market": "Thống kê giá cả danh mục trên sàn",
    "cost_plus": "Ước tính theo giá vốn (Cost-Plus)",
    "none": "Chưa đủ dữ liệu để gợi ý giá",
}

_GROWTH_LABELS = {
    "google_trends": "Google Trends",
    "google_suggest": "Gợi ý Google",
    "ai": "AI gợi ý",
}


def _dedup_key(tag: str) -> str:
    return strip_accents(tag).replace(" ", "")


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
        db_data = None if db_live_override is not None else _get_data_db()

        categories = _get_categories(db_live)
        banned = _get_banned_keywords(db_live)

        title_input = req.get_title_or_keywords()
        category_id_in = req.get_category_id()
        category_name_in = req.get_category_name()
        material_in = req.get_material()
        blank_cost = req.get_blank_cost()
        target_margin = req.get_target_margin()
        extra_attr = req.extra_attributes or ""

        # Tự điền chất liệu nếu seller để trống nhưng tiêu đề có nêu rõ
        effective_material = material_in or detect_material(title_input)

        combined_query = title_input
        if effective_material and not contains_phrase_lenient(title_input, effective_material):
            combined_query = f"{combined_query} {effective_material}".strip()
        if extra_attr:
            combined_query = f"{combined_query} {extra_attr}".strip()
        seller_text = " ".join(x for x in (title_input, material_in, extra_attr, category_name_in or "") if x)

        # ---------------- Khối 0: dữ liệu ----------------
        internal_market = MarketDataAggregator.fetch_internal_platform_data(
            title=title_input, category_name=category_name_in or "", db_live=db_live
        )
        keyword_data = MarketDataAggregator.fetch_google_trending_data(
            query=title_input or category_name_in or "", category_name=category_name_in or "", db_data=db_data
        )

        comp_est: Optional[ComparableEstimate] = None
        try:
            index = ComparableIndex.get()
            if index is not None and combined_query:
                index.refresh_live(db_live)
                comp_est = index.estimate(combined_query)
        except Exception as exc:
            logger.warning("f42.comparables_failed", extra={"error": str(exc)})
        detected_product = comp_est.detected_product if comp_est else None
        detected_brand = comp_est.detected_brand if comp_est else None

        # ---------------- Gemini (chỉ nội dung) ----------------
        ai_data: Optional[Dict[str, Any]] = None
        ai_errors: List[str] = []
        if MarketAIAdvisor.is_gemini_available() and title_input:
            try:
                raw = MarketAIAdvisor.call_gemini_analysis(
                    title=title_input,
                    category_name=category_name_in or "",
                    material=material_in,
                    blank_cost=blank_cost,
                    extra_attributes=extra_attr,
                    internal_data_summary=internal_market.get("summary_text", ""),
                    google_trends_summary=keyword_data.get("summary_text", ""),
                )
                if raw:
                    ai_data, ai_errors = validate_content(
                        raw, seller_text, banned, material_declared=bool(material_in)
                    )
                    if ai_errors:
                        logger.info("f42.content_validation", extra={"errors": ai_errors[:20]})
                    if len(ai_data.get("titles") or []) < 2:
                        ai_data = None  # quá ít tiêu đề hợp lệ → dùng nội dung dự phòng
            except Exception as exc:
                logger.warning("f42.gemini_failed", extra={"error": str(exc)})
                ai_data = None

        # ---------------- Khối 1: danh mục ----------------
        try:
            category_res = ContextResolver(categories).resolve(
                category_id=category_id_in, category_name=category_name_in, user_title=title_input
            )
        except Exception:
            category_res = CategoryResult(
                resolved_id=category_id_in, resolved_name=category_name_in, source="fallback", needs_confirmation=True
            )
        if category_res.source != "seller_selected" and (category_res.resolved_id is None or category_res.needs_confirmation):
            voted = _vote_category_from_comparables(comp_est, categories)
            if voted is not None and (
                category_res.resolved_id is None or voted.resolved_id == category_res.resolved_id
                or not category_res.candidates or voted.candidates[0].score > category_res.candidates[0].score
            ):
                category_res = voted
        if category_res.resolved_id is None and ai_data and ai_data.get("detected_category"):
            # Chỉ là tên gợi ý, seller phải xác nhận
            category_res.resolved_name = str(ai_data["detected_category"])
            category_res.source = "llm_gemini"
            category_res.needs_confirmation = True

        effective_category_id = category_res.resolved_id
        effective_category_name: str = category_res.resolved_name or category_name_in or detected_product or ""

        # ---------------- Khối 2: giá ----------------
        try:
            pricing_res = _resolve_pricing(
                comp_est, internal_market, effective_category_id, db_live,
                blank_cost, target_margin, effective_material or None,
            )
        except Exception as exc:
            logger.warning("f42.pricing_failed", extra={"error": str(exc)})
            pricing_res = compute_pricing([], blank_cost=blank_cost, target_margin=target_margin)
        pricing_res.detected_product = pricing_res.detected_product or detected_product
        pricing_res.detected_brand = pricing_res.detected_brand or detected_brand

        # ---------------- Khối 3: tag ----------------
        try:
            tag_res = fetch_tags_from_db(effective_category_id, db_live, banned)
        except Exception:
            tag_res = TagResult(items=[], basis="popular_tags_internal", sample_size=0)
        for item in tag_res.items:
            item.source = "vietcraft"

        seen_tags = {_dedup_key(t.tag) for t in tag_res.items}

        def _add(items: List[TagItem], kw: str, **kw_args: Any) -> None:
            key = _dedup_key(kw)
            if kw and key and key not in seen_tags and kw.lower() not in banned:
                seen_tags.add(key)
                items.append(TagItem(tag=kw, **kw_args))

        front: List[TagItem] = []
        if ai_data:
            for t in ai_data.get("tags") or []:
                _add(front, t, score=1.0, freq=0, source="ai")
        try:
            if comp_est is not None and comp_est.comparables:
                for kw, score, freq in ComparableIndex.mine_keywords(comp_est.comparables, combined_query, top_n=6):
                    _add(front, kw, score=score, freq=freq, source="comparables")
        except Exception:
            pass
        back: List[TagItem] = []
        try:
            for it in ExternalMarketProvider.get_lifted_keywords(effective_category_name, combined_query, top_n=6):
                _add(back, it.get("keyword", ""), score=float(it.get("lift", 1.0)), freq=int(it.get("freq", 0)), source="external_market")
        except Exception:
            pass
        for kw in keyword_data.get("trend_keywords", [])[:5]:
            _add(back, kw, score=1.0, freq=0, source="google_trends")
        for kw in keyword_data.get("suggest_keywords", [])[:5]:
            _add(back, kw, score=0.5, freq=0, source="google_suggest")
        tag_res.items = front + tag_res.items + back

        suggested_tags_list = [item.tag for item in tag_res.items]
        for extra_tag in (detected_product, effective_material):
            if extra_tag and _dedup_key(extra_tag) not in {_dedup_key(t) for t in suggested_tags_list}:
                suggested_tags_list.insert(0, extra_tag)

        # ---------------- Khối 4: nội dung ----------------
        if ai_data:
            content_res = MarketAIAdvisor.build_content_result(ai_data, title_input=title_input, source="llm_gemini")
            if ai_errors:
                content_res.warnings.append(
                    f"Đã loại {len(ai_errors)} chi tiết AI tự thêm mà bạn chưa khai báo (chất liệu, cam kết...)."
                )
        else:
            sem_res = MarketAIAdvisor.semantic_fallback_analysis(
                title=title_input or effective_category_name,
                category_name=effective_category_name,
                material=effective_material or "",
                blank_cost=blank_cost,
                extra_attributes=extra_attr,
            )
            content_res = MarketAIAdvisor.build_content_result(
                sem_res, title_input=title_input or effective_category_name, source="fallback"
            )

        elapsed_ms = int((time.time() - start_time) * 1000)
        meta_res = MetaResult(elapsed_ms=elapsed_ms, cache_hit=False)

        # ---------------- Tương thích FE ----------------
        suggested_titles_list: List[str] = [t.text for t in content_res.titles] or [title_input or effective_category_name]

        rec_price = pricing_res.suggested_price
        # Chỉ tính lợi nhuận khi có giá vốn thật — không tự đặt % lợi nhuận
        rec_markup = max(0, rec_price - int(blank_cost)) if (blank_cost > 0 and rec_price > 0) else 0

        # Bằng chứng: ưu tiên chính các sản phẩm làm căn cứ giá, sau đó là tham khảo
        merged_comps: List[ComparableItem] = list(pricing_res.comparables)
        seen_titles = {c.title for c in merged_comps}
        extra_comps: List[ComparableItem] = []
        if comp_est and comp_est.comparables:
            for c in comp_est.comparables:
                if c.title[:140] not in seen_titles:
                    seen_titles.add(c.title[:140])
                    extra_comps.append(ComparableItem(
                        title=c.title[:140], price=int(round(c.price)), similarity=round(c.similarity, 2),
                        source="Sàn VietCraft" if c.source == "vietcraft" else "Thị trường TMĐT",
                    ))
        for ic in internal_market.get("comparables") or []:
            if ic["title"][:140] not in seen_titles:
                seen_titles.add(ic["title"][:140])
                extra_comps.append(ComparableItem(
                    title=ic["title"][:140], price=ic["price"], similarity=ic.get("similarity"),
                    source=ic.get("source", "Sàn VietCraft"),
                ))
        pricing_res.comparables = (merged_comps + extra_comps)[:6]

        sample_n = pricing_res.sample_size_after_outlier_filter  # SỐ MẪU THẬT làm căn cứ giá
        is_ai_live = bool(ai_data)
        ai_engine_status = {
            "is_ai_live": is_ai_live,
            "engine": pricing_res.method,
            "content_engine": "gemini" if is_ai_live else "fallback",
            "engine_label": _ENGINE_LABELS.get(pricing_res.method, "Chưa đủ dữ liệu"),
            "pricing_method": pricing_res.method,
            "source_label": pricing_res.source_label or "Chưa đủ dữ liệu",
            "market_sample_count": sample_n,
            "notice": (
                "" if is_ai_live
                else "Tiêu đề và mô tả đang dùng mẫu cơ bản (AI viết nội dung chưa khả dụng); hãy bổ sung chi tiết trước khi đăng."
            ),
        }

        pricing_insight_compat = {
            "recommended_price": rec_price,
            "recommended_markup": rec_markup,
            "price_range": {
                "low": pricing_res.suggested_range.low,
                "median": rec_price,
                "high": pricing_res.suggested_range.high,
                "premium": pricing_res.p90 or pricing_res.suggested_range.high,
            },
            "market_sample_count": sample_n,
            "summary": pricing_res.explanation,
            "method": pricing_res.method,
            "source_label": pricing_res.source_label or "Chưa đủ dữ liệu",
            "confidence": pricing_res.confidence,
            "warnings": pricing_res.warnings,
            "detected_product": pricing_res.detected_product,
            "detected_brand": pricing_res.detected_brand,
            "comparables": [c.model_dump() for c in pricing_res.comparables],
            "market_signals": keyword_data.get("search_signals", []),
            "evidence_stats": {
                "sample_size": sample_n,
                "p25": pricing_res.suggested_range.low,
                "p50": rec_price,
                "p75": pricing_res.suggested_range.high,
                "p90": pricing_res.p90 or pricing_res.suggested_range.high,
                "blank_cost": int(blank_cost) if blank_cost > 0 else 0,
                "profit": rec_markup,
                "profit_margin_pct": round(rec_markup / rec_price * 100, 1) if rec_price > 0 and rec_markup > 0 else 0,
            },
            "ai_engine_status": ai_engine_status,
        }

        trending_keywords_compat = []
        for item in tag_res.items:
            src = getattr(item, "source", "internal")
            if src in _GROWTH_LABELS:
                growth = _GROWTH_LABELS[src]
            elif item.freq > 0:
                growth = f"{item.freq} sp"
            else:
                growth = ""
            trending_keywords_compat.append({
                "keyword": item.tag,
                "growth": growth,
                "demand_index": min(100.0, round(item.score * 10, 1)),
                "gap_score": min(100.0, round(item.score * 8, 1)),
                "is_hot": src == "google_trends",
                "tag_id": None,
                "source": src,
                "frequency": item.freq,
            })

        full_desc_text = _build_full_seo_description_text(
            title=suggested_titles_list[0],
            category_name=effective_category_name,
            desc_obj=content_res.description,
            tags=suggested_tags_list,
        )

        return UnifiedSuggestionResponse(
            category=category_res,
            pricing=pricing_res,
            tags=tag_res,
            content=content_res,
            meta=meta_res,
            category_detected=category_res.resolved_name or effective_category_name or "",
            product_type=req.product_type or req.productType or "general",
            noun=detected_product or (title_input.split()[0].title() if title_input else "Sản Phẩm"),
            suggested_titles=suggested_titles_list,
            pricing_insight=pricing_insight_compat,
            trending_keywords=trending_keywords_compat,
            suggested_tags=suggested_tags_list[:10],
            seo_description=full_desc_text,
            detected_material=effective_material or None,
            detected_product=detected_product,
            detected_brand=pricing_res.detected_brand,
            ai_engine_status=ai_engine_status,
        )
