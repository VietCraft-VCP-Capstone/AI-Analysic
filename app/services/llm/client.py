"""
Điểm gọi LLM duy nhất của toàn bộ chức năng AI (F42, nhận diện ảnh, Seasonal, nhận xét F43, endpoint cho BE).

Thứ tự: OpenAI (chính) → Gemini (dự phòng) → Claude (chỉ văn bản). Nhà cung cấp lỗi, hết hạn mức hoặc
hết credit thì tự chuyển sang cái kế; không có khoá nào thì trả None để nơi gọi dùng nhánh dự phòng không-LLM.

Khoá đọc từ môi trường: OPENAI_API_KEY, GEMINI_API_KEY + GEMINI_API_KEY_2 (dự phòng, hoặc GOOGLE_API_KEY), ANTHROPIC_API_KEY.
BE không giữ khoá LLM: BE gọi qua AI service (endpoint /api/v1/llm/json).
"""

import json
import logging
import os
import urllib.request
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.services.llm import config, gemini_api, openai_api

logger = logging.getLogger(__name__)


def openai_key() -> Optional[str]:
    return os.getenv("OPENAI_API_KEY") or None


def gemini_keys() -> List[str]:
    """Các khoá Gemini theo thứ tự thử: GEMINI_API_KEY, GEMINI_API_KEY_2 (dự phòng), GOOGLE_API_KEY."""
    keys = [os.getenv(n, "").strip() for n in ("GEMINI_API_KEY", "GEMINI_API_KEY_2", "GOOGLE_API_KEY")]
    return list(dict.fromkeys(k for k in keys if k))


def anthropic_key() -> Optional[str]:
    return os.getenv("ANTHROPIC_API_KEY") or None


def available() -> bool:
    """Có ít nhất một khoá LLM hợp lệ để gọi."""
    return any(k and len(k) > 15 for k in [openai_key(), *gemini_keys(), anthropic_key()])


def generate_json(
    parts: List[Dict[str, Any]],
    timeout_s: float = 12,
    temperature: float = 0.4,
    max_output_tokens: int = 4096,
    accept: Callable[[Dict[str, Any]], bool] = lambda d: True,
    gemini_models: Optional[List[str]] = None,
) -> Optional[Dict[str, Any]]:
    """JSON từ OpenAI; không có khoá hoặc OpenAI lỗi/hết hạn mức thì thử Gemini; cả hai lỗi thì None.
    `parts` theo định dạng Gemini: {"text": ...} hoặc {"inline_data": {"mime_type", "data"}} (ảnh)."""
    common = dict(timeout_s=timeout_s, temperature=temperature, max_output_tokens=max_output_tokens, accept=accept)
    key = openai_key()
    if key:
        data = openai_api.generate_json(parts, key, config.OPENAI_MODELS, **common)
        if data is not None:
            return data
        logger.warning("llm.fallback_to_gemini")
    for gkey in gemini_keys():
        data = gemini_api.generate_json(parts, gkey, gemini_models or config.GEMINI_MODELS, **common)
        if data is not None:
            return data
    return None


def _anthropic_text(prompt: str, api_key: str, timeout_s: float, max_tokens: int) -> Optional[str]:
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps({"model": config.ANTHROPIC_MODEL, "max_tokens": max_tokens,
                         "messages": [{"role": "user", "content": prompt}]}).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-api-key": api_key, "anthropic-version": "2023-06-01"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            return json.loads(resp.read().decode("utf-8"))["content"][0]["text"] or None
    except Exception as exc:  # noqa: BLE001
        logger.warning("llm.anthropic_call_failed: %s: %s", type(exc).__name__, exc)
        return None


def generate_text(
    prompt: str,
    timeout_s: float = 12,
    temperature: float = 0.3,
    max_output_tokens: int = 1200,
    gemini_models: Optional[List[str]] = None,
) -> Tuple[Optional[str], Optional[str]]:
    """(văn bản, tên nhà cung cấp) từ nhà cung cấp đầu tiên trả được; không có khoá hoặc đều lỗi thì (None, None)."""
    key = openai_key()
    if key:
        text = openai_api.generate_text(prompt, key, config.OPENAI_MODELS, timeout_s, temperature, max_output_tokens)
        if text:
            return text, "openai"
    for gkey in gemini_keys():
        text = gemini_api.generate_text(prompt, gkey, gemini_models or config.GEMINI_MODELS, timeout_s, temperature, max_output_tokens)
        if text:
            return text, "gemini"
    akey = anthropic_key()
    if akey:
        text = _anthropic_text(prompt, akey, timeout_s, max_output_tokens)
        if text:
            return text, f"anthropic/{config.ANTHROPIC_MODEL}"
    return None, None
