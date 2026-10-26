import hashlib
import json
import os
import time
import urllib.request
from typing import Any, Dict, List, Optional, Set, Tuple

from app.services.f42 import config
from app.services.f42.content_fallback import generate_fallback_content
from app.services.f42.content_validator import validate_content_output
from app.services.f42.prompts import (
    CONTENT_OUTPUT_SCHEMA,
    SYSTEM_PROMPT,
    USER_PROMPT_TEMPLATE,
)
from app.services.f42.schemas import (
    ContentResult,
    DescriptionStructure,
    SpecItem,
    TitleItem,
)
from app.services.f42.vi_text import normalize_nfc

# In-memory Cache: key -> (timestamp, ContentResult)
_CACHE: Dict[str, Tuple[float, ContentResult]] = {}


def _get_cache_key(user_title: str, category_name: str, material: str, blank_cost: float) -> str:
    norm = f"{normalize_nfc(user_title)}|{normalize_nfc(category_name)}|{normalize_nfc(material)}|{blank_cost:.2f}".lower()
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


def _get_api_key() -> Optional[str]:
    return os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")


def _call_gemini_api(prompt_text: str, api_key: str, timeout_s: int = config.LLM_TIMEOUT_S) -> Optional[str]:
    """Gọi Gemini HTTP API tương tự LLMSeasonalService."""
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{"parts": [{"text": prompt_text}]}],
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "generationConfig": {
            "temperature": config.LLM_TEMPERATURE,
            "topP": config.LLM_TOP_P,
            "maxOutputTokens": config.LLM_MAX_OUTPUT_TOKENS,
            "responseMimeType": "application/json"
        }
    }

    models_to_try = [config.LLM_MODEL, "gemini-1.5-flash", "gemini-2.0-flash", "gemini-2.5-flash"]
    for model in models_to_try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=timeout_s) as response:
                if response.status == 200:
                    body = json.loads(response.read().decode("utf-8"))
                    candidates = body.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        if parts:
                            return parts[0].get("text", "")
        except Exception:
            continue

    return None


def generate_content(
    user_title: str,
    category_name: str,
    material: str = "",
    blank_cost: float = 0.0,
    extra_attributes: str = "",
    banned_keywords: Optional[Set[str]] = None
) -> ContentResult:
    """
    Sinh tiêu đề SEO và bài mô tả sản phẩm hoàn chỉnh:
    1. Kiểm tra cache
    2. Thử gọi LLM nếu có Gemini API Key
    3. Hậu kiểm bằng post-validator
    4. Fallback an toàn nếu offline/lỗi/không có key
    """
    banned = banned_keywords or set()
    cache_key = _get_cache_key(user_title, category_name, material, blank_cost)
    now = time.time()

    # 1. Kiểm tra Cache
    if cache_key in _CACHE:
        ts, cached_res = _CACHE[cache_key]
        if now - ts < config.CACHE_TTL_S:
            return cached_res

    tier_label = f"Mức vốn phôi {int(blank_cost):,}đ".replace(",", ".") if blank_cost > 0 else "Không có"
    seller_input_block = f"""Danh mục: {category_name}
Ý tưởng / tên sản phẩm: {user_title}
Chất liệu khai báo: {material if material else 'Không khai báo'}
Phân loại giá vốn: {tier_label}
Thuộc tính khác: {extra_attributes if extra_attributes else 'Không có'}"""

    api_key = _get_api_key()

    # 2. Thử gọi LLM nếu có key
    if api_key and len(api_key) > 5:
        user_prompt = USER_PROMPT_TEMPLATE.format(
            category_name=category_name,
            user_title=user_title,
            material=material if material else "Không khai báo",
            tier_label=tier_label,
            extra_attributes=extra_attributes if extra_attributes else "Không có",
            banned_keywords=", ".join(sorted(list(banned))[:20]) if banned else "Không có"
        )

        for attempt in range(config.LLM_MAX_RETRIES):
            raw_text = _call_gemini_api(user_prompt, api_key)
            if raw_text:
                valid_data, errors = validate_content_output(
                    raw_text,
                    seller_input_block,
                    banned
                )
                if valid_data and not errors:
                    # Chuyển đổi thành ContentResult
                    titles = [
                        TitleItem(text=t.get("text", ""), angle=t.get("angle", "balanced"))
                        for t in valid_data.get("titles", [])
                    ]
                    desc_raw = valid_data.get("description", {})
                    specs = [
                        SpecItem(label=s.get("label", ""), value=s.get("value", ""))
                        for s in desc_raw.get("specs", [])
                    ]
                    desc = DescriptionStructure(
                        intro=desc_raw.get("intro", ""),
                        specs=specs,
                        highlights=desc_raw.get("highlights", []),
                        care_guide=desc_raw.get("care_guide")
                    )
                    res = ContentResult(
                        source="llm",
                        titles=titles,
                        description=desc,
                        claims_used=valid_data.get("claims_used", []),
                        missing_info=valid_data.get("missing_info", []),
                        warnings=valid_data.get("warnings", []),
                        disclaimer="Nội dung do AI gợi ý dựa trên thông tin bạn cung cấp. Vui lòng kiểm tra lại trước khi đăng."
                    )
                    _CACHE[cache_key] = (now, res)
                    return res
                else:
                    # Retry với phản hồi lỗi
                    user_prompt += f"\nLần trước output vi phạm các lỗi: {', '.join(errors[:3])}. Hãy sửa chữa triệt để."

    # 3. Fallback khi không có API key hoặc LLM thất bại
    fallback_res = generate_fallback_content(
        user_title=user_title,
        category_name=category_name,
        material=material,
        extra_attributes=extra_attributes,
        tier_label=tier_label
    )
    _CACHE[cache_key] = (now, fallback_res)
    return fallback_res
