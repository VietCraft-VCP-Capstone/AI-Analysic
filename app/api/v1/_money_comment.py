import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.api.v1._llm import _so, goi_llm
from app.api.v1._money_voucher import LOAI

CACHE_GIAY = 1800
DAI_TOI_DA = 150
CACHE_TOI_DA = 300
# khoá (shop, dữ kiện): mỗi khoảng 7/30/90 ngày giữ gợi ý riêng, đổi qua lại không gọi LLM lại
_CACHE: Dict[Tuple[str, str], Tuple[float, Dict[str, Any]]] = {}


def su_that(bc: Dict[str, Any]) -> Dict[str, str]:
    """Dữ kiện cho gợi ý voucher tiếp theo, do code tính; LLM chỉ được dùng số trong đây."""
    k = bc.get("voucher_stock") or {}
    if not k.get("suggest"):
        return {}
    g = k["suggest"]
    viec = {"keep": f"giữ mã {g.get('code')} đang chạy", "reactivate": f"bật lại mã {g.get('code')}"}.get(
        g.get("action"), f"tạo mã {LOAI.get(g['type'], g['type'])} mới")
    return {"next_voucher": f"Việc nên làm: {viec}. Kho mã: {k['total']} mã, đã dùng {k['used']}/{k['limit']} lượt, "
                            f"{k['idle']} mã ít dùng. {k['suggest']['reason']}"}


def _loi_nhac(su: Dict[str, str]) -> str:
    return ("Bạn là cố vấn kinh doanh cho người bán nhỏ trên sàn thương mại điện tử Việt Nam. "
            "Viết đúng 1 câu ngắn, tối đa 25 từ, tiếng Việt dễ hiểu: khuyên đúng việc ghi ở 'Việc nên làm' và vì sao, không gợi ý việc hay loại voucher khác. "
            "Tránh từ chung chung như tối ưu, nâng cao, đẩy mạnh, chiến lược. Nếu cần số thì chỉ dùng số có trong dữ kiện. "
            "Trả đúng JSON dạng {\"next_voucher\": \"...\"}.\n\n"
            + "\n".join(f"{k}: {v}" for k, v in su.items()))


def _doc_json(text: str) -> Optional[Dict[str, Any]]:
    try:
        doc = json.loads(text[text.index("{"): text.rindex("}") + 1])
    except ValueError:
        return None
    return doc if isinstance(doc, dict) else None


def _hop_le(cau: Any, su: Dict[str, str]) -> bool:
    if not isinstance(cau, str) or not 0 < len(cau.strip()) <= DAI_TOI_DA:
        return False
    return set(_so(cau)) <= set(_so(" ".join(su.values()))) | set(range(11))


def goi_y(shop_id: str, bc: Dict[str, Any]) -> Dict[str, Any]:
    """Gợi ý AI cho voucher tiếp theo; không có khoá hoặc LLM bịa số thì bỏ, FE giữ câu của luật."""
    su = su_that(bc)
    khoa = json.dumps(su, ensure_ascii=False)
    co = _CACHE.get((shop_id, khoa))
    if co and time.time() - co[0] < CACHE_GIAY:
        return co[1]
    # flash-lite ~1,5s; bản 3.5-flash mất >12s nên bị timeout
    van_ban, nguon = goi_llm(_loi_nhac(su), "gemini-3.1-flash-lite") if su else (None, None)
    doc = (_doc_json(van_ban) if van_ban else None) or {}
    tips = {k: doc[k].strip() for k in su if _hop_le(doc.get(k), su)}
    kq = {"source": "llm" if tips else "none", "provider": nguon if tips else None, "tips": tips}
    if tips:  # lỗi mạng/LLM thì lần sau gọi lại, không giữ kết quả rỗng
        if len(_CACHE) >= CACHE_TOI_DA:
            _CACHE.clear()
        _CACHE[(shop_id, khoa)] = (time.time(), kq)
    return kq
