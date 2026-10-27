from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class SuggestionRequest(BaseModel):
    category_id: Optional[str] = None
    categoryId: Optional[str] = None
    category_name: Optional[str] = None
    categoryName: Optional[str] = None
    title: Optional[str] = None
    product_title: Optional[str] = None
    productTitle: Optional[str] = None
    keywords: Optional[str] = None
    material: Optional[str] = None
    blank_cost: Optional[float] = None
    blankCost: Optional[float] = None
    target_margin: Optional[float] = None
    targetMargin: Optional[float] = None
    extra_attributes: Optional[str] = None
    product_type: Optional[str] = None
    productType: Optional[str] = None

    def get_category_id(self) -> Optional[str]:
        return (self.category_id or self.categoryId or "").strip() or None

    def get_category_name(self) -> Optional[str]:
        return (self.category_name or self.categoryName or "").strip() or None

    def get_title_or_keywords(self) -> str:
        return (self.title or self.product_title or self.productTitle or self.keywords or "").strip()

    def get_material(self) -> str:
        return (self.material or "").strip()

    def get_blank_cost(self) -> float:
        val = self.blank_cost if self.blank_cost is not None else self.blankCost
        return float(val) if val is not None and val > 0 else 0.0

    def get_target_margin(self) -> Optional[float]:
        val = self.target_margin if self.target_margin is not None else self.targetMargin
        return float(val) if val is not None and val > 0 else None


# New Refactored Response Models
class CategoryCandidate(BaseModel):
    id: str
    name: str
    score: float


class CategoryResult(BaseModel):
    resolved_id: Optional[str] = None
    resolved_name: Optional[str] = None
    source: str = "none"  # "seller_selected" | "tfidf" | "none"
    candidates: List[CategoryCandidate] = Field(default_factory=list)
    needs_confirmation: bool = False


class PriceRange(BaseModel):
    low: int = 0
    high: int = 0


class ComparableItem(BaseModel):
    title: str
    price: int
    similarity: float
    source: str  # "tiki" | "vietcraft"


class PricingResult(BaseModel):
    mode: str = "none"  # "market" | "market_low_confidence" | "cost_plus" | "none"
    # "comparables" | "category_market" | "cost_plus" | "none"
    method: str = "none"
    insufficient_market_data: bool = False
    sample_size: int = 0
    sample_size_after_outlier_filter: int = 0
    p25: int = 0
    p50: int = 0
    p75: int = 0
    p90: int = 0
    suggested_price: int = 0
    suggested_range: PriceRange = Field(default_factory=PriceRange)
    confidence: str = "none"  # "high" | "medium" | "low" | "none"
    warnings: List[str] = Field(default_factory=list)
    explanation: str = ""
    comparables: List[ComparableItem] = Field(default_factory=list)
    detected_product: Optional[str] = None
    detected_brand: Optional[str] = None
    source_label: Optional[str] = None


class TagItem(BaseModel):
    tag: str
    score: float = 0.0
    freq: int = 0
    source: str = "internal"  # "internal" | "category" | "llm"


class TagResult(BaseModel):
    items: List[TagItem] = Field(default_factory=list)
    basis: str = "popular_tags_internal"
    sample_size: int = 0


class TitleItem(BaseModel):
    text: str
    angle: str = "balanced"  # "material" | "function" | "style" | "technical" | "balanced"


class SpecItem(BaseModel):
    label: str
    value: str


class DescriptionStructure(BaseModel):
    intro: str = ""
    specs: List[SpecItem] = Field(default_factory=list)
    highlights: List[str] = Field(default_factory=list)
    care_guide: Optional[str] = None


class ContentResult(BaseModel):
    source: str = "fallback"  # "llm" | "fallback"
    titles: List[TitleItem] = Field(default_factory=list)
    description: DescriptionStructure = Field(default_factory=DescriptionStructure)
    claims_used: List[str] = Field(default_factory=list)
    missing_info: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    disclaimer: str = "Nội dung do AI gợi ý, vui lòng kiểm tra lại trước khi đăng."


class MetaResult(BaseModel):
    elapsed_ms: int = 0
    cache_hit: bool = False


class UnifiedSuggestionResponse(BaseModel):
    # New standardized structure
    category: CategoryResult = Field(default_factory=CategoryResult)
    pricing: PricingResult = Field(default_factory=PricingResult)
    tags: TagResult = Field(default_factory=TagResult)
    content: ContentResult = Field(default_factory=ContentResult)
    meta: MetaResult = Field(default_factory=MetaResult)

    # Backward compatibility with existing Frontend
    category_detected: str = ""
    product_type: str = "general"
    noun: str = "Sản Phẩm"
    suggested_titles: List[str] = Field(default_factory=list)
    pricing_insight: Dict[str, Any] = Field(default_factory=dict)
    trending_keywords: List[Dict[str, Any]] = Field(default_factory=list)
    suggested_tags: List[str] = Field(default_factory=list)
    seo_description: str = ""
    detected_material: Optional[str] = None
    detected_product: Optional[str] = None
    detected_brand: Optional[str] = None
    ai_engine_status: Dict[str, Any] = Field(default_factory=dict)
