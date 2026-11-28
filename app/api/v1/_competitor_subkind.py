import json
import os
import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional, Pattern, Sequence, Tuple

# Cùng loại nhỏ mới là đối thủ: trên 126 sản phẩm thật (24/11/2026) luật từ khoá đưa độ đúng 45% -> 81% (kiểm chéo theo shop), LLM 84%.
LOAI_NHO: Dict[str, Dict[str, Dict[str, str]]] = json.loads(Path(__file__).with_name("competitor_subkind.json").read_text("utf-8"))


def _chuan(s: Optional[str]) -> str:
    return " ".join(unicodedata.normalize("NFC", s or "").lower().split())


def _nap_luat() -> Dict[str, List[Tuple[str, Optional[Pattern[str]]]]]:
    """{loại hàng: [[loại nhỏ, [từ khoá]], ...]}: xét theo thứ tự, danh sách rỗng là mặc định và phải đứng cuối."""
    luat = json.loads(Path(__file__).with_name("competitor_subkind_rules.json").read_text("utf-8"))
    ra = {}
    for t, ds in luat.items():
        assert all(k in LOAI_NHO.get(t, {}) and all(_chuan(w) for w in ws) for k, ws in ds), f"luật loại nhỏ sai ở {t}"
        assert all(ws for _, ws in ds[:-1]), f"mặc định [] phải đứng cuối ở {t}"
        ra[t] = [(k, re.compile(r"(?<!\w)(?:" + "|".join(re.escape(_chuan(w)) for w in ws) + r")(?!\w)") if ws else None)
                 for k, ws in ds]
    return ra


LUAT = _nap_luat()


def bat() -> bool:
    return os.environ.get("COMPETITOR_SUBKIND") != "0"


def xep(r: Dict[str, Any], mo_ta: Optional[str]) -> Optional[str]:
    """Tên trước, không khớp mới xét 300 ký tự đầu mô tả; khớp nguyên từ, phân biệt dấu. None = so đối thủ kiểu cũ."""
    ds = LUAT.get(r.get("product_type_name")) or []
    for van in (_chuan(r.get("title")), _chuan((mo_ta or "")[:300])):
        for k, mau in ds:
            if mau and mau.search(van):
                return None if k == "test" else k
    k = ds[-1][0] if ds and ds[-1][1] is None else None
    return None if k == "test" else k


def nhan_cua(dong: Sequence[Dict[str, Any]], mo_ta: Dict[str, str]) -> List[Optional[str]]:
    """Loại nhỏ từng dòng; None khi tắt cờ hoặc luật không chắc."""
    return [xep(r, mo_ta.get(r["listing_id"])) for r in dong] if bat() else [None] * len(dong)
