"""
Gọi Gemini trả JSON — dùng chung cho viết nội dung (F42) và nhận diện sản phẩm từ ảnh.

  - Thử lần lượt model chính rồi model dự phòng trong một khoảng thời gian tối đa
    (model hay hết hạn mức → 429, model cũ ngừng cấp cho key mới → 404).
  - Tắt "suy nghĩ" (thinkingBudget=0): model 3.x suy nghĩ ăn hết maxOutputTokens làm JSON bị cắt cụt.
    Model không nhận tham số này (vd gemini-flash-lite-latest trả 400) thì gửi lại không kèm.
  - Nhận cả ảnh (inline_data) cho nhận diện sản phẩm.
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


def _extract_json(body: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    cands = body.get("candidates") or []
    parts = (cands[0].get("content") or {}).get("parts") or [] if cands else []
    txt = "".join(p.get("text", "") for p in parts if not p.get("thought")).strip()
    if txt.startswith("```"):
        txt = re.sub(r"^```[a-z]*\s*", "", txt)
        txt = re.sub(r"\s*```$", "", txt)
    data = json.loads(txt) if txt else None
    if isinstance(data, list) and data and all(isinstance(x, dict) for x in data):
        return {"items": data}   # model trả mảng (vd mỗi ảnh một object) — để nơi gọi tự gộp
    return data if isinstance(data, dict) else None


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
    if not api_key:
        return None
    gen = {"temperature": temperature, "maxOutputTokens": max_output_tokens, "responseMimeType": "application/json"}
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
                    data = _extract_json(json.loads(resp.read().decode("utf-8")))
                if data is not None and accept(data):
                    return data
                logger.warning("f42.gemini_answer_rejected: %s trả lời nhưng không dùng được: %s", model, str(data)[:200])
                break  # model trả lời nhưng không dùng được → thử model khác
            except urllib.error.HTTPError as exc:
                logger.warning("f42.gemini_call_failed: %s HTTP %s", model, exc.code)
                if exc.code == 400 and thinking_off:
                    continue  # model không nhận thinkingConfig → gửi lại không kèm
                break
            except Exception as exc:  # noqa: BLE001 — mạng/JSON lỗi: thử model kế
                logger.warning("f42.gemini_call_failed: %s %s: %s", model, type(exc).__name__, exc)
                break
    return None
