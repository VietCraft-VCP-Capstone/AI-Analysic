"""
Gọi Gemini (trả JSON hoặc văn bản) — nhà cung cấp dự phòng của gói llm.

  - Thử lần lượt model chính rồi model dự phòng trong một khoảng thời gian tối đa
    (model hay hết hạn mức → 429, model cũ ngừng cấp cho key mới → 404).
  - Tắt "suy nghĩ" (thinkingBudget=0): model 3.x suy nghĩ ăn hết maxOutputTokens làm JSON bị cắt cụt.
    Model không nhận tham số này (vd gemini-flash-lite-latest trả 400) thì gửi lại không kèm.
  - Nhận cả ảnh (inline_data) cho nhận diện sản phẩm.
  - Khoá gửi qua header x-goog-api-key, không đưa vào URL (URL hay bị ghi vào log).
"""

import json
import logging
import re
import time
import urllib.error
import urllib.request
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


def _text_of(body: Dict[str, Any]) -> str:
    cands = body.get("candidates") or []
    parts = (cands[0].get("content") or {}).get("parts") or [] if cands else []
    return "".join(p.get("text", "") for p in parts if not p.get("thought")).strip()


def _extract_json(body: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    txt = _text_of(body)
    if txt.startswith("```"):
        txt = re.sub(r"^```[a-z]*\s*", "", txt)
        txt = re.sub(r"\s*```$", "", txt)
    data = json.loads(txt) if txt else None
    if isinstance(data, list) and data and all(isinstance(x, dict) for x in data):
        return {"items": data}   # model trả mảng (vd mỗi ảnh một object) — để nơi gọi tự gộp
    return data if isinstance(data, dict) else None


def _generate(
    parts: List[Dict[str, Any]],
    api_key: str,
    models: List[str],
    timeout_s: float,
    temperature: float,
    max_output_tokens: int,
    json_mode: bool,
    handle: Callable[[Dict[str, Any]], Any],
    opener,
) -> Any:
    """Vòng thử model. `handle(body)` trả kết quả dùng được, hoặc None để thử model khác."""
    if not api_key:
        return None
    gen: Dict[str, Any] = {"temperature": temperature, "maxOutputTokens": max_output_tokens}
    if json_mode:
        gen["responseMimeType"] = "application/json"
    deadline = time.time() + timeout_s * 1.5
    for model in dict.fromkeys(models):
        for thinking_off in (True, False):
            remaining = deadline - time.time()
            if remaining <= 1:
                return None
            cfg = {**gen, "thinkingConfig": {"thinkingBudget": 0}} if thinking_off else gen
            req = urllib.request.Request(
                API.format(model=model),
                data=json.dumps({"contents": [{"parts": parts}], "generationConfig": cfg}).encode("utf-8"),
                headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
                method="POST",
            )
            try:
                with opener(req, timeout=min(timeout_s, remaining)) as resp:
                    result = handle(json.loads(resp.read().decode("utf-8")))
                if result is not None:
                    return result
                logger.warning("llm.gemini_answer_rejected: %s trả lời nhưng không dùng được", model)
                break  # model trả lời nhưng không dùng được → thử model khác
            except urllib.error.HTTPError as exc:
                logger.warning("llm.gemini_call_failed: %s HTTP %s", model, exc.code)
                if exc.code == 400 and thinking_off:
                    continue  # model không nhận thinkingConfig → gửi lại không kèm
                break
            except Exception as exc:  # noqa: BLE001 — mạng/JSON lỗi: thử model kế
                logger.warning("llm.gemini_call_failed: %s %s: %s", model, type(exc).__name__, exc)
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
    def handle(body: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        data = _extract_json(body)
        return data if data is not None and accept(data) else None

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
                     lambda body: _text_of(body) or None, opener)
