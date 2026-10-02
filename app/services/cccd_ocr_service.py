import re
import io
import logging
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path

import numpy as np

logger = logging.getLogger("cccd_ocr")

_reader = None


def _get_reader():
    global _reader
    if _reader is None:
        import easyocr
        _reader = easyocr.Reader(["vi", "en"], gpu=False)
        logger.info("EasyOCR reader initialized (vi + en, CPU)")
    return _reader

VALID_PROVINCE_CODES = {
    "001", "002", "004", "006", "008", "010", "011", "012", "014", "015",
    "017", "019", "020", "022", "024", "025", "026", "027", "030", "031",
    "033", "034", "035", "036", "037", "038", "040", "042", "044", "045",
    "046", "048", "049", "051", "052", "054", "056", "058", "060", "062",
    "064", "066", "067", "068", "070", "072", "074", "075", "077", "079",
    "080", "082", "083", "084", "086", "087", "089", "091", "092", "093",
    "094", "095", "096",
}

# 1. XÁC THỰC SỐ CCCD
def validate_cccd_number(raw: str) -> Dict[str, Any]:
    """Kiểm tra cấu trúc số CCCD 12 số theo quy chuẩn Bộ Công an.

    Cấu trúc: PPP G YY XXXXXX
      - PPP: mã tỉnh/thành phố (3 số)
      - G: giới tính + thế kỷ (0/1 = nam/nữ sinh 1900-1999, 2/3 = nam/nữ sinh 2000+)
      - YY: 2 số cuối năm sinh
      - XXXXXX: số ngẫu nhiên (6 số)
    """
    digits = re.sub(r"\D", "", raw)
    result: Dict[str, Any] = {
        "is_valid": False,
        "cleaned": digits,
        "province_code": None,
        "gender_digit": None,
        "gender": None,
        "birth_year_suffix": None,
        "errors": [],
    }

    if len(digits) != 12:
        result["errors"].append(f"Số CCCD phải đúng 12 chữ số, hiện có {len(digits)} số.")
        return result

    province_code = digits[:3]
    gender_digit = int(digits[3])
    birth_year_suffix = digits[4:6]

    result["province_code"] = province_code
    result["gender_digit"] = gender_digit
    result["birth_year_suffix"] = birth_year_suffix

    if province_code not in VALID_PROVINCE_CODES:
        result["errors"].append(f"Mã tỉnh '{province_code}' không nằm trong danh sách hợp lệ.")

    if gender_digit in (0, 2, 4, 6, 8):
        result["gender"] = "Nam"
    else:
        result["gender"] = "Nữ"

    if not result["errors"]:
        result["is_valid"] = True

    return result
    
# 2. KIỂM TRA CHẤT LƯỢNG ẢNH
def check_image_quality(img_array: np.ndarray) -> Dict[str, Any]:
    """Kiểm tra chất lượng ảnh CCCD: độ phân giải, mờ (blur), độ sáng."""
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
    result["blur_score"] = round(blur_score, 2)
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


# 3. PHÁT HIỆN CHỤP LẠI TỪ MÀN HÌNH (Moiré Pattern)
def detect_screen_capture(img_array: np.ndarray) -> Dict[str, Any]:
    """Phát hiện ảnh chụp lại từ màn hình bằng phân tích tần số FFT."""
    import cv2

    gray = cv2.cvtColor(img_array, cv2.COLOR_BGR2GRAY) if len(img_array.shape) == 3 else img_array

    f_transform = np.fft.fft2(gray.astype(float))
    f_shift = np.fft.fftshift(f_transform)
    magnitude = np.log1p(np.abs(f_shift))

    h, w = magnitude.shape
    cy, cx = h // 2, w // 2

    mask_radius = min(h, w) // 10
    magnitude[cy - mask_radius:cy + mask_radius, cx - mask_radius:cx + mask_radius] = 0

    high_freq_energy = float(np.mean(magnitude))

    is_screen_capture = high_freq_energy > 5.5

    return {
        "high_freq_energy": round(high_freq_energy, 3),
        "is_likely_screen_capture": is_screen_capture,
        "warning": "Ảnh có dấu hiệu chụp lại từ màn hình (moiré). Vui lòng chụp trực tiếp từ thẻ CCCD gốc."
        if is_screen_capture else None,
    }

# 4. PHÁT HIỆN BỐ CỤC CCCD (Layout Detection)
FRONT_KEYWORDS = [
    "CĂN CƯỚC", "CÔNG DÂN", "CITIZEN", "CARD",
    "Họ và tên", "Full name", "Sinh", "Date of birth",
    "Giới tính", "Sex", "Quốc tịch", "Nationality",
    "Quê quán", "Place of origin", "Nơi thường trú",
    "Place of residence", "Có giá trị đến", "Date of expiry",
    "Số", "No",
    "CĂN CƯỚC", "IDENTITY",
]

BACK_KEYWORDS = [
    "Đặc điểm nhận dạng", "Personal identification",
    "Ngày", "tháng", "năm",
    "CỤC TRƯỞNG", "GIÁM ĐỐC",
    "CỤC CẢNH SÁT", "CẢNH SÁT",
    "QUẢN LÝ HÀNH CHÍNH", "TRẬT TỰ XÃ HỘI",
    "DAC DIEM NHAN DANG", "NHAN DANG",
    "CUC TRUONG", "GIAM DOC",
    "CUC CANH SAT", "CANH SAT",
    "QUAN LY HANH CHINH", "TRAT TU XA HOI",
    "CONG AN", "CÔNG AN",
    "CONG HOA XA HOI", "CỘNG HÒA XÃ HỘI",
    "VIET NAM", "VIỆT NAM",
]


def detect_cccd_layout(ocr_texts: List[str], side: str = "front") -> Dict[str, Any]:
    """Kiểm tra xem ảnh có chứa bố cục CCCD hợp lệ không dựa trên keyword."""
    keywords = FRONT_KEYWORDS if side == "front" else BACK_KEYWORDS
    combined = " ".join(ocr_texts).upper()

    matched = []
    for kw in keywords:
        if kw.upper() in combined:
            matched.append(kw)

    min_matches = 2 if side == "back" else 3
    is_valid = len(matched) >= min_matches

    return {
        "side": side,
        "keywords_found": len(matched),
        "keywords_matched": matched[:10],
        "is_layout_valid": is_valid,
        "warning": f"Ảnh không giống CCCD {'mặt trước' if side == 'front' else 'mặt sau'}. "
                   f"Chỉ phát hiện {len(matched)} từ khóa đặc trưng (cần ≥ {min_matches})."
        if not is_valid else None,
    }

# 5. TRÍCH XUẤT THÔNG TIN TỪ OCR (Parsing)

def _clean_text(text: str) -> str:
    """Loại bỏ ký tự thừa, chuẩn hóa khoảng trắng."""
    return re.sub(r"\s+", " ", text).strip()


def _find_value_after(texts: List[str], label_patterns: List[str]) -> Optional[str]:
    """Tìm giá trị xuất hiện sau label (trên cùng dòng hoặc dòng kế tiếp).

    EasyOCR thường tách label và value thành 2 text block riêng biệt,
    ví dụ: ["Họ và tên / Full name", "NGUYỄN VĂN A"].
    Hàm này thử cả 2 cách: cùng dòng và dòng kế tiếp.
    """
    for i, text in enumerate(texts):
        for pattern in label_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                same_line_match = re.search(pattern + r"[:\s]*(.+)", text, re.IGNORECASE)
                if same_line_match:
                    value = _clean_text(same_line_match.group(1))
                    for remove_pat in label_patterns:
                        value = re.sub(remove_pat, "", value, flags=re.IGNORECASE).strip()
                    value = re.sub(r"^[/\-:|\s]+", "", value).strip()
                    value = re.sub(r"[/\-:|\s]+$", "", value).strip()
                    if value and len(value) > 1 and not re.match(r"^[\W\d]+$", value):
                        return value

                if i + 1 < len(texts):
                    next_value = _clean_text(texts[i + 1])
                    for remove_pat in label_patterns:
                        next_value = re.sub(remove_pat, "", next_value, flags=re.IGNORECASE).strip()
                    next_value = re.sub(r"^[/\-:|\s]+", "", next_value).strip()
                    if next_value and len(next_value) > 1 and not re.match(r"^[\W\d]+$", next_value):
                        return next_value

    combined = "\n".join(texts)
    for pattern in label_patterns:
        match = re.search(pattern + r"[:\s]*(.+)", combined, re.IGNORECASE)
        if match:
            value = _clean_text(match.group(1))
            for remove_pat in label_patterns:
                value = re.sub(remove_pat, "", value, flags=re.IGNORECASE).strip()
            value = re.sub(r"^[/\-:|\s]+", "", value).strip()
            if value and len(value) > 1 and not re.match(r"^[\W\d]+$", value):
                return value
    return None


def _extract_12_digit_number(texts: List[str]) -> Optional[str]:
    """Tìm chuỗi 12 chữ số liên tiếp (số CCCD)."""
    combined = " ".join(texts)
    match = re.search(r"\b(\d{12})\b", combined)
    if match:
        return match.group(1)
    all_digits = re.findall(r"\d{9,14}", combined)
    for d in all_digits:
        cleaned = d[:12]
        if len(cleaned) == 12:
            return cleaned
    return None


def _extract_date(texts: List[str], label_patterns: List[str]) -> Optional[str]:
    """Tìm ngày tháng theo format DD/MM/YYYY hoặc DD-MM-YYYY sau label."""
    combined = " ".join(texts)
    for pattern in label_patterns:
        match = re.search(pattern + r"[:\s]*(\d{1,2}[\s/\-\.]+\d{1,2}[\s/\-\.]+\d{2,4})",
                          combined, re.IGNORECASE)
        if match:
            raw = match.group(1)
            # Chuẩn hóa dấu phân cách
            parts = re.split(r"[\s/\-\.]+", raw)
            if len(parts) == 3:
                d, m, y = parts
                if len(y) == 2:
                    y = "19" + y if int(y) > 30 else "20" + y
                return f"{d.zfill(2)}/{m.zfill(2)}/{y}"
    return None


def parse_front_cccd(ocr_results: List[Tuple]) -> Dict[str, Any]:
    """Trích xuất thông tin từ kết quả OCR mặt trước CCCD.

    Trả về: số CCCD, họ tên, ngày sinh, giới tính, quốc tịch, quê quán,
    nơi thường trú, ngày hết hạn.
    """
    texts = [item[1] for item in ocr_results]
    full_text = "\n".join(texts)

    result: Dict[str, Any] = {
        "id_number": None,
        "full_name": None,
        "date_of_birth": None,
        "gender": None,
        "nationality": None,
        "place_of_origin": None,
        "place_of_residence": None,
        "date_of_expiry": None,
        "raw_texts": texts,
    }

    result["id_number"] = _extract_12_digit_number(texts)

    STOP_LABELS = re.compile(
        r"(Sinh|Date of birth|Gi[ớo]i t[ií]nh|Sex|Qu[ốo]c t[ịi]ch|Nationality|"
        r"Qu[êe] qu[áa]n|Place of origin|N[ơo]i th[ưu][ờo]ng tr[úu]|Place of residence|"
        r"C[óo] gi[áa] tr[ịi]|Date of expiry|\d{2}[/\-]\d{2}[/\-]\d{4})",
        re.IGNORECASE
    )
    NAME_LABEL = re.compile(
        r"(H[ọo] v[àa] t[êe]n|Ho va ten|Full name)",
        re.IGNORECASE
    )
    name_parts: List[str] = []
    found_name_label = False
    for i, text in enumerate(texts):
        if not found_name_label:
            if NAME_LABEL.search(text):
                found_name_label = True
                after_label = NAME_LABEL.sub("", text)
                after_label = re.sub(r"[/\-:|\.\s]+", " ", after_label).strip()
                if after_label and len(after_label) > 1 and not re.match(r"^[\W\d]+$", after_label):
                    name_parts.append(after_label)
        else:
            block = text.strip()
            if STOP_LABELS.search(block):
                break
            cleaned_block = re.sub(r"[/\-:|\.\s]+", "", block)
            if cleaned_block and not re.match(r"^\d+$", cleaned_block):
                name_parts.append(block)

    if name_parts:
        full_name = " ".join(name_parts)
        full_name = re.split(r"(?:Sinh|Date|Gi[ớo]i|Sex|Nam|N[ữu])", full_name, flags=re.IGNORECASE)[0]
        result["full_name"] = _clean_text(full_name).upper()
    else:
        name = _find_value_after(texts, [
            r"Họ và tên", r"Ho và tên", r"Ho va ten", r"Full name", r"Họ\s*va\s*tên",
        ])
        if name:
            name = re.split(r"(?:Sinh|Date|Gi[ớo]i|Sex|Nam|N[ữu])", name, flags=re.IGNORECASE)[0]
            result["full_name"] = _clean_text(name).upper()

    result["date_of_birth"] = _extract_date(texts, [
        r"Ngày[,\s]*tháng[,\s]*năm\s*sinh",
        r"Sinh",
        r"Date of birth",
        r"Ngay sinh",
    ])

    gender_text = _find_value_after(texts, [r"Giới tính", r"Sex", r"Gioi tinh"])
    if gender_text:
        upper = gender_text.upper()
        if "NAM" in upper or "MALE" in upper:
            result["gender"] = "Nam"
        elif "NỮ" in upper or "NU" in upper or "FEMALE" in upper:
            result["gender"] = "Nữ"

    nationality = _find_value_after(texts, [r"Quốc tịch", r"Nationality", r"Quoc tich"])
    if nationality:
        result["nationality"] = _clean_text(nationality)
    origin = _find_value_after(texts, [r"Quê quán", r"Place of origin", r"Que quan"])
    if origin:
        origin = re.split(r"(?:Nơi thường trú|Place of residence)", origin, flags=re.IGNORECASE)[0]
        result["place_of_origin"] = _clean_text(origin)

    residence = _find_value_after(texts, [
        r"Nơi thường trú",
        r"Place of residence",
        r"Noi thuong tru",
    ])
    if residence:
        residence = re.split(r"(?:Có giá trị|Date of expiry)", residence, flags=re.IGNORECASE)[0]
        result["place_of_residence"] = _clean_text(residence)

    result["date_of_expiry"] = _extract_date(texts, [
        r"Có giá trị đến",
        r"Date of expiry",
        r"Co gia tri den",
    ])

    return result


def parse_back_cccd(ocr_results: List[Tuple]) -> Dict[str, Any]:
    """Trích xuất thông tin từ kết quả OCR mặt sau CCCD.

    Trả về: đặc điểm nhận dạng, ngày cấp, nơi cấp.
    """
    texts = [item[1] for item in ocr_results]
    full_text = "\n".join(texts)

    result: Dict[str, Any] = {
        "personal_identification": None,
        "issue_date": None,
        "issuing_authority": None,
        "raw_texts": texts,
    }

    ident = _find_value_after(texts, [
        r"Đặc điểm nhận dạng",
        r"Personal identification",
        r"Dac diem nhan dang",
    ])
    if ident:
        result["personal_identification"] = _clean_text(ident)

    date_patterns = [
        r"[Nn]g[àa]y\s*(\d{1,2})\s*th[áa]ng\s*(\d{1,2})\s*n[ăa]m\s*(\d{4})",
        r"[Nn]ga?y\s*(\d{1,2})\s*tha?ng\s*(\d{1,2})\s*na?m\s*(\d{4})",
        r"(\d{1,2})[/\-\.](\d{1,2})[/\-\.](\d{4})",
    ]
    for dp in date_patterns:
        date_match = re.search(dp, full_text)
        if date_match:
            d, m, y = date_match.group(1), date_match.group(2), date_match.group(3)
            result["issue_date"] = f"{d.zfill(2)}/{m.zfill(2)}/{y}"
            break

    full_upper = full_text.upper()
    _DIACRITICS_MAP = str.maketrans(
        "ÀÁẢÃẠĂẮẰẲẴẶÂẤẦẨẪẬĐÈÉẺẼẸÊẾỀỂỄỆÌÍỈĨỊÒÓỎÕỌÔỐỒỔỖỘƠỚỜỞỠỢÙÚỦŨỤƯỨỪỬỮỰỲÝỶỸỴ",
        "AAAAAAAAAAAAAAAAADEEEEEEEEEEEIIIIIOOOOOOOOOOOOOOOOOUUUUUUUUUUUYYYYY"
    )
    normalized = full_upper.translate(_DIACRITICS_MAP)

    if "CUC TRUONG" in normalized or "CUC CANH SAT" in normalized:
        result["issuing_authority"] = "Cục Cảnh sát QLHC về TTXH"
    elif "GIAM DOC" in normalized:
        ca_match = re.search(r"C[OÔ]NG AN\s+(.+?)(?:\n|$)", full_text, re.IGNORECASE)
        if not ca_match:
            ca_match = re.search(r"CONG AN\s+(.+?)(?:\n|$)", full_text, re.IGNORECASE)
        if ca_match:
            result["issuing_authority"] = f"Công an {_clean_text(ca_match.group(1))}"
        else:
            result["issuing_authority"] = "Giám đốc Công an tỉnh/thành phố"

    return result


def scan_cccd(image_bytes: bytes, side: str = "front") -> Dict[str, Any]:
    """Quét ảnh CCCD: OCR + kiểm tra chất lượng + xác thực giả/thật.

    Args:
        image_bytes: Nội dung file ảnh (bytes)
        side: "front" = mặt trước, "back" = mặt sau

    Returns:
        Dict chứa: ocr_data, verification (kết quả xác thực)
    """
    import cv2

    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    if img is None:
        return {
            "success": False,
            "error": "Không thể đọc file ảnh. Vui lòng tải lên ảnh định dạng JPG, PNG hoặc WebP.",
            "ocr_data": None,
            "verification": None,
        }

    quality = check_image_quality(img)

    screen_check = detect_screen_capture(img)

    reader = _get_reader()
    ocr_results = reader.readtext(img)
    texts = [item[1] for item in ocr_results]

    layout = detect_cccd_layout(texts, side=side)

    if side == "front":
        ocr_data = parse_front_cccd(ocr_results)
    else:
        ocr_data = parse_back_cccd(ocr_results)

    id_validation = None
    if side == "front" and ocr_data.get("id_number"):
        id_validation = validate_cccd_number(ocr_data["id_number"])
    checks = {
        "image_quality_ok": quality["is_resolution_ok"] and not quality["is_blurry"] and quality["is_brightness_ok"],
        "layout_detected": layout["is_layout_valid"],
        "no_screen_capture": not screen_check["is_likely_screen_capture"],
    }

    if side == "front":
        checks["id_format_valid"] = id_validation["is_valid"] if id_validation else False
        checks["has_name"] = bool(ocr_data.get("full_name"))
        checks["has_dob"] = bool(ocr_data.get("date_of_birth"))

    # Điểm tin cậy tổng hợp
    total_checks = len(checks)
    passed_checks = sum(1 for v in checks.values() if v)
    confidence = round(passed_checks / total_checks, 2) if total_checks > 0 else 0

    # Tổng hợp cảnh báo
    warnings: List[str] = []
    warnings.extend(quality.get("warnings", []))
    if screen_check.get("warning"):
        warnings.append(screen_check["warning"])
    if layout.get("warning"):
        warnings.append(layout["warning"])
    if id_validation and id_validation.get("errors"):
        warnings.extend(id_validation["errors"])

    is_likely_authentic = confidence >= 0.6 and layout["is_layout_valid"]

    ocr_data_clean = {k: v for k, v in ocr_data.items() if k != "raw_texts"}

    return {
        "success": True,
        "side": side,
        "ocr_data": ocr_data_clean,
        "verification": {
            "is_likely_authentic": is_likely_authentic,
            "confidence_score": confidence,
            "checks": checks,
            "warnings": warnings,
            "details": {
                "image_quality": {
                    "resolution": quality["resolution"],
                    "blur_score": quality["blur_score"],
                    "brightness": quality["brightness"],
                },
                "layout": {
                    "keywords_found": layout["keywords_found"],
                    "is_valid": layout["is_layout_valid"],
                },
                "screen_capture": {
                    "high_freq_energy": screen_check["high_freq_energy"],
                    "is_screen": screen_check["is_likely_screen_capture"],
                },
            },
        },
    }
