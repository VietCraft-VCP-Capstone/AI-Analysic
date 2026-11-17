"""Gọi mô hình ngôn ngữ cho nhận xét F43; không có khoá hoặc lỗi thì trả (None, None)."""
import json
import os
import re
import urllib.request
from typing import Callable, Dict, List, Optional, Tuple

MO_HINH_CLAUDE = os.getenv("COMPETITOR_BRIEF_MODEL", "claude-sonnet-5-5")


def _so(text: str) -> List[int]:
    """Các con số trong câu, bỏ dấu phân cách nghìn: '159.000đ' -> 159000."""
    return [int(re.sub(r"[.,\s]", "", m)) for m in re.findall(r"\d[\d.,]*\d|\d", text)]


def _goi(url: str, body: Dict, headers: Dict[str, str], lay: Callable[[Dict], str]) -> Optional[str]:
    try:
        req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"),
                                     headers={"Content-Type": "application/json", **headers}, method="POST")
        # 12s để cả lượt (tính sự thật ~4s + LLM) vẫn dưới timeout 20s của BE gateway.
        with urllib.request.urlopen(req, timeout=12) as r:
            return lay(json.loads(r.read().decode("utf-8")))
    except Exception:
        return None


def goi_llm(loi_nhac: str, gemini: str = "gemini-3.5-flash") -> Tuple[Optional[str], Optional[str]]:
    """(văn bản, nhà cung cấp) từ khoá đầu tiên có trong môi trường; không có khoá hoặc lỗi thì (None, None)."""
    if os.getenv("ANTHROPIC_API_KEY"):
        return _goi("https://api.anthropic.com/v1/messages",
                    {"model": MO_HINH_CLAUDE, "max_tokens": 1200, "messages": [{"role": "user", "content": loi_nhac}]},
                    {"x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01"},
                    lambda b: b["content"][0]["text"]), f"anthropic/{MO_HINH_CLAUDE}"
    khoa = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if khoa:
        m = gemini
        return _goi(f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={khoa}",
                    {"contents": [{"parts": [{"text": loi_nhac}]}], "generationConfig": {"temperature": 0.3}},
                    {}, lambda b: b["candidates"][0]["content"]["parts"][0]["text"]), f"gemini/{m}"
    if os.getenv("OPENAI_API_KEY"):
        return _goi("https://api.openai.com/v1/chat/completions",
                    {"model": "gpt-4o-mini", "temperature": 0.3, "messages": [{"role": "user", "content": loi_nhac}]},
                    {"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
                    lambda b: b["choices"][0]["message"]["content"]), "openai/gpt-4o-mini"
    return None, None
