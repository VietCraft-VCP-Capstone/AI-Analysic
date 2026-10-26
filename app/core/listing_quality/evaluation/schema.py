from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

class LabeledListing(BaseModel):
    listing_id: str
    category: str
    title: Optional[str] = None
    description: Optional[str] = None
    images: List[str] = Field(default_factory=list)
    materials: List[str] = Field(default_factory=list)
    original_price: Optional[float] = None
    tags: List[str] = Field(default_factory=list)
    variants: List[Dict[str, Any]] = Field(default_factory=list)
    ground_truth_issues: List[str] = Field(default_factory=list)
    provenance: str = "curated_pod_expert_review"

class DetectorMetrics(BaseModel):
    detector: str
    total_samples: int
    tp: int
    fp: int
    fn: int
    tn: int
    precision: float
    recall: float
    f1: float
    fpr: float
    fnr: float
