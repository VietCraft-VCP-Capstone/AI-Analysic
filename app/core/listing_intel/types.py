from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ListingInput:
    title: str
    description: str = ""
    tags: list[str] = field(default_factory=list)
    materials: list[str] = field(default_factory=list)
    category: str | None = None
    group: str | None = None
    price: float | None = None
    image_urls: list[str] = field(default_factory=list)
    product_id: str | None = None
    seller_id: str | None = None
    updated_at: datetime | None = None
    rating_count: int | None = None
    average_rating: float | None = None


@dataclass
class AxisResult:
    score: float | None = None
    features: dict[str, float] = field(default_factory=dict)
    issues: list[dict] = field(default_factory=list)
    missing_reason: str | None = None
