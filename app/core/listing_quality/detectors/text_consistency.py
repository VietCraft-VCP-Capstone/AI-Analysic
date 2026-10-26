import re
from typing import Any, Dict, List
from ..schemas import Issue, Recommendation

class TextConsistencyDetector:
    code = "text_consistency"

    MATERIAL_GROUPS = {
        "cotton": ["cotton", "100% cotton", "cotton compact"],
        "polyester": ["polyester", "poly", "pe"],
        "silk": ["lụa", "silk", "phi bóng"],
        "wool": ["len", "wool", "dệt kim"],
        "leather": ["da thật", "da bò", "da cừu", "leather"],
        "ceramic": ["gốm", "sứ", "ceramic", "porcelain"],
        "glass": ["thủy tinh", "glass"]
    }

    CATEGORY_INDICATORS = {
        "drinkware": [r"\bcốc\b", r"\bly\b", r"\btách\b", r"\bmug\b", r"\bbình giữ nhiệt\b"],
        "apparel": [r"\báo thun\b", r"\báo khoác\b", r"\bváy\b", r"\bđầm\b", r"\bhoodie\b", r"\bquần\b"],
        "bag": [r"\btúi tote\b", r"\btúi xách\b", r"\bbalo\b", r"\bbackpack\b"]
    }

    CATEGORY_NAMES = {
        "drinkware": ["ly-tach", "ly tách", "cốc"],
        "apparel": ["ao-thun", "áo thun", "vay-dam", "váy đầm", "ao-khoac", "áo khoác", "set-ao-vay"],
        "bag": ["tui", "túi", "phu-kien", "phụ kiện"]
    }

    def _extract_material_group(self, text: str) -> str:
        t = text.lower()
        for group, keywords in self.MATERIAL_GROUPS.items():
            for kw in keywords:
                if re.search(r"\b" + re.escape(kw) + r"\b", t):
                    return group
        return ""

    def evaluate(self, listing: Dict[str, Any], context: Dict[str, Any]) -> List[Issue]:
        issues: List[Issue] = []
        title = str(listing.get("title") or "")
        title_lower = title.lower()

        title_material = self._extract_material_group(title_lower)
        structured_materials = [str(m).lower() for m in (listing.get("materials") or [])]
        variants = context.get("variants", [])
        variant_materials = [str(v.get("material") or "").lower() for v in variants if v.get("material")]

        all_structured_materials = structured_materials + variant_materials
        if title_material and all_structured_materials:
            for s_mat in all_structured_materials:
                s_group = self._extract_material_group(s_mat)
                if s_group and s_group != title_material:
                    issues.append(Issue(
                        id="conflict_material",
                        code="MATERIAL_CONTRADICTION",
                        detector=self.code,
                        severity="high",
                        field="materials",
                        status="open",
                        confidence=0.95,
                        evidence={
                            "title_material": title_material,
                            "structured_material": s_mat
                        },
                        message=f"Mâu thuẫn chất liệu: Tiêu đề ghi '{title_material}' nhưng thông tin cấu hình lại ghi '{s_mat}'.",
                        recommendation=Recommendation(
                            action="RESOLVE_MATERIAL_CONFLICT",
                            message="Đồng bộ lại thông tin chất liệu giữa tiêu đề và thuộc tính sản phẩm.",
                            field_link="materials",
                            verification="Kiểm tra chất liệu ở tiêu đề và thuộc tính thống nhất với nhau."
                        )
                    ))
                    break

        cats = [str(c).lower() for c in (listing.get("categories") or [])]
        for type_key, patterns in self.CATEGORY_INDICATORS.items():
            matched_indicator = any(re.search(pat, title_lower) for pat in patterns)
            if matched_indicator:
                for other_type, other_cats in self.CATEGORY_NAMES.items():
                    if other_type != type_key:
                        in_other_cat = any(any(oc in c for oc in other_cats) for c in cats)
                        in_own_cat = any(any(tc in c for tc in self.CATEGORY_NAMES[type_key]) for c in cats)
                        if in_other_cat and not in_own_cat:
                            issues.append(Issue(
                                id=f"conflict_category_{type_key}",
                                code="CATEGORY_CONTRADICTION",
                                detector=self.code,
                                severity="high",
                                field="categories",
                                status="open",
                                confidence=0.92,
                                evidence={
                                    "title_indicated_type": type_key,
                                    "assigned_categories": cats
                                },
                                message=f"Mâu thuẫn ngành hàng: Tiêu đề thuộc nhóm '{type_key}' nhưng sản phẩm đang chọn ngành hàng khác.",
                                recommendation=Recommendation(
                                    action="CORRECT_CATEGORY_ASSIGNMENT",
                                    message="Kiểm tra lại danh mục ngành hàng để đảm bảo đúng với loại sản phẩm thực tế.",
                                    field_link="categories",
                                    verification="Kiểm tra danh mục sản phẩm trùng khớp với tên gọi trên tiêu đề."
                                )
                            ))
                            break

        return issues
