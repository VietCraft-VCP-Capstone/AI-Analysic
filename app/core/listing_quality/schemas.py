from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field

SeverityLevel = Literal["high", "medium", "low"]
IssueStatus = Literal["open", "resolved", "dismissed", "unverified"]
AuditStatus = Literal["completed", "partial", "failed"]

class Recommendation(BaseModel):
    action: str
    message: str
    field_link: Optional[str] = None
    verification: str

class Issue(BaseModel):
    id: str
    code: str
    detector: str
    severity: SeverityLevel
    field: str
    status: IssueStatus = "open"
    confidence: float = 1.0
    evidence: Dict[str, Any] = Field(default_factory=dict)
    message: str
    recommendation: Recommendation

class AuditSummary(BaseModel):
    high: int = 0
    medium: int = 0
    low: int = 0
    total: int = 0

class AuditResponse(BaseModel):
    auditId: str
    listingId: str
    version: str = "listing-audit-1.0"
    status: AuditStatus = "completed"
    auditedAt: str
    contentHash: str
    summary: AuditSummary
    issues: List[Issue] = Field(default_factory=list)
    detectors: Dict[str, str] = Field(default_factory=dict)
    warnings: List[str] = Field(default_factory=list)
