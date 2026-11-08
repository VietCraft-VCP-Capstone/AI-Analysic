"""
Kiểm thử phần tách thông tin OCR CCCD (không cần EasyOCR / ảnh thật).
Dữ liệu là chuỗi giả lập theo bố cục thẻ, số CCCD là số giả.
"""

import pytest

from app.services.cccd_ocr_service import (
    build_verification,
    detect_cccd_layout,
    mrz_check_digit,
    parse_back_cccd,
    parse_front_cccd,
    parse_mrz,
    validate_cccd_number,
)


def R(lines):
    return [(None, t, 0.9) for t in lines]


def front(name="NGUYỄN VĂN AN", sex="Nam", dob="12/05/2003", id_no="001203012345", same_line_nat=False):
    lines = [
        "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM",
        "CĂN CƯỚC CÔNG DÂN",
        f"Số / No.: {id_no}",
        "Họ và tên / Full name:",
        name,
        f"Ngày sinh / Date of birth: {dob}",
    ]
    if same_line_nat:
        lines.append(f"Giới tính / Sex: {sex}   Quốc tịch / Nationality: Việt Nam")
    else:
        lines += [f"Giới tính / Sex: {sex}", "Quốc tịch / Nationality: Việt Nam"]
    lines += [
        "Quê quán / Place of origin:", "Xã Tân Lập, Huyện Đan Phượng, Hà Nội",
        "Nơi thường trú / Place of residence:", "Số 12 Ngõ 34, Phường Dịch Vọng, Cầu Giấy, Hà Nội",
        "Có giá trị đến: 12/05/2028",
    ]
    return R(lines)


# ---------------------------------------------------------------- mặt trước
@pytest.mark.parametrize("name", ["NGUYỄN HOÀI NAM", "LÊ NGỌC NỮ TRÂM", "TRẦN NAM SINH", "PHẠM THỊ NỮ"])
def test_name_containing_gender_words_kept(name):
    assert parse_front_cccd(front(name=name))["full_name"] == name


def test_name_on_same_line_as_label():
    r = parse_front_cccd(R(["CĂN CƯỚC CÔNG DÂN", "Họ và tên / Full name: Đỗ Minh Nam", "Ngày sinh: 01/01/1999"]))
    assert r["full_name"] == "ĐỖ MINH NAM"


def test_vi_and_en_labels_split_into_separate_blocks():
    # Đầu ra thật của EasyOCR: nhãn tiếng Việt và tiếng Anh nằm ở 2 block riêng
    r = parse_front_cccd(R([
        "CĂN CƯỚC CÔNG DÂN", "Số", "No.: 001099012345",
        "Họ và tên", "Full name:", "NGUYỄN HOÀI NAM",
        "Ngày sinh", "Date of birth: 15/08/1999",
        "Giới tính", "Sex: Nam",
        "Quốc tịch", "Nationality: Việt Nam",
        "Quê quán", "Place of origin: Xã Phú Lương, Hà Đông, Hà Nội",
        "Nơi thường trú", "Place of residence: Số 12 ngõ 34, Đống Đa, Hà Nội",
    ]))
    assert r["full_name"] == "NGUYỄN HOÀI NAM"
    assert r["gender"] == "Nam"
    assert r["nationality"] == "Việt Nam"
    assert r["place_of_origin"] == "Xã Phú Lương, Hà Đông, Hà Nội"
    assert r["place_of_residence"] == "Số 12 ngõ 34, Đống Đa, Hà Nội"
    assert (r["id_number"], r["date_of_birth"]) == ("001099012345", "15/08/1999")


def test_female_on_same_line_as_nationality():
    r = parse_front_cccd(front(sex="Nữ", id_no="001303012345", dob="01/02/2003", same_line_nat=True))
    assert r["gender"] == "Nữ"
    assert r["nationality"] == "Việt Nam"


def test_ocr_without_diacritics():
    r = parse_front_cccd(R([
        "CAN CUOC CONG DAN", "So / No.: 079095001234", "Ho va ten / Full name:", "TRAN THI LAN",
        "Ngay sinh / Date of birth: 03/04/1995", "Gioi tinh / Sex: Nu",
    ]))
    assert (r["id_number"], r["full_name"], r["gender"], r["date_of_birth"]) == \
        ("079095001234", "TRAN THI LAN", "Nữ", "03/04/1995")


def test_fields_and_address_not_truncated():
    r = parse_front_cccd(front())
    assert r["place_of_residence"] == "Số 12 Ngõ 34, Phường Dịch Vọng, Cầu Giấy, Hà Nội"
    assert r["place_of_origin"] == "Xã Tân Lập, Huyện Đan Phượng, Hà Nội"
    assert r["date_of_expiry"] == "12/05/2028"


@pytest.mark.parametrize("raw,expected", [
    ("Số / No.: 001 203 012 345", "001203012345"),
    ("Số / No.: 001.203.012.345", "001203012345"),
    ("Số / No.: OO12O3O12345", "001203012345"),   # OCR đọc 0 thành O
    ("Số / No.: 0012030123456", None),              # 13 số → không tự cắt
])
def test_id_number_extraction(raw, expected):
    r = parse_front_cccd(R(["CĂN CƯỚC CÔNG DÂN", raw]))
    assert r["id_number"] == expected


def test_invalid_calendar_date_rejected():
    r = parse_front_cccd(R(["CĂN CƯỚC CÔNG DÂN", "Ngày sinh / Date of birth: 31/02/2003"]))
    assert r["date_of_birth"] is None


# ---------------------------------------------------------------- bố cục
def test_layout_rejects_non_id_documents():
    assert not detect_cccd_layout(["HÓA ĐƠN TIỀN ĐIỆN", "Số: 12", "Ngày sinh hoạt", "NOI DUNG"], "front")["is_layout_valid"]
    assert not detect_cccd_layout(["CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM", "Ngày 1 tháng 2 năm 2024"], "back")["is_layout_valid"]


def test_layout_accepts_real_layouts():
    texts = [t for _, t, _ in front()]
    assert detect_cccd_layout(texts, "front")["is_layout_valid"]
    back_old = ["Đặc điểm nhận dạng: Nốt ruồi", "Ngày 15 tháng 03 năm 2021", "CỤC TRƯỞNG CỤC CẢNH SÁT"]
    assert detect_cccd_layout(back_old, "back")["is_layout_valid"]
    back_2024 = ["Nơi cư trú / Place of residence: Hà Nội", "Ngày, tháng, năm cấp / Date of issue: 15/03/2024",
                 "BỘ CÔNG AN"]
    assert detect_cccd_layout(back_2024, "back")["is_layout_valid"]


# ---------------------------------------------------------------- số CCCD + đối chiếu
def test_validate_number_century_and_gender():
    v = validate_cccd_number("001303012345")
    assert v["is_valid"] and v["gender"] == "Nữ" and v["birth_year"] == 2003
    assert validate_cccd_number("001003012345")["birth_year"] == 1903
    assert not validate_cccd_number("999203012345")["is_valid"]


def _verify(ocr_data, side="front"):
    quality = {"is_resolution_ok": True, "is_blurry": False, "is_brightness_ok": True, "warnings": [],
               "resolution": "1000x630", "blur_score": 300.0, "brightness": 120.0}
    screen = {"is_likely_screen_capture": False, "warning": None, "high_freq_energy": 4.0}
    texts = ["CĂN CƯỚC CÔNG DÂN", "Họ và tên", "Ngày sinh", "Giới tính"] if side == "front" else \
        ["Đặc điểm nhận dạng", "Ngày 15 tháng 03 năm 2021"]
    return build_verification(side, ocr_data, quality, screen, detect_cccd_layout(texts, side))


def test_cross_check_detects_dob_and_gender_mismatch():
    data = parse_front_cccd(front(sex="Nam", dob="12/05/1998", id_no="001303012345"))
    v = _verify(data)
    assert v["checks"]["id_matches_dob"] is False
    assert v["checks"]["id_matches_gender"] is False
    assert v["is_valid_format_and_quality"] is False
    assert any("không khớp" in w for w in v["warnings"])


def test_consistent_card_is_valid():
    v = _verify(parse_front_cccd(front()))
    assert v["is_valid_format_and_quality"] is True
    assert v["checks"]["id_matches_dob"] and v["checks"]["id_matches_gender"]
    assert set(v["checks"]) >= {"image_quality_ok", "layout_detected", "no_screen_capture", "id_format_valid"}


def test_not_valid_without_id_or_name():
    """Bản cũ: chỉ cần 4/6 tiêu chí là 'đạt' dù không đọc được số CCCD."""
    data = parse_front_cccd(front())
    data["id_number"] = None
    assert _verify(data)["is_valid_format_and_quality"] is False


# ---------------------------------------------------------------- mặt sau + MRZ
def _mrz(id12="001203012345", dob="030512", sex="M", exp="280512"):
    doc = id12[-9:]
    l1 = f"IDVNM{doc}{mrz_check_digit(doc)}{id12}".ljust(30, "<")[:30]
    l2 = f"{dob}{mrz_check_digit(dob)}{sex}{exp}{mrz_check_digit(exp)}VNM".ljust(29, "<") + "0"
    l3 = "NGUYEN<<VAN<AN".ljust(30, "<")
    return [l1, l2, l3]


def test_mrz_parsed_and_check_digits_verified():
    m = parse_mrz(_mrz())
    assert m["is_valid"] and m["full_id"] == "001203012345" and m["full_id_consistent"]
    assert m["sex"] == "Nam" and m["name"] == "NGUYEN VAN AN"


def test_mrz_wrong_check_digit_flagged():
    lines = _mrz()
    lines[1] = lines[1][:6] + str((int(lines[1][6]) + 1) % 10) + lines[1][7:]
    assert parse_mrz(lines)["dob_valid"] is False


def test_mrz_ocr_spaces_and_guillemets():
    lines = [l.replace("<", "«") for l in _mrz()]
    lines[0] = " ".join(lines[0][i:i + 5] for i in range(0, 30, 5))
    assert parse_mrz(lines)["is_valid"]


def test_back_issue_date_not_confused_with_expiry():
    r = parse_back_cccd(R(["Có giá trị đến: 12/05/2028", "Ngày 15 tháng 03 năm 2021", "CỤC TRƯỞNG CỤC CẢNH SÁT"]))
    assert r["issue_date"] == "15/03/2021"
    assert r["issuing_authority"] == "Cục Cảnh sát QLHC về TTXH"
    r2 = parse_back_cccd(R(["Ngày, tháng, năm hết hạn / Date of expiry: 12/05/2034",
                            "Ngày, tháng, năm cấp / Date of issue: 15/03/2024", "BỘ CÔNG AN"]))
    assert r2["issue_date"] == "15/03/2024" and r2["date_of_expiry"] == "12/05/2034"


def test_back_with_mrz_valid():
    r = parse_back_cccd(R(["Đặc điểm nhận dạng: Nốt ruồi", "Ngày 15 tháng 03 năm 2021"] + _mrz()))
    v = _verify(r, side="back")
    assert v["checks"]["mrz_valid"] is True and v["is_valid_format_and_quality"] is True
