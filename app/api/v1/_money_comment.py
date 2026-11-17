import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.api.v1._doi_thu_ke_hoach import _so, _tien, goi_llm

CACHE_GIAY = 1800
DAI_TOI_DA = 150
CACHE_TOI_DA = 300
# khoá (shop, dữ kiện): mỗi khoảng 7/30/90 ngày giữ gợi ý riêng, đổi qua lại không gọi LLM lại
_CACHE: Dict[Tuple[str, str], Tuple[float, Dict[str, Any]]] = {}


def _pct(a: float, b: float) -> str:
    return f"{a / b * 100:.1f}".replace(".", ",") + "%" if b else "0%"


def su_that(bc: Dict[str, Any]) -> Dict[str, str]:
    """Dữ kiện từng thẻ, do code tính; LLM chỉ được dùng số trong đây."""
    f, su = bc["flow"], {}
    paid, mat = f["buyer_paid_vnd"], f["buyer_paid_vnd"] - f["net_vnd"]
    if paid > 0:
        lon = max([("phí sàn", f["platform_fee_vnd"]), ("voucher của shop", f["shop_voucher_vnd"]),
                   ("hoàn tiền", f["refund_vnd"])], key=lambda x: x[1])
        su["cost"] = f"Shop bị trừ {_pct(mat, paid)} tiền hàng ({_tien(mat)}), khoản lớn nhất là {lon[0]} {_tien(lon[1])}."
    c = bc.get("voucher_compare")
    if c:
        v = (f"Đơn có voucher thực nhận trung bình {_tien(c['with_avg_vnd'])} ({c['with_orders']} đơn), "
             f"đơn không voucher {_tien(c['without_avg_vnd'])} ({c['without_orders']} đơn); "
             f"tổng chi voucher {_tien(f['shop_voucher_vnd'])}.")
        su["voucher"] = v
    top = (bc.get("by_product") or [None])[0]
    if top and f["net_vnd"] > 0:
        su["product"] = f"Sản phẩm bán tốt nhất \"{top['title']}\" chiếm {_pct(top['net_vnd'], f['net_vnd'])} thực nhận."
    p = bc.get("pod")
    if p:
        su["pod"] = (f"Hàng in theo yêu cầu: thực nhận {_tien(p['net_vnd'])}, giá phôi {_tien(p['blank_cost_vnd'])}, "
                     f"lãi {_tien(p['profit_vnd'])} ({_pct(p['profit_vnd'], p['net_vnd'])}).")
    return su


def _loi_nhac(su: Dict[str, str]) -> str:
    return ("Bạn là cố vấn kinh doanh cho người bán nhỏ trên sàn đồ thủ công Việt Nam. "
            "Với mỗi chủ đề dưới đây, viết đúng 1 câu ngắn, tối đa 20 từ, nêu MỘT việc cụ thể người bán làm được ngay tuần này, "
            "bắt đầu bằng động từ, tiếng Việt dễ hiểu cho người mới. Tránh từ chung chung như tối ưu, nâng cao, đẩy mạnh, chiến lược. "
            "Không nhắc lại số liệu; nếu cần số thì chỉ dùng số có trong dữ kiện. "
            "Đơn có voucher thường là đơn lớn sẵn vì có mức tối thiểu, nên đừng kết luận voucher kéo thêm tiền chỉ từ so sánh trung bình. "
            f"Trả đúng JSON chỉ với các khoá {list(su)}, dạng {{\"cost\": \"...\"}}.\n\n"
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
    """Gợi ý AI cho từng thẻ; không có khoá hoặc LLM bịa số thì bỏ, FE giữ câu của luật."""
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
