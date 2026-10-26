import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from bson import ObjectId

from app.api.v1._live import db_live
from ..detectors import (
    ImageQualityDetector,
    PodContentDetector,
    RequiredFieldsDetector,
    TextConsistencyDetector,
)
from ..schemas import AuditResponse, AuditSummary, Issue

class AuditService:
    VERSION = "listing-audit-1.0"
    COLLECTION = "listing_quality_audits"

    def __init__(self):
        self.detectors = [
            RequiredFieldsDetector(),
            PodContentDetector(),
            ImageQualityDetector(),
            TextConsistencyDetector(),
        ]

    def _compute_hash(self, listing: Dict[str, Any], variants: List[Dict[str, Any]]) -> str:
        canonical = {
            "title": str(listing.get("title") or "").strip(),
            "description": str(listing.get("description") or "").strip(),
            "images": [str(img) for img in (listing.get("images") or [])],
            "categories": [str(c) for c in (listing.get("categories") or [])],
            "tags": [str(t) for t in (listing.get("tags") or [])],
            "materials": [str(m) for m in (listing.get("materials") or [])],
            "original_price": str(listing.get("original_price") or ""),
            "variants": [
                {
                    "sku": str(v.get("sku") or ""),
                    "size": str(v.get("size") or ""),
                    "color": str(v.get("color") or ""),
                    "material": str(v.get("material") or ""),
                    "retail_price": str(v.get("retail_price") or ""),
                    "is_active": bool(v.get("is_active", True))
                }
                for v in sorted(variants, key=lambda x: str(x.get("sku") or ""))
            ]
        }
        encoded = json.dumps(canonical, sort_keys=True).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _fetch_listing_data(self, listing_id: str) -> Optional[tuple[Dict[str, Any], List[Dict[str, Any]]]]:
        try:
            oid = ObjectId(listing_id)
        except Exception:
            return None

        db = db_live()
        product = db["products"].find_one({"_id": oid})
        if not product:
            return None

        variants = list(db["product_variants"].find({"product_id": oid}))
        return product, variants

    def audit_listing(
        self,
        listing_id: str,
        force: bool = False,
        context_override: Optional[Dict[str, Any]] = None
    ) -> Optional[AuditResponse]:
        data = self._fetch_listing_data(listing_id)
        if not data:
            return None

        product, variants = data
        content_hash = self._compute_hash(product, variants)
        db = db_live()

        if not force and not context_override:
            cached = db[self.COLLECTION].find_one(
                {"listing_id": listing_id, "content_hash": content_hash},
                sort=[("audited_at", -1)]
            )
            if cached and "issues" in cached:
                cached_issues = [Issue(**iss) for iss in cached["issues"]]
                cached_summary = AuditSummary(**cached["summary"])
                return AuditResponse(
                    auditId=cached.get("audit_id", str(cached["_id"])),
                    listingId=listing_id,
                    version=cached.get("version", self.VERSION),
                    status=cached.get("status", "completed"),
                    auditedAt=cached.get("audited_at", datetime.now(timezone.utc).isoformat()),
                    contentHash=content_hash,
                    summary=cached_summary,
                    issues=cached_issues,
                    detectors=cached.get("detectors", {}),
                    warnings=cached.get("warnings", [])
                )

        context: Dict[str, Any] = {"variants": variants}
        if context_override:
            context.update(context_override)

        all_issues: List[Issue] = []
        detectors_status: Dict[str, str] = {}
        warnings: List[str] = []

        for detector in self.detectors:
            try:
                res = detector.evaluate(product, context)
                all_issues.extend(res)
                detectors_status[detector.code] = "completed"
            except Exception as e:
                detectors_status[detector.code] = "failed"
                warnings.append(f"Detector {detector.code} encountered an error: {str(e)}")

        detectors_status["image_consistency"] = "disabled"

        audit_status = "completed"
        if any(s == "failed" for s in detectors_status.values()):
            audit_status = "partial" if any(s == "completed" for s in detectors_status.values()) else "failed"

        seen_codes = set()
        deduped_issues: List[Issue] = []
        for iss in all_issues:
            key = (iss.code, iss.field)
            if key not in seen_codes:
                seen_codes.add(key)
                deduped_issues.append(iss)

        summary = AuditSummary(
            high=sum(1 for i in deduped_issues if i.severity == "high"),
            medium=sum(1 for i in deduped_issues if i.severity == "medium"),
            low=sum(1 for i in deduped_issues if i.severity == "low"),
            total=len(deduped_issues)
        )

        audit_id = f"audit_{uuid.uuid4().hex[:12]}"
        now_iso = datetime.now(timezone.utc).isoformat()

        response = AuditResponse(
            auditId=audit_id,
            listingId=listing_id,
            version=self.VERSION,
            status=audit_status,
            auditedAt=now_iso,
            contentHash=content_hash,
            summary=summary,
            issues=deduped_issues,
            detectors=detectors_status,
            warnings=warnings
        )

        try:
            doc = {
                "audit_id": audit_id,
                "listing_id": listing_id,
                "content_hash": content_hash,
                "version": self.VERSION,
                "audited_at": now_iso,
                "status": audit_status,
                "summary": summary.model_dump(),
                "issues": [iss.model_dump() for iss in deduped_issues],
                "detectors": detectors_status,
                "warnings": warnings,
                "created_at": datetime.now(timezone.utc)
            }
            db[self.COLLECTION].insert_one(doc)
        except Exception:
            pass

        return response

    def get_latest_audit(self, listing_id: str) -> Optional[AuditResponse]:
        db = db_live()
        doc = db[self.COLLECTION].find_one(
            {"listing_id": listing_id},
            sort=[("audited_at", -1)]
        )
        if not doc:
            return self.audit_listing(listing_id, force=False)

        issues = [Issue(**iss) for iss in doc.get("issues", [])]
        summary = AuditSummary(**doc.get("summary", {}))
        return AuditResponse(
            auditId=doc.get("audit_id", str(doc["_id"])),
            listingId=listing_id,
            version=doc.get("version", self.VERSION),
            status=doc.get("status", "completed"),
            auditedAt=doc.get("audited_at", datetime.now(timezone.utc).isoformat()),
            contentHash=doc.get("content_hash", ""),
            summary=summary,
            issues=issues,
            detectors=doc.get("detectors", {}),
            warnings=doc.get("warnings", [])
        )

    def recheck_listing(self, listing_id: str) -> Optional[AuditResponse]:
        db = db_live()
        prev_doc = db[self.COLLECTION].find_one(
            {"listing_id": listing_id},
            sort=[("audited_at", -1)]
        )
        new_audit = self.audit_listing(listing_id, force=True)
        if not new_audit:
            return None

        if prev_doc and "issues" in prev_doc:
            current_issue_keys = {(i.code, i.field) for i in new_audit.issues}
            resolved_issues: List[Issue] = []
            for raw in prev_doc["issues"]:
                prev_key = (raw.get("code"), raw.get("field"))
                if prev_key not in current_issue_keys:
                    resolved_iss = Issue(**raw)
                    resolved_iss.status = "resolved"
                    resolved_issues.append(resolved_iss)

            if resolved_issues:
                all_issues = new_audit.issues + resolved_issues
                new_audit.issues = all_issues

        return new_audit
