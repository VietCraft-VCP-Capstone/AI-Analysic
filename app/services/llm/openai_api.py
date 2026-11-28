"""
Gọi OpenAI Chat Completions (trả JSON hoặc văn bản) — nhà cung cấp chính của gói llm.

  - `parts` theo định dạng Gemini ({"text": ...} hoặc {"inline_data": {"mime_type", "data"}}) để nơi gọi
    không phải đổi cách dựng prompt; ảnh được đổi sang image_url dạng data URL.
  - Thử lần lượt các model; model không nhận temperature (dòng suy luận) trả 400 thì gửi lại không kèm.
  - Mọi lỗi (hết hạn mức 429, hết credit, model sai tên, mạng) trả None để nơi gọi chuyển sang Gemini.
"""

import json
import logging
import time
import urllib.error
import urllib.request
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

API = "https://api.openai.com/v1/chat/completions"


def _to_content(parts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for p in parts:
        if "text" in p:
            out.append({"type": "text", "text": p["text"]})
        elif "inline_data" in p:
            d = p["inline_data"]
            out.append({"type": "image_url", "image_url": {"url": f"data:{d['mime_type']};base64,{d['data']}"}})
    return out


def _generate(
    parts: List[Dict[str, Any]],
    api_key: str,
    models: List[str],
    timeout_s: float,
    temperature: float,
    max_output_tokens: int,
    json_mode: bool,
    handle: Callable[[str], Any],
    opener,
) -> Any:
    """Vòng thử model. `handle(text)` trả kết quả dùng được, hoặc None để thử model khác."""
    if not api_key:
        return None
    system = ("Trả lời bằng đúng một đối tượng JSON hợp lệ, không thêm chữ nào khác." if json_mode
              else "Trả lời ngắn gọn, đúng yêu cầu.")
    messages = [{"role": "system", "content": system}, {"role": "user", "content": _to_content(parts)}]
    deadline = time.time() + timeout_s * 1.5
    for model in dict.fromkeys(models):
        for with_temperature in (True, False):
            remaining = deadline - time.time()
            if remaining <= 1:
                return None
            body: Dict[str, Any] = {"model": model, "messages": messages, "max_completion_tokens": max_output_tokens}
            if json_mode:
                body["response_format"] = {"type": "json_object"}
            if with_temperature:
                body["temperature"] = temperature
            req = urllib.request.Request(
                API,
                data=json.dumps(body).encode("utf-8"),
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
                method="POST",
            )
            try:
                with opener(req, timeout=min(timeout_s, remaining)) as resp:
                    text = json.loads(resp.read().decode("utf-8"))["choices"][0]["message"]["content"]
                result = handle(text or "")
                if result is not None:
                    return result
                logger.warning("llm.openai_answer_rejected: %s trả lời nhưng không dùng được", model)
                break  # model trả lời nhưng không dùng được → thử model khác
            except urllib.error.HTTPError as exc:
                logger.warning("llm.openai_call_failed: %s HTTP %s", model, exc.code)
                if exc.code == 400 and with_temperature:
                    continue  # model không nhận temperature → gửi lại không kèm
                break
            except Exception as exc:  # noqa: BLE001 — mạng/JSON lỗi: thử model kế
                logger.warning("llm.openai_call_failed: %s %s: %s", model, type(exc).__name__, exc)
                break
    return None


def generate_json(
    parts: List[Dict[str, Any]],
    api_key: str,
    models: List[str],
    timeout_s: float,
    temperature: float = 0.4,
    max_output_tokens: int = 4096,
    accept: Callable[[Dict[str, Any]], bool] = lambda d: True,
    opener=urllib.request.urlopen,
) -> Optional[Dict[str, Any]]:
    """JSON đầu tiên `accept` chấp nhận, hoặc None nếu mọi model đều lỗi / hết giờ."""
    def handle(text: str) -> Optional[Dict[str, Any]]:
        data = json.loads(text) if text else None
        return data if isinstance(data, dict) and accept(data) else None

    return _generate(parts, api_key, models, timeout_s, temperature, max_output_tokens, True, handle, opener)


def generate_text(
    prompt: str,
    api_key: str,
    models: List[str],
    timeout_s: float,
    temperature: float = 0.3,
    max_output_tokens: int = 1200,
    opener=urllib.request.urlopen,
) -> Optional[str]:
    """Văn bản đầu tiên không rỗng, hoặc None nếu mọi model đều lỗi / hết giờ."""
    return _generate([{"text": prompt}], api_key, models, timeout_s, temperature, max_output_tokens, False,
                     lambda text: text.strip() or None, opener)
