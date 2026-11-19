"""Route nội bộ cho BE gọi LLM: BE không giữ khoá OpenAI/Gemini, mọi lệnh gọi LLM đi qua AI service
để một nơi duy nhất lo khoá, chuyển dự phòng khi hết hạn mức và nhật ký."""

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.v1._template import ok, require_gateway
from app.services import llm

router = APIRouter(prefix="/api/internal/llm", tags=["LLM dùng chung (nội bộ)"],
                   dependencies=[Depends(require_gateway)])


class TextBody(BaseModel):
    prompt: str = Field(min_length=1, max_length=20000)
    timeout_s: float = Field(default=12, ge=1, le=30)
    max_output_tokens: int = Field(default=2048, ge=16, le=4096)


@router.post("/text")
def post_text(body: TextBody):
    """Văn bản do LLM viết (BE tự đọc JSON trong đó theo prompt của nó). Không có khoá hoặc mọi nhà cung cấp lỗi
    thì `text` là null, BE dùng nhánh dự phòng của nó."""
    text, provider = llm.generate_text(body.prompt, timeout_s=body.timeout_s, max_output_tokens=body.max_output_tokens)
    return ok({"text": text, "provider": provider})
