"""
OCR Căn cước công dân (CCCD) — trích xuất thông tin + kiểm tra định dạng / chất lượng ảnh.

Hỗ trợ: CCCD mã vạch, CCCD gắn chip (2021) và thẻ Căn cước mẫu 2024.
Kết quả chỉ để TỰ ĐIỀN form và hỗ trợ admin đối soát, không có giá trị xác minh danh tính.

Thiết kế:
- Nhãn trường được so khớp trên bản chữ HOA KHÔNG DẤU (EasyOCR hay mất dấu), giá trị
  được cắt từ bản gốc theo cùng vị trí (bảng bỏ dấu 1-1 nên độ dài không đổi).
- Giá trị một trường dừng tại nhãn của trường kế tiếp — không cắt theo nội dung
  (bản cũ cắt tại chữ "Nam"/"Nữ" làm mất tên "NGUYỄN HOÀI NAM").
- Đối chiếu chéo số CCCD (mã thế kỷ + giới tính + 2 số cuối năm sinh) với ngày sinh,
  giới tính đọc được; đọc dải MRZ mặt sau thẻ chip và kiểm tra chữ số kiểm tra ICAO 9303.
"""

import logging
import re
import threading
import unicodedata
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger("cccd_ocr")

# ── EasyOCR: nạp lười, an toàn khi nhiều request đến cùng lúc ───────────────
_reader = None
_reader_lock = threading.Lock()


def _get_reader():
    global _reader
    if _reader is None:
        with _reader_lock:
            if _reader is None:
                import easyocr
                _reader = easyocr.Reader(["vi", "en"], gpu=False)
                logger.info("EasyOCR reader initialized (vi + en, CPU)")
    return _reader


# ── Mã tỉnh/thành phố (3 số đầu CCCD) theo Thông tư 07/2016/TT-BCA ─────────
VALID_PROVINCE_CODES = {
    "001", "002", "004", "006", "008", "010", "011", "012", "014", "015",
    "017", "019", "020", "022", "024", "025", "026", "027", "030", "031",
    "033", "034", "035", "036", "037", "038", "040", "042", "044", "045",
    "046", "048", "049", "051", "052", "054", "056", "058", "060", "062",
    "064", "066", "067", "068", "070", "072", "074", "075", "077", "079",
    "080", "082", "083", "084", "086", "087", "089", "091", "092", "093",
    "094", "095", "096",
}

# Chữ số thứ 4: mã thế kỷ sinh + giới tính (chẵn = nam, lẻ = nữ)
_CENTURY_BY_DIGIT = {0: 1900, 1: 1900, 2: 2000, 3: 2000, 4: 2100, 5: 2100, 6: 2200, 7: 2200, 8: 1800, 9: 1800}


# ═══════════════════════════════════════════════════════════════════════════
# 0. CHUẨN HÓA CHỮ
# ═══════════════════════════════════════════════════════════════════════════
_SRC = "ÀÁẢÃẠĂẮẰẲẴẶÂẤẦẨẪẬĐÈÉẺẼẸÊẾỀỂỄỆÌÍỈĨỊÒÓỎÕỌÔỐỒỔỖỘƠỚỜỞỠỢÙÚỦŨỤƯỨỪỬỮỰỲÝỶỸỴ"
_DST = "AAAAAAAAAAAAAAAAADEEEEEEEEEEEIIIIIOOOOOOOOOOOOOOOOOUUUUUUUUUUUYYYYY"
_UNACCENT = str.maketrans(_SRC, _DST)


def _nfc(text: str) -> str:
    return unicodedata.normalize("NFC", text or "")


def _norm(text: str) -> str:
    """HOA + bỏ dấu, GIỮ NGUYÊN độ dài để vị trí khớp với chuỗi gốc."""
    return _nfc(text).upper().translate(_UNACCENT)


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


_SEP = r"[\s/\-:|.,;]*"

# Nhãn trường (trên bản HOA không dấu). Thứ tự không quan trọng.
LABELS: Dict[str, str] = {
    "name": r"HO,?\s*(?:VA|CHU\s*DEM\s*VA)\s*TEN(?:\s*KHAI\s*SINH)?|FULL\s*NAME|SURNAME[A-Z ,]*NAME",
    "dob": r"NGAY,?\s*THANG,?\s*NAM\s*SINH|NGAY\s*SINH|DATE\s*OF\s*BIRTH",
    "sex": r"GIOI\s*TINH|(?<![A-Z])SEX(?![A-Z])",
    "nationality": r"QUOC\s*TICH|NATIONALITY",
    "origin": r"QUE\s*QUAN|PLACE\s*OF\s*ORIGIN",
    "residence": r"NOI\s*THUONG\s*TRU|NOI\s*CU\s*TRU|PLACE\s*OF\s*RESIDENCE",
    "birth_reg": r"NOI\s*DANG\s*KY\s*KHAI\s*SINH|PLACE\s*OF\s*BIRTH",
    "expiry": r"CO\s*GIA\s*TRI\s*DEN|NGAY,?\s*THANG,?\s*NAM\s*HET\s*HAN|DATE\s*OF\s*EXPIRY",
    "issue": r"NGAY,?\s*THANG,?\s*NAM\s*CAP|DATE\s*OF\s*ISSUE",
    "ident": r"DAC\s*DIEM\s*NHAN\s*DANG|PERSONAL\s*IDENTIFICATION(?!\s*NUMBER)",
    "id_label": r"SO\s*DINH\s*DANH\s*CA\s*NHAN|PERSONAL\s*IDENTIFICATION\s*NUMBER|(?<![A-Z])(?:SO|NO)(?![A-Z])",
}
_LABEL_RE = {k: re.compile(v) for k, v in LABELS.items()}
_ANY_LABEL = re.compile("|".join(f"(?:{v})" for v in LABELS.values()))
# Nhãn dùng để dừng giá trị (không gồm "SO"/"NO" đứng riêng vì quá phổ biến trong địa chỉ)
_STOP_LABEL = re.compile("|".join(f"(?:{v})" for k, v in LABELS.items() if k != "id_label")
                         + r"|SO\s*DINH\s*DANH|PERSONAL\s*IDENTIFICATION\s*NUMBER")


def _strip_leading_labels(original: str) -> str:
    """Bỏ các nhãn phụ / ký tự phân cách ở đầu chuỗi ("/ Full name: ...")."""
    s = original
    while True:
        s2 = re.sub(r"^" + _SEP, "", s)
        m = _STOP_LABEL.match(_norm(s2))
        if m and m.start() == 0 and m.end() > 0:
            s2 = s2[m.end():]
        if s2 == s:
            return s.strip()
        s = s2


def _cut_at_next_label(original: str) -> str:
    m = _STOP_LABEL.search(_norm(original))
    return original[:m.start()] if m else original


def _value_after(texts: List[str], key: str, max_next_blocks: int = 1) -> Optional[str]:
    """Giá trị của trường `key`: phần sau nhãn trong cùng block, hoặc block kế tiếp."""
    label = _LABEL_RE[key]
    for i, text in enumerate(texts):
        m = label.search(_norm(text))
        if not m:
            continue
        rest = _clean_text(_cut_at_next_label(_strip_leading_labels(text[m.end():])))
        rest = re.sub(r"^" + _SEP + "|" + _SEP + "$", "", rest)
        if len(rest) > 1:
            return rest
        parts: List[str] = []
        for nxt in texts[i + 1:i + 1 + max_next_blocks]:
            n = _norm(nxt)
            lead = _STOP_LABEL.search(n)
            if lead and lead.start() <= 2:
                break
            parts.append(_cut_at_next_label(nxt))
            if lead:
                break
        val = re.sub(r"^" + _SEP + "|" + _SEP + "$", "", _clean_text(" ".join(parts)))
        if len(val) > 1:
            return val
        # Chưa có giá trị: EasyOCR hay tách "Giới tính" | "Sex: Nam" thành 2 block,
        # nên tìm tiếp ở block nhãn kế tiếp thay vì bỏ cuộc.
    return None


# ═══════════════════════════════════════════════════════════════════════════
# 1. XÁC THỰC SỐ CCCD
# ═══════════════════════════════════════════════════════════════════════════
def validate_cccd_number(raw: str) -> Dict[str, Any]:
    digits = re.sub(r"\D", "", raw or "")
    result: Dict[str, Any] = {
        "is_valid": False,
        "cleaned": digits,
        "province_code": None,
        "gender_digit": None,
        "gender": None,
        "birth_year_suffix": None,
        "birth_year": None,
        "errors": [],
    }
    if len(digits) != 12:
        result["errors"].append(f"Số CCCD phải đúng 12 chữ số, hiện có {len(digits)} số.")
        return result

    province_code = digits[:3]
    gender_digit = int(digits[3])
    birth_year_suffix = digits[4:6]
    result.update(
        province_code=province_code,
        gender_digit=gender_digit,
        birth_year_suffix=birth_year_suffix,
        gender="Nam" if gender_digit % 2 == 0 else "Nữ",
        birth_year=_CENTURY_BY_DIGIT[gender_digit] + int(birth_year_suffix),
    )
    if province_code not in VALID_PROVINCE_CODES:
        result["errors"].append(f"Mã tỉnh '{province_code}' không nằm trong danh sách hợp lệ.")
    if result["birth_year"] > date.today().year or result["birth_year"] < 1900:
        result["errors"].append("Mã thế kỷ / năm sinh trong số CCCD không hợp lệ.")
    result["is_valid"] = not result["errors"]
    return result


# ═══════════════════════════════════════════════════════════════════════════
# 2. KIỂM TRA CHẤT LƯỢNG ẢNH
# ═══════════════════════════════════════════════════════════════════════════
def check_image_quality(img_array: np.ndarray) -> Dict[str, Any]:
    import cv2

    h, w = img_array.shape[:2]
    result: Dict[str, Any] = {
        "resolution": f"{w}x{h}",
        "width": w,
        "height": h,
        "is_resolution_ok": w >= 400 and h >= 250,
        "blur_score": 0.0,
        "is_blurry": False,
        "brightness": 0.0,
        "is_brightness_ok": True,
        "warnings": [],
    }
    gray = cv2.cvtColor(img_array, cv2.COLOR_BGR2GRAY) if len(img_array.shape) == 3 else img_array
    blur_score = cv2.Laplacian(gray, cv2.CV_64F).var()
    result["blur_score"] = round(float(blur_score), 2)
    result["is_blurry"] = blur_score < 50.0
    if result["is_blurry"]:
        result["warnings"].append("Ảnh bị mờ (blur). Vui lòng chụp lại rõ nét hơn.")
    if not result["is_resolution_ok"]:
        result["warnings"].append(f"Độ phân giải quá thấp ({w}×{h}). Cần tối thiểu 400×250 pixel.")
    brightness = float(np.mean(gray))
    result["brightness"] = round(brightness, 2)
    if brightness < 40:
        result["is_brightness_ok"] = False
        result["warnings"].append("Ảnh quá tối. Vui lòng chụp lại ở nơi có đủ ánh sáng.")
    elif brightness > 230:
        result["is_brightness_ok"] = False
        result["warnings"].append("Ảnh bị lóa sáng (overexposed). Vui lòng chụp lại tránh ánh sáng trực tiếp.")
    return result


def detect_screen_capture(img_array: np.ndarray) -> Dict[str, Any]:
    """
    Heuristic phổ tần cao (moiré). Ngưỡng chưa được hiệu chỉnh trên tập ảnh thật nên
    CHỈ dùng để cảnh báo, không dùng để kết luận ảnh hợp lệ hay không.
    """
    import cv2

    gray = cv2.cvtColor(img_array, cv2.COLOR_BGR2GRAY) if len(img_array.shape) == 3 else img_array
    f_shift = np.fft.fftshift(np.fft.fft2(gray.astype(float)))
    magnitude = np.log1p(np.abs(f_shift))
    h, w = magnitude.shape
    cy, cx = h // 2, w // 2
    r = min(h, w) // 10
    magnitude[cy - r:cy + r, cx - r:cx + r] = 0
    high_freq_energy = float(np.mean(magnitude))
    is_screen_capture = high_freq_energy > 5.5
    return {
        "high_freq_energy": round(high_freq_energy, 3),
        "is_likely_screen_capture": is_screen_capture,
        "warning": "Ảnh có thể được chụp lại từ màn hình (moiré). Nên chụp trực tiếp từ thẻ gốc."
        if is_screen_capture else None,
    }


# ═══════════════════════════════════════════════════════════════════════════
# 3. NHẬN DIỆN BỐ CỤC
# ═══════════════════════════════════════════════════════════════════════════
_FRONT_TITLE = re.compile(r"CAN\s*CUOC|IDENTITY\s*CARD|CITIZEN\s*IDENTITY")
_FRONT_GROUPS = ["name", "dob", "sex", "nationality", "origin", "residence", "expiry"]
_BACK_GROUPS = {
    "ident": _LABEL_RE["ident"],
    "issue": re.compile(LABELS["issue"] + r"|NGAY\s*\d{1,2}\s*THANG\s*\d{1,2}\s*NAM\s*\d{4}"),
    "authority": re.compile(r"CUC\s*TRUONG|CUC\s*CANH\s*SAT|GIAM\s*DOC\s*CONG\s*AN|BO\s*CONG\s*AN"),
    "residence": _LABEL_RE["residence"],
    "birth_reg": _LABEL_RE["birth_reg"],
    "mrz": re.compile(r"I[DO<]?VNM"),
}

# Giữ tên cũ cho tương thích (một số nơi có thể import)
FRONT_KEYWORDS = _FRONT_GROUPS
BACK_KEYWORDS = list(_BACK_GROUPS)


def detect_cccd_layout(ocr_texts: List[str], side: str = "front") -> Dict[str, Any]:
    """
    Mặt trước: có tiêu đề "CĂN CƯỚC..." và >= 2 nhãn trường, hoặc >= 4 nhãn trường.
    Mặt sau: >= 2 nhóm đặc trưng (đặc điểm nhận dạng, ngày cấp, cơ quan cấp, nơi cư trú,
    nơi đăng ký khai sinh, MRZ). Không còn dùng từ phổ biến như "Số", "No", "Ngày", "Việt Nam".
    """
    combined = _norm(" ".join(ocr_texts))
    if side == "front":
        matched = [g for g in _FRONT_GROUPS if _LABEL_RE[g].search(combined)]
        has_title = bool(_FRONT_TITLE.search(combined))
        if has_title:
            matched = ["title"] + matched
        is_valid = (has_title and len(matched) - 1 >= 2) or len([m for m in matched if m != "title"]) >= 4
        need = "tiêu đề CĂN CƯỚC + ≥ 2 trường"
    else:
        matched = [g for g, rx in _BACK_GROUPS.items() if rx.search(combined.replace(" ", "") if g == "mrz" else combined)]
        is_valid = len(matched) >= 2
        need = "≥ 2 đặc trưng mặt sau"
    return {
        "side": side,
        "keywords_found": len(matched),
        "keywords_matched": matched,
        "is_layout_valid": is_valid,
        "warning": None if is_valid else (
            f"Ảnh không giống CCCD {'mặt trước' if side == 'front' else 'mặt sau'} "
            f"(phát hiện {len(matched)} đặc trưng, cần {need})."
        ),
    }


# ═══════════════════════════════════════════════════════════════════════════
# 4. TRÍCH XUẤT TRƯỜNG
# ═══════════════════════════════════════════════════════════════════════════
_DATE_RE = re.compile(r"(\d{1,2})\s*[/\-.]\s*(\d{1,2})\s*[/\-.]\s*(\d{2,4})")
_ID_RE = re.compile(r"(?<!\d)\d(?:[ .]?\d){11}(?!\d)")
_OCR_DIGIT_FIX = str.maketrans({"O": "0", "o": "0", "D": "0", "I": "1", "l": "1", "|": "1", "B": "8", "S": "5"})


def _to_date(d: str, m: str, y: str) -> Optional[str]:
    if len(y) == 2:
        y = ("19" if int(y) > (date.today().year % 100) else "20") + y
    try:
        dt = date(int(y), int(m), int(d))
    except ValueError:
        return None
    if not (1900 <= dt.year <= 2200):
        return None
    return dt.strftime("%d/%m/%Y")


def _date_in(text: str) -> Optional[str]:
    m = _DATE_RE.search(text or "")
    return _to_date(*m.groups()) if m else None


def _date_after(texts: List[str], key: str) -> Optional[str]:
    label = _LABEL_RE[key]
    for i, text in enumerate(texts):
        m = label.search(_norm(text))
        if not m:
            continue
        found = _date_in(_cut_at_next_label(_strip_leading_labels(text[m.end():])))
        if found:
            return found
        if i + 1 < len(texts):
            nxt = texts[i + 1]
            lead = _STOP_LABEL.search(_norm(nxt))
            if not (lead and lead.start() <= 2):
                found = _date_in(_cut_at_next_label(nxt))
                if found:
                    return found
    return None


def _extract_id_number(texts: List[str]) -> Optional[str]:
    """
    Số CCCD 12 chữ số. Chấp nhận khoảng trắng / dấu chấm giữa các nhóm số do OCR tách.
    Không bao giờ cắt chuỗi dài hơn 12 số (dãy 13 số bị loại chứ không lấy 12 số đầu).
    Ưu tiên block có nhãn "Số / No / Số định danh cá nhân".
    """
    labelled, others = [], []
    for text in texts:
        m = _LABEL_RE["id_label"].search(_norm(text))
        if m:
            labelled.append(text[m.end():].translate(_OCR_DIGIT_FIX))
        else:
            others.append(text)
    for chunk in labelled + others:
        for cand in _ID_RE.findall(chunk):
            digits = re.sub(r"\D", "", cand)
            if len(digits) == 12:
                return digits
    return None


_NAME_OK = re.compile(r"^[A-ZÀ-ỸĐ][A-ZÀ-ỸĐ' ]+$")


def _extract_name(texts: List[str]) -> Optional[str]:
    name_label = _LABEL_RE["name"]
    for i, text in enumerate(texts):
        m = name_label.search(_norm(text))
        if not m:
            continue
        parts: List[str] = []
        first = _clean_text(_cut_at_next_label(_strip_leading_labels(text[m.end():])))
        if first:
            parts.append(first)
        if not parts:
            # Tên nằm ở 1–2 block kế tiếp (tên dài có thể bị tách)
            for nxt in texts[i + 1:i + 3]:
                n = _norm(nxt)
                lead = _STOP_LABEL.search(n)
                if (lead and lead.start() <= 2) or _DATE_RE.search(nxt):
                    break
                parts.append(_clean_text(_cut_at_next_label(nxt)))
                if lead:
                    break
        name = _clean_text(" ".join(parts)).upper()
        name = re.sub(r"^" + _SEP + "|" + _SEP + "$", "", name)
        if name and _NAME_OK.match(name) and 2 <= len(name.split()) <= 7:
            return name
        # "Họ và tên" | "Full name:" | tên — tìm tiếp ở block nhãn kế tiếp
    return None


def _extract_gender(texts: List[str]) -> Optional[str]:
    val = _value_after(texts, "sex")
    if not val:
        return None
    first = _norm(val).split()[0] if val.split() else ""
    if first in ("NAM", "MALE", "M"):
        return "Nam"
    if first in ("NU", "FEMALE", "F"):
        return "Nữ"
    return None


def parse_front_cccd(ocr_results: List[Tuple]) -> Dict[str, Any]:
    texts = [_nfc(item[1]) for item in ocr_results]
    result: Dict[str, Any] = {
        "id_number": _extract_id_number(texts),
        "full_name": _extract_name(texts),
        "date_of_birth": _date_after(texts, "dob"),
        "gender": _extract_gender(texts),
        "nationality": None,
        "place_of_origin": None,
        "place_of_residence": None,
        "date_of_expiry": _date_after(texts, "expiry"),
        "raw_texts": texts,
    }
    nat = _value_after(texts, "nationality")
    if nat:
        result["nationality"] = nat
    origin = _value_after(texts, "origin", max_next_blocks=2)
    if origin:
        result["place_of_origin"] = origin
    residence = _value_after(texts, "residence", max_next_blocks=2)
    if residence:
        result["place_of_residence"] = residence
    return result


# ── MRZ (ICAO 9303, TD1: 3 dòng × 30 ký tự) ─────────────────────────────────
def _mrz_char_value(c: str) -> int:
    if c.isdigit():
        return int(c)
    if "A" <= c <= "Z":
        return ord(c) - 55
    return 0  # '<'


def mrz_check_digit(data: str) -> str:
    weights = (7, 3, 1)
    return str(sum(_mrz_char_value(c) * weights[i % 3] for i, c in enumerate(data)) % 10)


def _mrz_lines(texts: List[str]) -> List[str]:
    out = []
    for t in texts:
        s = _nfc(t).upper().replace(" ", "")
        s = re.sub(r"[«‹≪〈<]", "<", s)
        if 25 <= len(s) <= 32 and re.fullmatch(r"[A-Z0-9<]+", s):
            out.append(s[:30].ljust(30, "<"))
    return out


def parse_mrz(texts: List[str]) -> Optional[Dict[str, Any]]:
    """Đọc MRZ TD1 mặt sau thẻ chip. Trả None nếu không tìm thấy 2 dòng đầu hợp lệ."""
    lines = _mrz_lines(texts)
    for i, l1 in enumerate(lines):
        if not re.match(r"I[A-Z<]VNM", l1) or i + 1 >= len(lines):
            continue
        l2 = lines[i + 1]
        doc_number, doc_check = l1[5:14], l1[14]
        optional = l1[15:30]
        dob, dob_check, sex = l2[0:6], l2[6], l2[7]
        expiry, expiry_check = l2[8:14], l2[14]
        full_id_match = re.search(r"\d{12}", optional)
        full_id = full_id_match.group(0) if full_id_match else None
        name = None
        if i + 2 < len(lines):
            raw_name = lines[i + 2].strip("<")
            surname, _, given = raw_name.partition("<<")
            name = _clean_text(f"{surname.replace('<', ' ')} {given.replace('<', ' ')}") or None
        result = {
            "doc_number": doc_number,
            "doc_number_valid": mrz_check_digit(doc_number) == doc_check,
            "full_id": full_id,
            "full_id_consistent": bool(full_id and full_id.endswith(doc_number)),
            "dob_yymmdd": dob,
            "dob_valid": dob.isdigit() and mrz_check_digit(dob) == dob_check,
            "sex": {"M": "Nam", "F": "Nữ"}.get(sex),
            "expiry_yymmdd": expiry,
            "expiry_valid": expiry.isdigit() and mrz_check_digit(expiry) == expiry_check,
            "name": name,
        }
        result["is_valid"] = result["doc_number_valid"] and result["dob_valid"] and result["expiry_valid"]
        return result
    return None


def parse_back_cccd(ocr_results: List[Tuple]) -> Dict[str, Any]:
    """Mặt sau: đặc điểm nhận dạng, ngày cấp, nơi cấp, (thẻ 2024) nơi cư trú, MRZ."""
    texts = [_nfc(item[1]) for item in ocr_results]
    full_text = "\n".join(texts)
    normalized = _norm(full_text)

    result: Dict[str, Any] = {
        "personal_identification": _value_after(texts, "ident"),
        "issue_date": None,
        "issuing_authority": None,
        "place_of_residence": _value_after(texts, "residence", max_next_blocks=2),
        "place_of_birth_registration": _value_after(texts, "birth_reg", max_next_blocks=2),
        "date_of_expiry": _date_after(texts, "expiry"),
        "mrz": None,
        "raw_texts": texts,
    }

    # Ngày cấp: nhãn "Ngày, tháng, năm cấp / Date of issue" → "Ngày DD tháng MM năm YYYY"
    issue = _date_after(texts, "issue")
    if not issue:
        m = re.search(r"NGA?Y\s*(\d{1,2})\s*THA?NG\s*(\d{1,2})\s*NA?M\s*(\d{4})", normalized)
        if m:
            issue = _to_date(*m.groups())
    if not issue:
        # Ngày bất kỳ trên mặt sau, trừ ngày hết hạn
        for m in _DATE_RE.finditer(full_text):
            d = _to_date(*m.groups())
            if d and d != result["date_of_expiry"]:
                issue = d
                break
    result["issue_date"] = issue

    if re.search(r"CUC\s*TRUONG|CUC\s*CANH\s*SAT", normalized):
        result["issuing_authority"] = "Cục Cảnh sát QLHC về TTXH"
    elif re.search(r"BO\s*CONG\s*AN", normalized):
        result["issuing_authority"] = "Bộ Công an"
    elif "GIAM DOC" in normalized:
        ca = re.search(r"C[OÔ]NG\s*AN\s+(.+?)(?:\n|$)", full_text, re.IGNORECASE)
        result["issuing_authority"] = f"Công an {_clean_text(ca.group(1))}" if ca else "Giám đốc Công an tỉnh/thành phố"

    result["mrz"] = parse_mrz(texts)
    return result


# ═══════════════════════════════════════════════════════════════════════════
# 5. ĐỐI CHIẾU CHÉO
# ═══════════════════════════════════════════════════════════════════════════
def cross_check_front(ocr_data: Dict[str, Any], id_validation: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """So số CCCD (thế kỷ + giới tính + năm sinh) với ngày sinh và giới tính đọc được."""
    out: Dict[str, Any] = {"id_matches_dob": None, "id_matches_gender": None, "warnings": []}
    if not id_validation or id_validation.get("birth_year") is None:
        return out
    dob = ocr_data.get("date_of_birth")
    if dob:
        dob_year = int(dob[-4:])
        out["id_matches_dob"] = dob_year == id_validation["birth_year"]
        if not out["id_matches_dob"]:
            out["warnings"].append(
                f"Năm sinh trên thẻ ({dob_year}) không khớp năm sinh mã hóa trong số CCCD "
                f"({id_validation['birth_year']}). Kiểm tra lại số CCCD hoặc ngày sinh."
            )
    if ocr_data.get("gender"):
        out["id_matches_gender"] = ocr_data["gender"] == id_validation["gender"]
        if not out["id_matches_gender"]:
            out["warnings"].append("Giới tính trên thẻ không khớp giới tính mã hóa trong số CCCD.")
    return out


# ═══════════════════════════════════════════════════════════════════════════
# 6. QUÉT
# ═══════════════════════════════════════════════════════════════════════════
def _load_image(image_bytes: bytes):
    """Trả (ảnh BGR, lỗi). Chặn decompression bomb trước khi giải mã."""
    import io
    import cv2
    from PIL import Image

    Image.MAX_IMAGE_PIXELS = 16_000_000
    try:
        with Image.open(io.BytesIO(image_bytes)) as pil_img:
            pw, ph = pil_img.size
            if (pw * ph > 16_000_000) or max(pw, ph) > 4096:
                return None, (f"Kích thước ảnh quá lớn ({pw}x{ph} px, vượt giới hạn an toàn 16 Megapixels / 4096px). "
                              "Vui lòng thu nhỏ ảnh trước khi tải lên.")
    except Exception as img_err:
        logger.warning("[CCCD OCR Security] Kiểm tra header ảnh thất bại: %s", type(img_err).__name__)
        return None, "Ảnh không hợp lệ, bị hỏng hoặc kích thước giải mã vượt giới hạn an toàn."

    img = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        return None, "Không thể đọc file ảnh. Vui lòng tải lên ảnh định dạng JPG, PNG hoặc WebP."
    h, w = img.shape[:2]
    if max(h, w) > 2048:
        scale = 2048.0 / max(h, w)
        img = cv2.resize(img, (max(1, int(w * scale)), max(1, int(h * scale))), interpolation=cv2.INTER_AREA)
    return img, None


def build_verification(
    side: str,
    ocr_data: Dict[str, Any],
    quality: Dict[str, Any],
    screen_check: Dict[str, Any],
    layout: Dict[str, Any],
) -> Dict[str, Any]:
    """Tổng hợp các kiểm tra. Hàm thuần — test được không cần ảnh / EasyOCR."""
    image_quality_ok = quality["is_resolution_ok"] and not quality["is_blurry"] and quality["is_brightness_ok"]
    checks: Dict[str, bool] = {
        "image_quality_ok": image_quality_ok,
        "layout_detected": layout["is_layout_valid"],
        "no_screen_capture": not screen_check["is_likely_screen_capture"],  # chỉ cảnh báo
    }
    warnings: List[str] = list(quality.get("warnings", []))
    if screen_check.get("warning"):
        warnings.append(screen_check["warning"])
    if layout.get("warning"):
        warnings.append(layout["warning"])

    cross: Dict[str, Any] = {}
    if side == "front":
        id_validation = validate_cccd_number(ocr_data["id_number"]) if ocr_data.get("id_number") else None
        checks["id_format_valid"] = bool(id_validation and id_validation["is_valid"])
        checks["has_name"] = bool(ocr_data.get("full_name"))
        checks["has_dob"] = bool(ocr_data.get("date_of_birth"))
        if id_validation:
            warnings.extend(id_validation["errors"])
        else:
            warnings.append("Không đọc được số CCCD 12 chữ số. Vui lòng nhập tay và kiểm tra lại.")
        cross = cross_check_front(ocr_data, id_validation)
        for key in ("id_matches_dob", "id_matches_gender"):
            if cross[key] is not None:
                checks[key] = cross[key]
        warnings.extend(cross["warnings"])
        no_mismatch = cross["id_matches_dob"] is not False and cross["id_matches_gender"] is not False
        is_valid = (layout["is_layout_valid"] and image_quality_ok and checks["id_format_valid"]
                    and checks["has_name"] and no_mismatch)
    else:
        mrz = ocr_data.get("mrz")
        checks["has_issue_date"] = bool(ocr_data.get("issue_date"))
        if mrz:
            checks["mrz_valid"] = bool(mrz["is_valid"])
            if not mrz["is_valid"]:
                warnings.append("Dải MRZ đọc được nhưng sai chữ số kiểm tra — có thể do OCR đọc nhầm.")
        is_valid = layout["is_layout_valid"] and image_quality_ok and (checks["has_issue_date"] or checks.get("mrz_valid", False))

    passed = sum(1 for v in checks.values() if v)
    ratio = round(passed / len(checks), 2) if checks else 0.0
    return {
        "is_valid_format_and_quality": is_valid,
        "is_likely_authentic": is_valid,  # alias cũ — KHÔNG có nghĩa thẻ là thật
        "confidence_score": int(round(ratio * 100)),
        "confidence_ratio": ratio,
        "disclaimer": "Kết quả OCR chỉ hỗ trợ trích xuất thông tin tự động và kiểm tra chất lượng ảnh. "
                      "Không có giá trị pháp lý thay thế xác minh danh tính từ cơ quan Nhà nước.",
        "checks": checks,
        "warnings": warnings,
        "details": {
            "image_quality": {
                "resolution": quality["resolution"],
                "blur_score": quality["blur_score"],
                "brightness": quality["brightness"],
            },
            "layout": {"keywords_found": layout["keywords_found"], "is_valid": layout["is_layout_valid"]},
            "screen_capture": {
                "high_freq_energy": screen_check["high_freq_energy"],
                "is_screen": screen_check["is_likely_screen_capture"],
                "is_heuristic": True,
            },
        },
    }


def scan_cccd(image_bytes: bytes, side: str = "front") -> Dict[str, Any]:
    img, error = _load_image(image_bytes)
    if error:
        return {"success": False, "error": error, "ocr_data": None, "verification": None}

    quality = check_image_quality(img)
    screen_check = detect_screen_capture(img)
    ocr_results = _get_reader().readtext(img)
    texts = [item[1] for item in ocr_results]
    layout = detect_cccd_layout(texts, side=side)
    ocr_data = parse_front_cccd(ocr_results) if side == "front" else parse_back_cccd(ocr_results)
    verification = build_verification(side, ocr_data, quality, screen_check, layout)

    return {
        "success": True,
        "side": side,
        "ocr_data": {k: v for k, v in ocr_data.items() if k != "raw_texts"},  # không trả chữ OCR thô
        "verification": verification,
    }
