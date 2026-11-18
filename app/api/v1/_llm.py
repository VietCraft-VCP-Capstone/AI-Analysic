"""Gọi mô hình ngôn ngữ cho nhận xét F43; không có khoá hoặc lỗi thì trả (None, None).
Việc chọn nhà cung cấp (OpenAI → Gemini → Claude) nằm ở app/services/llm, dùng chung cho mọi chức năng AI."""
import re
from typing import List, Optional, Tuple

from app.services import llm


def _so(text: str) -> List[int]:
    """Các con số trong câu, bỏ dấu phân cách nghìn: '159.000đ' -> 159000."""
    return [int(re.sub(r"[.,\s]", "", m)) for m in re.findall(r"\d[\d.,]*\d|\d", text)]


def goi_llm(loi_nhac: str, gemini: Optional[str] = None) -> Tuple[Optional[str], Optional[str]]:
    """(văn bản, nhà cung cấp). `gemini` = model Gemini ưu tiên khi phải dùng dự phòng (vd bản flash-lite nhanh hơn).
    12s để cả lượt (tính sự thật ~4s + LLM) vẫn dưới timeout 20s của BE gateway."""
    return llm.generate_text(loi_nhac, timeout_s=12, gemini_models=[gemini] if gemini else None)
