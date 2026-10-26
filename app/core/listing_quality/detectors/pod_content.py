import re
from typing import Any, Dict, List
from ..schemas import Issue, Recommendation

class PodContentDetector:
    code = "pod_content"

    APPAREL_TERMS = {
        "ao-thun", "vay-dam", "quan-dai", "ao-khoac", "jacket", "ao-long",
        "set-ao-vay", "quan", "sweater", "leather", "ao-quan-bong-da",
        "áo", "quần", "váy", "đầm", "hoodie", "tee", "shirt", "skirt", "top"
    }

    DRINKWARE_TERMS = {
        "ly-tach", "ly", "tách", "cốc", "mug", "cup", "bình", "binh-giu-nhiet"
    }

    BAG_TERMS = {
        "tui", "túi", "tote", "bag", "balo", "ví", "backpack"
    }

    ART_TERMS = {
        "tranh-anh", "trang-tri", "tranh", "ảnh", "poster", "canvas", "khung"
    }

    FABRIC_KEYWORDS = [
        r"\bcotton\b", r"\bnỉ\b", r"\blen\b", r"\bvải thun\b", r"\bthun cotton\b", r"\bkaki\b", r"\bdenim\b",
        r"\bjean\b", r"\bpolyester\b", r"\bpoly\b", r"\blụa\b", r"\bvoan\b", r"\bren\b",
        r"\bmodal\b", r"\bbamboo\b", r"\bchiffon\b", r"\bspandex\b", r"\bvải\b",
        r"\bda bò\b", r"\bda\b", r"\bfleece\b", r"\blinen\b", r"\bdệt kim\b"
    ]

    SIZE_KEYWORDS = [
        r"\bsize\b", r"\bkích thước\b", r"\bkích cỡ\b", r"\bbảng size\b", r"\bsố đo\b",
        r"\bchiều dài\b", r"\bchiều rộng\b", r"\bvòng ngực\b", r"\bvòng eo\b", r"\bfit\b",
        r"\boversize\b", r"\bfreesize\b", r"\bfree size\b", r"\b\d+\s*(?:cm|kg)\b",
        r"\b(?:xs|s|m|l|xl|xxl|2xl|3xl)\b"
    ]

    CARE_KEYWORDS = [
        r"\bgiặt\b", r"\bbảo quản\b", r"\btẩy\b", r"\bủi\b", r"\blà\b",
        r"\bphơi\b", r"\bnhiệt độ\b", r"\bcare\b", r"\bwash\b"
    ]

    DRINKWARE_KEYWORDS = [
        r"\bsứ\b", r"\bthủy tinh\b", r"\bgốm\b", r"\binox\b", r"\bnhôm\b", r"\bnhựa\b",
        r"\bceramic\b", r"\bglass\b", r"\bdung tích\b", r"\b\d+\s*(?:ml|oz|lít)\b"
    ]

    def _get_combined_text(self, listing: Dict[str, Any]) -> str:
        parts = [
            str(listing.get("title") or ""),
            str(listing.get("description") or ""),
            " ".join(str(t) for t in (listing.get("tags") or [])),
            " ".join(str(c) for c in (listing.get("categories") or []))
        ]
        return " ".join(parts).lower()

    def _matches_any(self, text: str, patterns: List[str]) -> bool:
        for pat in patterns:
            if re.search(pat, text, re.IGNORECASE):
                return True
        return False

    def _determine_category_group(self, listing: Dict[str, Any], text: str) -> str:
        cats = [str(c).lower() for c in (listing.get("categories") or [])]
        for c in cats:
            if any(term in c for term in self.APPAREL_TERMS):
                return "apparel"
            if any(term in c for term in self.DRINKWARE_TERMS):
                return "drinkware"
            if any(term in c for term in self.BAG_TERMS):
                return "bag"
            if any(term in c for term in self.ART_TERMS):
                return "art"

        title = str(listing.get("title") or "").lower()
        if any(term in title for term in self.APPAREL_TERMS):
            return "apparel"
        if any(term in title for term in self.DRINKWARE_TERMS):
            return "drinkware"
        if any(term in title for term in self.BAG_TERMS):
            return "bag"
        if any(term in title for term in self.ART_TERMS):
            return "art"

        return "general"

    def evaluate(self, listing: Dict[str, Any], context: Dict[str, Any]) -> List[Issue]:
        issues: List[Issue] = []
        title_str = str(listing.get("title") or "").strip()
        desc_str = str(listing.get("description") or "").strip()
        if not title_str and not desc_str:
            return issues

        text = self._get_combined_text(listing)
        group = self._determine_category_group(listing, text)

        structured_materials = listing.get("materials") or []
        variants = context.get("variants", [])
        variant_materials = [v.get("material") for v in variants if v.get("material")]
        variant_sizes = [v.get("size") for v in variants if v.get("size")]

        desc_text = str(listing.get("description") or "").lower()
        title_clean = re.sub(r"áo\s+thun|ao-thun|t-shirt|tee", "", str(listing.get("title") or "").lower())
        mat_text = f"{desc_text} {title_clean}"

        has_material = (
            len(structured_materials) > 0
            or len(variant_materials) > 0
            or self._matches_any(mat_text, self.FABRIC_KEYWORDS)
        )

        has_size_info = (
            len(variant_sizes) > 0
            or self._matches_any(text, self.SIZE_KEYWORDS)
        )

        has_care_info = self._matches_any(text, self.CARE_KEYWORDS)

        if group == "apparel":
            if not has_material:
                issues.append(Issue(
                    id="pod_apparel_material_missing",
                    code="MATERIAL_MISSING",
                    detector=self.code,
                    severity="high",
                    field="materials",
                    status="open",
                    confidence=1.0,
                    evidence={"observed": None, "expected": "Chất liệu may mặc (cotton, nỉ, len, thun,...)"},
                    message="Sản phẩm thời trang thiếu thông tin chất liệu vải.",
                    recommendation=Recommendation(
                        action="ADD_MATERIAL",
                        message="Bổ sung chất liệu vải vào thuộc tính hoặc mô tả chi tiết sản phẩm.",
                        field_link="materials",
                        verification="Kiểm tra thông tin chất liệu vải được ghi nhận rõ ràng."
                    )
                ))

            if not has_size_info:
                issues.append(Issue(
                    id="pod_apparel_size_missing",
                    code="SIZE_INFO_MISSING",
                    detector=self.code,
                    severity="medium",
                    field="size",
                    status="open",
                    confidence=1.0,
                    evidence={"observed": None, "expected": "Bảng kích thước hoặc các phân loại size (S/M/L/...)"},
                    message="Sản phẩm thời trang chưa có hướng dẫn kích cỡ hoặc phân loại size.",
                    recommendation=Recommendation(
                        action="ADD_SIZE_GUIDE",
                        message="Thêm các phân loại kích cỡ (variants) hoặc kèm bảng thông số số đo trong mô tả.",
                        field_link="variants",
                        verification="Kiểm tra có ít nhất 1 biến thể kích cỡ hoặc hướng dẫn chọn size."
                    )
                ))

            if not has_care_info:
                issues.append(Issue(
                    id="pod_apparel_care_missing",
                    code="CARE_INSTRUCTIONS_MISSING",
                    detector=self.code,
                    severity="low",
                    field="description",
                    status="open",
                    confidence=1.0,
                    evidence={"observed": None, "expected": "Hướng dẫn giặt ủi và bảo quản trang phục"},
                    message="Mô tả chưa có hướng dẫn giặt ủi và bảo quản quần áo.",
                    recommendation=Recommendation(
                        action="ADD_CARE_INSTRUCTIONS",
                        message="Bổ sung lưu ý giặt máy/giặt tay và bảo quản hình in để sản phẩm bền màu.",
                        field_link="description",
                        verification="Kiểm tra mô tả có hướng dẫn bảo quản sản phẩm."
                    )
                ))

        elif group == "drinkware":
            has_drinkware_spec = (
                has_material
                or self._matches_any(text, self.DRINKWARE_KEYWORDS)
            )
            if not has_drinkware_spec:
                issues.append(Issue(
                    id="pod_drinkware_specs_missing",
                    code="DRINKWARE_SPECS_MISSING",
                    detector=self.code,
                    severity="medium",
                    field="description",
                    status="open",
                    confidence=1.0,
                    evidence={"observed": None, "expected": "Chất liệu (gốm sứ, thủy tinh, inox) hoặc dung tích (ml/oz)"},
                    message="Sản phẩm ly/tách thiếu thông tin chất liệu gốm sứ hoặc dung tích.",
                    recommendation=Recommendation(
                        action="ADD_DRINKWARE_SPECS",
                        message="Bổ sung chất liệu cốc (gốm, sứ, thuỷ tinh) và dung tích chứa (ml).",
                        field_link="description",
                        verification="Kiểm tra mô tả có thông số dung tích hoặc chất liệu cốc."
                    )
                ))

        elif group == "bag":
            if not has_material:
                issues.append(Issue(
                    id="pod_bag_material_missing",
                    code="BAG_MATERIAL_MISSING",
                    detector=self.code,
                    severity="medium",
                    field="materials",
                    status="open",
                    confidence=1.0,
                    evidence={"observed": None, "expected": "Chất liệu túi (canvas, vải bố, da, dù)"},
                    message="Túi xách thiếu thông tin chất liệu cấu tạo.",
                    recommendation=Recommendation(
                        action="ADD_BAG_MATERIAL",
                        message="Ghi rõ chất liệu túi như canvas, vải bố dày dặn hay da nhân tạo.",
                        field_link="materials",
                        verification="Kiểm tra thông tin chất liệu túi được bổ sung."
                    )
                ))

        return issues
