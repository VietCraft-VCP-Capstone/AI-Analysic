import time
from typing import Any, Dict, List, Optional, Set
from pymongo import MongoClient

from app.config import settings
from app.services.f42.ai_engine import MarketAIAdvisor
from app.services.f42.comparable_pricing import ComparableEstimate, ComparableIndex
from app.services.f42.context_resolver import ContextResolver
from app.services.f42.external_market import ExternalMarketProvider
from app.services.f42.pricing_engine import (
    compute_pricing,
    detect_material,
    fetch_prices_from_db,
    format_vnd,
    pricing_from_comparables,
    round_price,
)
from app.services.f42.vi_text import contains_phrase_lenient, strip_accents
from app.services.f42.schemas import (
    CategoryCandidate,
    CategoryResult,
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
    """Ghép bài mô tả chuẩn giao diện cho Frontend."""
    intro = getattr(desc_obj, "intro", "") or ""
    specs = getattr(desc_obj, "specs", []) or []
    highlights = getattr(desc_obj, "highlights", []) or []
    care_guide = getattr(desc_obj, "care_guide", None)

    specs_text = "\n".join([f"  • {s.label}: {s.value}" for s in specs]) if specs else f"  • Danh mục: {category_name}"
    highlights_text = "\n".join([f"  • {h}" for h in highlights]) if highlights else "  • Sản phẩm được kiểm định chất lượng kỹ càng."
    care_text = f"\nHƯỚNG DẪN BẢO QUẢN:\n{care_guide}\n" if care_guide else ""
    tags_text = ", ".join(["#" + t.replace(" ", "") for t in tags[:8]]) if tags else ""

    text = f"""{title.upper()}

THÔNG TIN SẢN PHẨM:
{intro}

THÔNG SỐ SẢN PHẨM:
{specs_text}

ĐẶC ĐIỂM NỔI BẬT:
{highlights_text}
{care_text}
CHÍNH SÁCH BÁN HÀNG:
- 100% hình ảnh thực tế, mô tả minh bạch trung thực.
- Kiểm tra chất lượng kỹ càng trước khi đóng gói gửi đi.
- Hỗ trợ đổi trả theo đúng quy định sàn nếu có lỗi sản xuất.

TỪ KHÓA TÌM KIẾM:
{tags_text}
"""
    return text.strip()


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


def _ml_fallback_pricing(query: str, category_name: str, blank_cost: float) -> Optional[PricingResult]:
    """Ước lượng thô từ mô hình hồi quy khi không có dữ liệu so sánh nào. Luôn gắn độ tin cậy thấp."""
    band = ExternalMarketProvider.predict_price_band_ml(query, category_name) if query else None
    if not band or band[1] <= 0:
        return None
    p25, p50, p75 = band
    warnings = [
        "Không tìm thấy sản phẩm tương tự để đối chiếu, đây là ước lượng từ mô hình máy học — hãy kiểm tra lại trước khi áp dụng.",
    ]
    if blank_cost > 0:
        min_safe = round_price(blank_cost * 1.30)
        if p50 < min_safe:
            warnings.append("Ước lượng thị trường thấp hơn giá vốn + biên tối thiểu, đã nâng giá đề xuất lên mức an toàn.")
            p50 = min_safe
            p25 = max(p25, min_safe)
            p75 = max(p75, p50)
    return PricingResult(
        mode="market_low_confidence",
        method="ml_estimate",
        insufficient_market_data=True,
        sample_size=0,
        sample_size_after_outlier_filter=0,
        p25=p25, p50=p50, p75=p75, p90=p75,
        suggested_price=p50,
        suggested_range=PriceRange(low=p25, high=p75),
        confidence="low",
        warnings=warnings,
        explanation=(
            f"Ước lượng từ mô hình hồi quy (chưa có sản phẩm tương tự để đối chiếu): "
            f"khoảng {format_vnd(p25)} – {format_vnd(p75)}, mức giữa {format_vnd(p50)}."
        ),
        source_label="Ước tính mô hình ML (Chưa có mẫu đối chiếu)",
    )


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

        # Tự điền chất liệu nếu seller để trống nhưng tiêu đề có nêu rõ (không dùng để nhân giá)
        effective_material = material_in or detect_material(title_input)

        # Truy vấn đầy đủ: tiêu đề + chất liệu khai báo riêng + thuộc tính khác
        combined_query = title_input
        if effective_material and not contains_phrase_lenient(title_input, effective_material):
            combined_query = f"{combined_query} {effective_material}".strip()
        if extra_attr:
            combined_query = f"{combined_query} {extra_attr}".strip()

        # -------------------------------------------------------------
        # KHỐI 0: CÀO & TỔNG HỢP DỮ LIỆU TỪ SÀN VIETCRAFT & GOOGLE TRENDS
        # -------------------------------------------------------------
        internal_market = MarketDataAggregator.fetch_internal_platform_data(
            title=title_input,
            category_name=category_name_in,
            db_live=db_live
        )
        google_trends = MarketDataAggregator.fetch_google_trending_data(
            query=title_input or category_name_in,
            category_name=category_name_in,
            db_data=_get_data_db()
        )

        # -------------------------------------------------------------
        # KHỐI 1: KIỂM TRA REAL AI (Google Gemini LLM Trực Tiếp)
        # -------------------------------------------------------------
        ai_data: Optional[Dict[str, Any]] = None
        if MarketAIAdvisor.is_gemini_available():
            try:
                ai_data = MarketAIAdvisor.call_gemini_analysis(
                    title=title_input,
                    category_name=category_name_in or "",
                    material=effective_material or "",
                    blank_cost=blank_cost,
                    extra_attributes=extra_attr,
                    internal_data_summary=internal_market.get("summary_text", ""),
                    google_trends_summary=google_trends.get("summary_text", "")
                )
            except Exception:
                ai_data = None

        if ai_data:
            detected_product = ai_data.get("detected_product")
            detected_brand = ai_data.get("detected_brand")
            detected_category_name = ai_data.get("detected_category") or category_name_in

            # 1. Danh mục
            category_res = CategoryResult(
                resolved_id=category_id_in,
                resolved_name=category_name_in or detected_category_name or None,
                source="llm_gemini" if not category_id_in else "seller_selected",
                needs_confirmation=bool(not category_id_in and not detected_category_name),
            )
            effective_category_id = category_res.resolved_id
            effective_category_name: str = category_res.resolved_name or detected_category_name or ""

            # Kiểm tra định giá: Nếu AI trả về 0 (ví dụ model mới chưa phát hành), tự động suy luận từ phân khúc thị trường & Google Trends
            rec_price_candidate = int(ai_data.get("pricing", {}).get("recommended") or 0)
            if rec_price_candidate <= 0:
                p25, p50, p75, expl = MarketDataAggregator.deduce_optimal_pricing(
                    title=title_input,
                    category_name=effective_category_name,
                    internal_data=internal_market,
                    google_trends=google_trends,
                    blank_cost=blank_cost,
                )
                if p50 > 0:
                    ai_data["pricing"] = {
                        "low": p25,
                        "recommended": p50,
                        "high": p75,
                        "explanation": expl
                    }

            # 2. Định giá AI thị trường
            pricing_res = MarketAIAdvisor.build_pricing_result(
                ai_data,
                blank_cost=blank_cost,
                method="llm_gemini",
                mode="market_ai",
                confidence="medium" if (ai_data.get("pricing", {}).get("recommended") or 0) > 0 else "none",
                sample_size=internal_market.get("found_count", 0)
            )

            # 3. Tiêu đề & Bài mô tả chuẩn Mall TMĐT
            content_res = MarketAIAdvisor.build_content_result(
                ai_data,
                title_input=title_input,
                source="llm_gemini"
            )

            # 4. Thẻ Tag
            tag_res = MarketAIAdvisor.build_tag_result(ai_data, basis="gemini_seo_tags")
            suggested_tags_list = ai_data.get("tags", [])

            # Bổ sung từ khóa xu hướng Google Trends vào danh sách gợi ý
            for kw in google_trends.get("trending_keywords", [])[:5]:
                if kw.lower() not in banned and not any(strip_accents(t) == strip_accents(kw) for t in suggested_tags_list):
                    suggested_tags_list.append(kw)
                    tag_res.items.append(TagItem(tag=kw, score=2.5, freq=1, source="google_trends"))

        else:
            # -------------------------------------------------------------
            # KHỐI 2: DỮ LIỆU ĐỐI CHUẨN THỰC TẾ & SEMANTIC AI ENGINE
            # -------------------------------------------------------------
            comp_est: Optional[ComparableEstimate] = None
            try:
                index = ComparableIndex.get()
                if index is not None and combined_query:
                    index.refresh_live(db_live)
                    comp_est = index.estimate(combined_query)
            except Exception:
                comp_est = None
            detected_product = comp_est.detected_product if comp_est else None

            # Context Resolver (danh mục)
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
                    resolved_name=category_name_in,
                    source="fallback",
                    needs_confirmation=True
                )

            if category_res.source != "seller_selected" and (category_res.resolved_id is None or category_res.needs_confirmation):
                voted = _vote_category_from_comparables(comp_est, categories)
                if voted is not None and (category_res.resolved_id is None or voted.resolved_id == category_res.resolved_id
                                          or not category_res.candidates
                                          or voted.candidates[0].score > category_res.candidates[0].score):
                    category_res = voted

            effective_category_id = category_res.resolved_id
            effective_category_name: str = category_res.resolved_name or detected_product or category_name_in or ""

            sem_res: Optional[Dict[str, Any]] = None
            # Pricing:
            # Ưu tiên 1: Tin đối chiếu thực tế uy tín (đã lọc phụ kiện, độ tương đồng cao)
            # Ưu tiên 2: Cào dữ liệu sàn VietCraft + Google Trends + Phân khúc thương hiệu
            # Ưu tiên 3: Semantic AI Engine (Cost-Plus nếu có giá vốn, hoặc báo chưa đủ dữ liệu)
            if (
                comp_est is not None
                and comp_est.usable
                and comp_est.confidence in ("high", "medium")
                and comp_est.mean_similarity >= 0.25
                and comp_est.p50 > 0
            ):
                pricing_res = pricing_from_comparables(comp_est, blank_cost=blank_cost)
            else:
                p25, p50, p75, expl = 0, 0, 0, ""
                if db_live_override is not False:
                    p25, p50, p75, expl = MarketDataAggregator.deduce_optimal_pricing(
                        title=title_input,
                        category_name=effective_category_name,
                        internal_data=internal_market,
                        google_trends=google_trends,
                        blank_cost=blank_cost,
                    )
                if p50 > 0:
                    pricing_res = PricingResult(
                        mode="market_ai",
                        method="market_aggregator",
                        insufficient_market_data=False,
                        sample_size=internal_market.get("found_count", 0),
                        sample_size_after_outlier_filter=internal_market.get("found_count", 0),
                        p25=p25,
                        p50=p50,
                        p75=p75,
                        p90=int(p75 * 1.12),
                        suggested_price=p50,
                        suggested_range=PriceRange(low=p25, high=p75),
                        confidence="medium",
                        warnings=[],
                        explanation=expl,
                        source_label="Phân tích xu hướng thị trường & sàn TMĐT",
                        detected_product=detected_product,
                        detected_brand=detected_brand if 'detected_brand' in locals() else None,
                    )
                else:
                    sem_res = MarketAIAdvisor.semantic_fallback_analysis(
                        title=title_input,
                        category_name=effective_category_name,
                        material=effective_material or "",
                        blank_cost=blank_cost,
                        extra_attributes=extra_attr,
                    )
                    detected_product = sem_res.get("detected_product") or detected_product
                    detected_brand = sem_res.get("detected_brand")
                    if sem_res.get("detected_category") and (
                        not effective_category_name or effective_category_name in (DEFAULT_CATEGORY_NAME, "Thời Trang & Đời Sống", "Mỹ nghệ & Đời sống")
                    ):
                        effective_category_name = str(sem_res["detected_category"])

                    # Không dùng bảng giá theo từ khóa trong semantic fallback làm giá thị trường.
                    pricing_res = compute_pricing(
                        prices=internal_market.get("prices", []),
                        blank_cost=blank_cost,
                        target_margin=target_margin
                    )

            # Tag Mining
            if sem_res and "tags" in sem_res and sem_res["tags"]:
                tag_res = MarketAIAdvisor.build_tag_result(sem_res, basis="ai_semantic_tags")
                suggested_tags_list = sem_res["tags"]
            else:
                try:
                    tag_res = fetch_tags_from_db(effective_category_id, db_live, banned)
                except Exception:
                    tag_res = TagResult(items=[], basis="popular_tags_internal", sample_size=0)

                def _known(tag: str) -> bool:
                    key = strip_accents(tag)
                    return any(strip_accents(t.tag) == key for t in tag_res.items)

                try:
                    comp_items: List[TagItem] = []
                    if comp_est is not None and comp_est.comparables:
                        for kw, score, freq in ComparableIndex.mine_keywords(comp_est.comparables, combined_query, top_n=6):
                            if kw.lower() not in banned and not _known(kw):
                                comp_items.append(TagItem(tag=kw, score=score, freq=freq, source="comparables"))
                    tag_res.items = comp_items + tag_res.items

                    lifted_items = ExternalMarketProvider.get_lifted_keywords(effective_category_name, combined_query, top_n=6)
                    for item in lifted_items:
                        kw = item.get("keyword", "")
                        if kw and kw.lower() not in banned and not _known(kw):
                            tag_res.items.append(TagItem(tag=kw, score=float(item.get("lift", 1.5)), freq=int(item.get("freq", 2)), source="external_market"))
                except Exception:
                    pass

                suggested_tags_list = [item.tag for item in tag_res.items]
                for extra_tag in (detected_product, effective_material):
                    if extra_tag and strip_accents(extra_tag) not in [strip_accents(t) for t in suggested_tags_list]:
                        suggested_tags_list.insert(0, extra_tag)

            # Content Generation: Phân tích chuyên sâu từ Semantic AI
            if not sem_res:
                sem_res = MarketAIAdvisor.semantic_fallback_analysis(
                    title=title_input or effective_category_name,
                    category_name=effective_category_name,
                    material=effective_material or "",
                    blank_cost=blank_cost,
                    extra_attributes=extra_attr,
                )
            content_res = MarketAIAdvisor.build_content_result(
                sem_res,
                title_input=title_input or effective_category_name,
                source="ai_semantic_model"
            )

        elapsed_ms = int((time.time() - start_time) * 1000)
        meta_res = MetaResult(elapsed_ms=elapsed_ms, cache_hit=False)

        # --- CHUYỂN ĐỔI BACKWARD-COMPATIBILITY CHO FRONTEND ---
        suggested_titles_list: List[str] = [t.text for t in content_res.titles]
        if not suggested_titles_list:
            suggested_titles_list = [title_input or effective_category_name]

        rec_price = pricing_res.suggested_price
        if rec_price <= 0:
            rec_markup = 0
        else:
            rec_markup = (rec_price - int(blank_cost)) if blank_cost > 0 else int(rec_price * 0.40)
            if rec_markup < 0:
                rec_markup = max(0, int(blank_cost * 0.30))

        is_ai_live = bool(ai_data)
        ai_engine_status = {
            "is_ai_live": is_ai_live,
            "engine": "gemini" if is_ai_live else ("comparables" if pricing_res.method == "comparables" else ("market_aggregator" if pricing_res.method == "market_aggregator" else ("cost_plus" if pricing_res.method == "cost_plus" else "semantic_fallback"))),
            "engine_label": (
                "Phân tích chuyên sâu (Dữ liệu Sàn & Google Trends)" if is_ai_live
                else ("Đối chiếu từ sản phẩm tương đồng trên thị trường" if pricing_res.method == "comparables"
                else ("Phân tích thị trường & Google Trends" if pricing_res.method == "market_aggregator"
                else ("Ước tính theo giá vốn (Cost-Plus)" if pricing_res.method == "cost_plus"
                else "Chưa đủ dữ liệu thị trường")))
            ),
            "pricing_method": pricing_res.method,
            "source_label": pricing_res.source_label or "Chưa đủ dữ liệu",
            "market_sample_count": pricing_res.sample_size_after_outlier_filter,
            "notice": "" if is_ai_live or pricing_res.method == "market_aggregator" else "Tiêu đề và mô tả đang dùng mẫu dự phòng; giá được lấy từ dữ liệu đối chiếu, giá vốn hoặc để trống nếu chưa đủ căn cứ."
        }

        pricing_insight_compat = {
            "recommended_price": rec_price,
            "recommended_markup": max(0, rec_markup),
            "price_range": {
                "low": pricing_res.suggested_range.low,
                "median": rec_price,
                "high": pricing_res.suggested_range.high,
                "premium": pricing_res.p90 or pricing_res.suggested_range.high,
            },
            "market_sample_count": pricing_res.sample_size_after_outlier_filter,  # SỐ MẪU THẬT, KHÔNG HASH
            "summary": pricing_res.explanation,
            "method": pricing_res.method,
            "source_label": pricing_res.source_label or "Chưa đủ dữ liệu",
            "confidence": pricing_res.confidence,
            "warnings": pricing_res.warnings,
            "detected_product": pricing_res.detected_product,
            "detected_brand": pricing_res.detected_brand,
            "comparables": [c.model_dump() for c in pricing_res.comparables[:5]],
            "ai_engine_status": ai_engine_status,
        }

        trending_keywords_compat = [
            {
                "keyword": item.tag.title(),
                "growth": (
                    "Google Trends" if getattr(item, "source", "") == "google_trends"
                    else ("Sàn VietCraft" if getattr(item, "source", "") == "vietcraft"
                    else (f"{item.freq} sp" if item.freq > 0 else ""))
                ),
                "demand_index": min(100.0, round(item.score * 10, 1)),
                "gap_score": min(100.0, round(item.score * 8, 1)),
                "is_hot": getattr(item, "source", "") == "google_trends",
                "tag_id": None,
                "source": getattr(item, "source", "internal"),
                "frequency": item.freq,
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
            category_detected=category_res.resolved_name or effective_category_name or "",
            product_type=req.product_type or "general",
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
