import json
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from app.services.f42 import config
from app.services.f42.vi_text import (
    contains_phrase_boundary,
    contains_phrase_lenient,
    normalize_nfc,
    strip_accents,
)


def _has_emoji_or_decorative(text: str) -> bool:
    """Kiểm tra có chứa emoji hoặc ký tự trang trí cấm."""
    bad_chars = ["★", "☆", "✔", "✓", "✗", "✘", "⚡", "🔥", "✨", "❤️", "💖", "###", "@@@"]
    if any(c in text for c in bad_chars):
        return True
    # Kiểm tra dải Unicode Emoji
    emoji_pattern = re.compile(
        "[\U00010000-\U0010ffff]|[\u2600-\u27bf]",
        flags=re.UNICODE
    )
    return bool(emoji_pattern.search(text))


def validate_content_output(
    output_data: Any,
    seller_input_text: str,
    banned_keywords: Set[str],
    risky_claims: List[str] = config.RISKY_CLAIMS,
    known_materials: List[str] = config.KNOWN_MATERIALS
) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    """
    Post-validator kiểm tra 10 lỗi vi phạm nguyên tắc trung thực và quy chuẩn SEO.
    Trả về: (data_dict nếu hợp lệ, danh sách mã lỗi).
    """
    errors: List[str] = []

    # 1. Parse JSON nếu đầu vào là string
    data: Dict[str, Any] = {}
    if isinstance(output_data, str):
        cleaned_str = output_data.strip()
        if cleaned_str.startswith("```json"):
            cleaned_str = cleaned_str[7:]
        if cleaned_str.startswith("```"):
            cleaned_str = cleaned_str[3:]
        if cleaned_str.endswith("```"):
            cleaned_str = cleaned_str[:-3]
        cleaned_str = cleaned_str.strip()
        try:
            data = json.loads(cleaned_str)
        except Exception as e:
            return None, [f"invalid_json:{str(e)[:50]}"]
    elif isinstance(output_data, dict):
        data = output_data
    else:
        return None, ["invalid_json:not_a_dict_or_string"]

    # 2. Kiểm tra schema cơ bản
    required_keys = ["titles", "description", "claims_used", "missing_info", "warnings"]
    for k in required_keys:
        if k not in data:
            errors.append(f"schema_missing_key:{k}")

    titles = data.get("titles", [])
    desc = data.get("description", {})

    # 3. Kiểm tra số lượng và độ dài tiêu đề
    if not isinstance(titles, list) or len(titles) != 5:
        errors.append(f"titles_count:{len(titles) if isinstance(titles, list) else 0}")
    else:
        seen_titles = set()
        for idx, t_obj in enumerate(titles):
            t_text = t_obj.get("text", "") if isinstance(t_obj, dict) else str(t_obj)
            t_text = normalize_nfc(t_text).strip()
            
            # Độ dài tiêu đề 40-120 ký tự
            if len(t_text) < 40 or len(t_text) > 120:
                errors.append(f"title_length:idx_{idx}_len_{len(t_text)}")
            
            # Title style: không ALL CAPS, không emoji
            if t_text.isupper() and len(t_text) > 10:
                errors.append(f"title_style_all_caps:idx_{idx}")
            if _has_emoji_or_decorative(t_text):
                errors.append(f"title_style_emoji:idx_{idx}")

            # Trùng lặp
            t_norm = strip_accents(t_text)
            if t_norm in seen_titles:
                errors.append(f"duplicate_titles:idx_{idx}")
            seen_titles.add(t_norm)

    # 4. Tập hợp toàn bộ text của output để kiểm tra rò rỉ khẳng định / từ cấm
    all_output_text_parts: List[str] = []
    if isinstance(titles, list):
        for t_obj in titles:
            all_output_text_parts.append(t_obj.get("text", "") if isinstance(t_obj, dict) else str(t_obj))
    if isinstance(desc, dict):
        all_output_text_parts.append(desc.get("intro", ""))
        for s in desc.get("specs", []):
            if isinstance(s, dict):
                all_output_text_parts.append(f"{s.get('label', '')} {s.get('value', '')}")
        for h in desc.get("highlights", []):
            all_output_text_parts.append(str(h))
        if desc.get("care_guide"):
            all_output_text_parts.append(str(desc.get("care_guide")))

    full_output_text = " ".join(all_output_text_parts)
    full_input_text = normalize_nfc(seller_input_text)

    # 5. Kiểm tra từ cấm (banned_keywords)
    for b in banned_keywords:
        b_clean = normalize_nfc(b).strip()
        if b_clean and contains_phrase_lenient(full_output_text, b_clean):
            errors.append(f"banned:{b_clean}")

    # 6. Kiểm tra khẳng định rủi ro (unsupported_claim)
    for claim in risky_claims:
        if contains_phrase_lenient(full_output_text, claim):
            # Nếu input không có cụm này thì vi phạm
            if not contains_phrase_lenient(full_input_text, claim):
                errors.append(f"unsupported_claim:{claim}")

    # 7. Kiểm tra chất liệu không được khai báo (unsupported_material)
    for mat in known_materials:
        if contains_phrase_boundary(full_output_text, mat):
            if not contains_phrase_boundary(full_input_text, mat):
                errors.append(f"unsupported_material:{mat}")

    # 8. care_guide_without_material
    care_guide = desc.get("care_guide") if isinstance(desc, dict) else None
    if care_guide:
        # Kiểm tra xem seller có khai báo chất liệu nào trong input không
        has_mat_in_input = any(contains_phrase_boundary(full_input_text, m) for m in known_materials)
        if not has_mat_in_input:
            errors.append("care_guide_without_material")

    # 9. claims_used_not_in_input
    claims_used = data.get("claims_used", [])
    if isinstance(claims_used, list):
        for c in claims_used:
            c_str = normalize_nfc(str(c)).strip()
            if c_str and not contains_phrase_lenient(full_input_text, c_str):
                errors.append(f"claims_used_not_in_input:{c_str}")

    return (data if not errors else None), errors
