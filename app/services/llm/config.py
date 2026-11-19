"""Cấu hình dùng chung cho mọi chức năng AI gọi LLM. Khoá chỉ lấy từ môi trường (app/.env), không nằm trong code."""

import os
from typing import List


def _models(env: str, default: str) -> List[str]:
    return [m.strip() for m in os.getenv(env, default).split(",") if m.strip()]


# OpenAI là nhà cung cấp chính; mỗi model thử lần lượt (cách nhau dấu phẩy).
OPENAI_MODELS: List[str] = _models("LLM_OPENAI_MODELS", "gpt-4o-mini")

# Gemini là dự phòng khi OpenAI lỗi/hết hạn mức. gemini-2.5-flash đã ngừng cấp cho key mới (404);
# gemini-flash-latest hay hết hạn mức (429). Giữ danh sách ngắn để không cộng dồn timeout.
GEMINI_MODELS: List[str] = _models(
    "LLM_GEMINI_MODELS",
    "gemini-3.5-flash,gemini-3-flash-preview,gemini-3.1-flash-lite,gemini-flash-lite-latest",
)

# Claude chỉ dùng cho văn bản ngắn (nhận xét F43), sau OpenAI và Gemini.
ANTHROPIC_MODEL: str = os.getenv("COMPETITOR_BRIEF_MODEL", "claude-sonnet-5-5")
