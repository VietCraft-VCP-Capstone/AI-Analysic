"""
Kiểm tra nội dung AI sinh ra trước khi trả cho seller (spec F42 mục 8.6).

Nguyên tắc: một thuộc tính / khẳng định chỉ được xuất hiện nếu seller đã nhập.
Phần vi phạm bị LOẠI BỎ (không sửa chữ), lý do ghi vào `errors` để log và để
orchestrator quyết định chuyển sang nội dung dự phòng.
"""

import re
from typing import Any, Dict, Iterable, List, Set, Tuple

from app.services.f42 import config
from app.services.f42.vi_text import contains_phrase_boundary, contains_phrase_lenient, normalize_nfc

TITLE_MIN_LEN = 10
TITLE_MAX_LEN = 150
_DECOR_RE = re.compile(r"[★☆✔✓✅🔥💥⭐❤]|!!+|#{2,}")
_EMOJI_RE = re.compile("[\U0001F300-\U0001FAFF\U00002600-\U000027BF]")
# Từ đứng trước làm chất liệu thành màu/hoa văn ("màu gỗ", "vân đá", "giả da")
_NEG_PREV = ("màu ", "vân ", "giả ", "họa tiết ", "kiểu ")


# Văn bản AI sinh ra luôn có dấu → so khớp CÓ DẤU (tránh "lên"→"len", "trẻ"→"tre", "may"→"mây").
# Thông tin seller nhập có thể gõ không dấu → so khớp lỏng (có dấu hoặc không dấu).
def _mentions_material(text: str, material: str) -> bool:
    if not contains_phrase_boundary(text, material):
        return False
    low = normalize_nfc(text).lower()
    mat = normalize_nfc(material).lower()
    idx = low.find(mat)
    while idx != -1:
        if not any(low[:idx].endswith(p) for p in _NEG_PREV):
            return True
        idx = low.find(mat, idx + 1)
    return False


def find_violations(text: str, seller_text: str, banned: Iterable[str], cfg=config) -> List[str]:
    """Các khẳng định / chất liệu / từ cấm có trong `text` mà seller không nhập."""
    errors: List[str] = []
    if not text:
        return errors
    for claim in cfg.RISKY_CLAIMS:
        if contains_phrase_boundary(text, claim) and not contains_phrase_lenient(seller_text, claim):
            errors.append(f"unsupported_claim:{claim}")
    for mat in cfg.KNOWN_MATERIALS:
        if _mentions_material(text, mat) and not contains_phrase_lenient(seller_text, mat):
            errors.append(f"unsupported_material:{mat}")
    for kw in banned:
        if kw and contains_phrase_boundary(text, kw):
            errors.append(f"banned:{kw}")
    return errors


def _title_style_errors(title: str) -> List[str]:
    errs = []
    letters = [c for c in title if c.isalpha()]
    if letters and sum(c.isupper() for c in letters) / len(letters) > 0.8:
        errs.append("title_style:all_caps")
    if _DECOR_RE.search(title) or _EMOJI_RE.search(title):
        errs.append("title_style:decoration")
    if not (TITLE_MIN_LEN <= len(title) <= TITLE_MAX_LEN):
        errs.append("title_length")
    return errs


def validate_content(
    ai_data: Dict[str, Any],
    seller_text: str,
    banned: Set[str],
    material_declared: bool,
    cfg=config,
) -> Tuple[Dict[str, Any], List[str]]:
    """
    Trả (ai_data đã lọc, errors). Không bao giờ thêm chữ mới — chỉ giữ hoặc bỏ.
    - Tiêu đề vi phạm bị bỏ, trùng lặp bị bỏ.
    - Intro vi phạm → để trống.
    - Highlight vi phạm bị bỏ.
    - Spec chỉ giữ nếu giá trị có trong thông tin seller nhập.
    - Hướng dẫn bảo quản chỉ giữ khi seller khai báo chất liệu; chính sách bảo hành luôn bỏ.
    """
    errors: List[str] = []
    data = dict(ai_data)

    titles: List[str] = []
    seen: Set[str] = set()
    for t in data.get("titles") or []:
        if not isinstance(t, str) or not t.strip():
            continue
        t = normalize_nfc(t).strip()
        # Bỏ tiền tố kiểu "Tiêu đề 1:" mà model đôi khi chép lại từ ví dụ
        t = re.sub(r"^(tiêu đề\s*\d+\s*[:\-–]\s*)", "", t, flags=re.I)
        errs = find_violations(t, seller_text, banned, cfg) + _title_style_errors(t)
        key = t.lower()
        if key in seen:
            errs.append("duplicate_titles")
        if errs:
            errors.extend(f"title:{e}" for e in errs)
            continue
        seen.add(key)
        titles.append(t)
    data["titles"] = titles

    desc = dict(data.get("description") or {})
    intro = str(desc.get("intro") or "")
    intro_errs = find_violations(intro, seller_text, banned, cfg)
    if intro_errs:
        errors.extend(f"intro:{e}" for e in intro_errs)
        desc["intro"] = ""

    kept_highlights = []
    for h in desc.get("highlights") or []:
        h_errs = find_violations(str(h), seller_text, banned, cfg)
        if h_errs:
            errors.extend(f"highlight:{e}" for e in h_errs)
        else:
            kept_highlights.append(str(h))
    desc["highlights"] = kept_highlights[:5]

    kept_specs = []
    for s in desc.get("specs") or []:
        if not isinstance(s, dict):
            continue
        val = str(s.get("value") or "").strip()
        if val and contains_phrase_lenient(seller_text, val):
            kept_specs.append({"label": str(s.get("label") or ""), "value": val})
        elif val:
            errors.append(f"spec_not_in_input:{s.get('label')}")
    desc["specs"] = kept_specs

    usage = desc.get("usage_guide")
    if usage and (not material_declared or find_violations(str(usage), seller_text, banned, cfg)):
        errors.append("care_guide_without_material" if not material_declared else "care_guide:unsupported")
        desc["usage_guide"] = None
    if desc.get("warranty_policy"):
        desc["warranty_policy"] = None  # cam kết bảo hành/đổi trả chỉ seller được tự viết

    data["description"] = desc
    data["tags"] = [
        t for t in (data.get("tags") or [])
        if isinstance(t, str) and not find_violations(t, seller_text, banned, cfg)
    ]
    return data, errors
