
import logging
import pandas as pd
import numpy as np
from datetime import datetime, date, timedelta
from typing import Union, Dict, Any, Optional, List

# Bảng ngày mùng 1 Tết Nguyên Đán (Dương lịch).
# Mở rộng tới 2030: dự báo 12 tuần tính từ cuối 2026 sẽ chạm sang 2027, và bảng
# cũ dừng ở 2026 làm get_tet_date() ném lỗi ngay giữa kỳ dự báo.
TET_DATES: Dict[int, str] = {
    2021: "2021-02-12",
    2022: "2022-02-01",
    2023: "2023-01-22",
    2024: "2024-02-10",
    2025: "2025-01-29",
    2026: "2026-02-17",
    2027: "2027-02-06",
    2028: "2028-01-26",
    2029: "2029-02-13",
    2030: "2030-02-03",
}

# Các ngày lễ cố định dương lịch tại Việt Nam (tháng, ngày)
VN_HOLIDAYS_SOLAR = {
    (1, 1): "Tết Dương Lịch",
    (4, 30): "Giải phóng Miền Nam",
    (5, 1): "Quốc tế Lao Động",
    (9, 2): "Quốc Khánh",
    (10, 20): "Phụ nữ Việt Nam",
    (11, 20): "Nhà giáo Việt Nam",
    (12, 24): "Giáng Sinh",
    (2, 14): "Valentine",
    (3, 8): "Quốc tế Phụ nữ",
}


def get_tet_date(year: int) -> pd.Timestamp:
    """Trả về ngày mùng 1 Tết của một năm nhất định."""
    if year in TET_DATES:
        return pd.Timestamp(TET_DATES[year])
    raise ValueError(f"Chưa có cấu hình ngày Tết cho năm {year} (hỗ trợ 2021–2030).")


def days_to_tet(date_val: Union[str, datetime, date, pd.Timestamp]) -> int:
    """
    Tính số ngày cách Tết Nguyên Đán gần nhất.
    - Giá trị âm (-k): k ngày TRƯỚC Tết.
    - Giá trị 0: Đúng mùng 1 Tết.
    - Giá trị dương (+k): k ngày SAU Tết.
    """
    ts = pd.to_datetime(date_val)
    year = ts.year

    candidate_years = [y for y in [year - 1, year, year + 1] if y in TET_DATES]
    if not candidate_years:
        raise ValueError(f"Không tìm thấy năm Tết phù hợp cho ngày {date_val}")

    diffs = [(ts - pd.Timestamp(TET_DATES[y])).days for y in candidate_years]
    min_diff = min(diffs, key=abs)
    return int(min_diff)


def is_vn_holiday(date_val: Union[str, datetime, date, pd.Timestamp]) -> bool:
    """Kiểm tra một ngày có phải ngày lễ hoặc cận Tết (trong vòng +- 7 ngày Tết) hay không."""
    ts = pd.to_datetime(date_val)
    if (ts.month, ts.day) in VN_HOLIDAYS_SOLAR:
        return True
    if abs(days_to_tet(ts)) <= 7:
        return True
    return False


def get_tet_aligned_series(series: pd.Series) -> pd.DataFrame:
    """
    Chuyển chuỗi thời gian nhiều năm sang trục ngày cách Tết (-60 đến +30 ngày).
    Trả về DataFrame gồm: observed_on, value, year, days_to_tet.
    """
    df = series.reset_index()
    df.columns = ["observed_on", "value"]
    df["observed_on"] = pd.to_datetime(df["observed_on"])
    df["year"] = df["observed_on"].dt.year
    df["days_to_tet"] = df["observed_on"].apply(days_to_tet)
    return df


MID_AUTUMN_DATES: Dict[int, str] = {
    2021: "2021-09-21",
    2022: "2022-09-10",
    2023: "2023-09-29",
    2024: "2024-09-17",
    2025: "2025-10-06",
    2026: "2026-09-25",
    2027: "2027-09-15",
    2028: "2028-10-03",
    2029: "2029-09-22",
    2030: "2030-09-12",
}

_MISSING_LOGGED: set = set()

ALL_GROUPS = ["fashion", "bags", "shoes", "accessories", "home", "sport"]


def _fixed(month: int, day: int):
    return lambda year: date(year, month, day)


def _black_friday(year: int) -> date:
    first = date(year, 11, 1)
    thursday = first + timedelta(days=(3 - first.weekday()) % 7 + 21)
    return thursday + timedelta(days=1)


SHOPPING_EVENTS = [
    {"key": "tet", "name": "Tết Nguyên Đán", "prep_days": 45, "lead_time_days": 18, "groups": ALL_GROUPS,
     "date_fn": lambda y: date.fromisoformat(TET_DATES[y]), "icon": "sparkles", "badge": "Đỉnh điểm sức mua toàn sàn",
     "category_focus": "Quà biếu Tết, bao lì xì, áo dài cách tân, hộp quà gỗ/gốm, vật phẩm phong thủy",
     "default_search_keywords": ["quà tết", "lì xì tết", "áo tết", "trang trí tết", "hộp quà tết"]},
    {"key": "valentine", "name": "Valentine 14/2", "prep_days": 28, "lead_time_days": 10,
     "groups": ["fashion", "bags", "accessories"], "date_fn": _fixed(2, 14), "icon": "heart", "badge": "Mùa quà tặng tình nhân",
     "category_focus": "Áo đôi, ly sứ đôi in tên, móc khóa khắc ngày kỷ niệm, thiệp gỗ hoa khô",
     "default_search_keywords": ["quà valentine", "áo đôi", "quà tặng người yêu", "cốc in hình"]},
    {"key": "8/3", "name": "Quốc tế Phụ nữ 8/3", "prep_days": 28, "lead_time_days": 10,
     "groups": ["fashion", "bags", "accessories", "home"], "date_fn": _fixed(3, 8), "icon": "flower", "badge": "Tri ân phái đẹp",
     "category_focus": "Set quà công ty/B2B, nến thơm, túi vải canvas hoa nhí, trang sức mộc",
     "default_search_keywords": ["quà 8/3", "quà tặng mẹ", "quà tặng bạn thân", "túi tote"]},
    {"key": "30/4", "name": "Lễ 30/4 & 1/5 (Hè du lịch)", "prep_days": 30, "lead_time_days": 12,
     "groups": ["fashion", "shoes", "sport"], "date_fn": _fixed(4, 30), "icon": "sun", "badge": "Mùa du lịch dã ngoại",
     "category_focus": "Áo thun du lịch, mũ nón, túi tote đi biển, bình giữ nhiệt",
     "default_search_keywords": ["áo thun", "áo phông nam", "áo phông nữ", "in áo thun", "túi tote"]},
    {"key": "1/6", "name": "Quốc tế Thiếu nhi 1/6", "prep_days": 21, "lead_time_days": 9,
     "groups": ["fashion", "shoes", "sport"], "date_fn": _fixed(6, 1), "icon": "smile", "badge": "Quà tặng trẻ em & gia đình",
     "category_focus": "Áo gia đình, đồ chơi gỗ mộc, gối ôm in hình thú",
     "default_search_keywords": ["áo gia đình", "quà tặng", "móc khóa"]},
    {"key": "khai_giang", "name": "Tựu trường & Khai giảng 5/9", "prep_days": 35, "lead_time_days": 14,
     "groups": ["bags", "shoes", "fashion", "sport", "accessories"], "date_fn": _fixed(9, 5), "icon": "backpack", "badge": "Mùa học sinh & áo lớp",
     "category_focus": "Áo lớp/áo nhóm theo yêu cầu, balo canvas, sổ tay bìa da, móc khóa thẻ tên",
     "default_search_keywords": ["áo lớp", "áo nhóm", "áo đồng phục", "túi tote", "móc khóa"]},
    {"key": "trung_thu", "name": "Tết Trung Thu", "prep_days": 30, "lead_time_days": 12,
     "groups": ["home", "fashion", "accessories"],
     "date_fn": lambda y: date.fromisoformat(MID_AUTUMN_DATES[y]), "icon": "moon", "badge": "Tết đoàn viên truyền thống",
     "category_focus": "Hộp bánh trà quà tặng, lồng đèn giấy mộc, áo thun đoàn viên gia đình",
     "default_search_keywords": ["quà trung thu", "áo gia đình", "quà tặng"]},
    {"key": "20/10", "name": "Phụ nữ Việt Nam 20/10", "prep_days": 28, "lead_time_days": 10,
     "groups": ["fashion", "bags", "accessories", "home"], "date_fn": _fixed(10, 20), "icon": "heart", "badge": "Mùa quà tặng thu đông",
     "category_focus": "Set quà tri ân mẹ & cô giáo, khăn choàng, bình gốm cắm hoa mộc",
     "default_search_keywords": ["quà 20/10", "quà tặng mẹ", "quà tặng người yêu"]},
    {"key": "halloween", "name": "Lễ hội Halloween 31/10", "prep_days": 28, "lead_time_days": 10,
     "groups": ["fashion", "accessories", "home"], "date_fn": _fixed(10, 31), "icon": "ghost", "badge": "Trang phục cá tính & Decor",
     "category_focus": "Áo hoodie nỉ đen gothic, cốc sứ tạo hình, sticker & tranh canvas ma mị",
     "default_search_keywords": ["áo hoodie", "áo oversize", "móc khóa", "poster trang trí"]},
    {"key": "11/11", "name": "Siêu sale 11/11", "prep_days": 21, "lead_time_days": 7,
     "groups": ALL_GROUPS, "date_fn": _fixed(11, 11), "icon": "zap", "badge": "Đại hội sale đầu mùa đông",
     "category_focus": "Combo giảm giá, quà tặng kèm, áo nỉ ấm, đồ decor phòng",
     "default_search_keywords": ["áo hoodie", "áo thun", "cốc in hình"]},
    {"key": "20/11", "name": "Nhà giáo Việt Nam 20/11", "prep_days": 28, "lead_time_days": 10,
     "groups": ["fashion", "bags", "accessories", "home"], "date_fn": _fixed(11, 20), "icon": "book-open", "badge": "Mùa quà tặng tri ân",
     "category_focus": "Sổ da khắc tên, bút gỗ kỷ niệm, bình giữ nhiệt in câu chúc, tranh chữ mộc",
     "default_search_keywords": ["quà 20/11", "quà tặng thầy cô", "quà lưu niệm"]},
    {"key": "12/12", "name": "Siêu sale 12/12", "prep_days": 21, "lead_time_days": 7,
     "groups": ALL_GROUPS, "date_fn": _fixed(12, 12), "icon": "shopping-bag", "badge": "Xả kho & Kích cầu cuối năm",
     "category_focus": "Set quà Noel sớm, áo khoác nỉ, đồ trang trí năm mới",
     "default_search_keywords": ["áo hoodie", "quà tặng", "áo vintage"]},
    {"key": "noel", "name": "Giáng Sinh & Năm Mới 24/12", "prep_days": 35, "lead_time_days": 12,
     "groups": ["fashion", "shoes", "accessories", "home"], "date_fn": _fixed(12, 24), "icon": "snowflake", "badge": "Mùa lễ hội cuối năm",
     "category_focus": "Áo len giáng sinh, ly sứ Noel, set quà tất ấm, tranh treo tường mùa đông",
     "default_search_keywords": ["quà giáng sinh", "áo giáng sinh", "trang trí noel", "áo hoodie"]},
]


def calculate_occasion_window(ev: Dict[str, Any], hom_nay: date) -> Optional[Dict[str, Any]]:
    """
    Tính cửa sổ hành động 4 pha cho một dịp:
    - Pha 1 (R&D / Lên kệ): Chuẩn bị mẫu, chụp ảnh sản phẩm, lên listing.
    - Pha 2 (Đẩy số / Thử nhỏ): Chạy thử ngân sách nhỏ, thu thập đánh giá đầu tiên.
    - Pha 3 (Cao điểm bán hàng / Thu hoạch): Sức mua mạnh nhất, duy trì quảng cáo chuyển đổi.
    - Pha 4 (Hạn chốt đơn): Hạn cuối chốt đơn để xưởng sản xuất và ship kịp giao trước sự kiện.
    
    Quy tắc an toàn: Sau hạn chốt đơn, đóng cổng giao thường để tránh bom hàng/hoàn đơn.
    """
    lead_time = ev.get("lead_time_days", 14)  # Thời gian in p90 + ship p90 + buffer 2 ngày
    prep_days = ev.get("prep_days", 30)       # Tổng số ngày chuẩn bị trước ngày lễ

    # Tìm năm phù hợp: chọn năm gần nhất mà hạn chốt đơn >= hôm nay
    # Nếu sự kiện năm nay đã qua hạn chốt đơn thì chuyển sang kỳ năm sau
    target_event_date = None
    for y in (hom_nay.year, hom_nay.year + 1):
        try:
            ev_d = ev["date_fn"](y)
            cut_off_d = ev_d - timedelta(days=lead_time)
            if cut_off_d >= hom_nay:
                target_event_date = ev_d
                break
        except (KeyError, ValueError):
            continue

    if not target_event_date:
        # Nếu đã qua hết năm tới hoặc không tìm được, lấy năm tiếp theo
        try:
            target_event_date = ev["date_fn"](hom_nay.year + 1)
        except Exception:
            return None

    event_date = target_event_date
    cut_off_date = event_date - timedelta(days=lead_time)
    peak_start = cut_off_date - timedelta(days=max(7, int(prep_days * 0.4)))
    traction_start = cut_off_date - timedelta(days=max(14, int(prep_days * 0.75)))
    rd_start = cut_off_date - timedelta(days=prep_days)

    days_to_cut_off = (cut_off_date - hom_nay).days
    days_to_event = (event_date - hom_nay).days
    days_to_rd = (rd_start - hom_nay).days

    # Xác định trạng thái và pha hiện tại
    if days_to_cut_off < 0:
        status = "passed"
        phase = "passed"
        phase_label = "Đã qua hạn chốt đơn dịp này"
        badge_tone = "neutral"
    elif days_to_rd > 0:
        status = "upcoming"
        phase = "early"
        phase_label = f"Sắp tới hạn chuẩn bị (còn {days_to_rd} ngày)"
        badge_tone = "neutral"
    elif hom_nay < traction_start:
        status = "active"
        phase = "rd_sprint"
        phase_label = f"Pha 1: Lên mẫu & Đăng bán (còn {days_to_cut_off} ngày chốt đơn)"
        badge_tone = "info"
    elif hom_nay < peak_start:
        status = "active"
        phase = "traction"
        phase_label = f"Pha 2: Đẩy số & Thử nhỏ (còn {days_to_cut_off} ngày chốt đơn)"
        badge_tone = "warn"
    else:
        status = "active"
        phase = "peak"
        phase_label = f"Pha 3: Cao điểm bán hàng (chỉ còn {days_to_cut_off} ngày trước hạn chốt đơn!)"
        badge_tone = "good"

    return {
        "event_key": ev["key"],
        "event_name": ev["name"],
        "event_date": event_date.isoformat(),
        "cut_off_date": cut_off_date.isoformat(),
        "peak_start": peak_start.isoformat(),
        "traction_start": traction_start.isoformat(),
        "rd_start": rd_start.isoformat(),
        "lead_time_days": lead_time,
        "days_to_cut_off": days_to_cut_off,
        "days_to_event": days_to_event,
        "status": status,
        "current_phase": phase,
        "phase_label": phase_label,
        "badge_tone": badge_tone,
        "cut_off_formula": f"Ngày sự kiện ({event_date.strftime('%d/%m')}) − Thời gian sản xuất p90 & giao hàng ({lead_time} ngày)",
    }


def upcoming_events(d: date, weeks: int = 12) -> list:
    d = pd.Timestamp(d).date()
    end = d + timedelta(weeks=weeks)
    found = []
    for ev in SHOPPING_EVENTS:
        win = calculate_occasion_window(ev, d)
        if not win:
            continue
        ev_date = date.fromisoformat(win["event_date"])
        if d <= ev_date <= end or win["status"] == "active":
            found.append({
                "key": ev["key"],
                "name": ev["name"],
                "date": ev_date,
                "window": win,
                "groups": list(ev["groups"]),
                "icon": ev.get("icon", "calendar"),
                "badge": ev.get("badge", ""),
                "category_focus": ev.get("category_focus", ""),
                "default_search_keywords": ev.get("default_search_keywords", [])
            })
    return sorted(found, key=lambda e: e["date"])



if __name__ == "__main__":
    print("=== TỰ KIỂM TRA MODULE CALENDAR_VN.PY ===")
    
    # 1. Kiểm tra tính đúng ngày cách Tết
    assert days_to_tet("2023-01-20") == -2, "20/01/2023 phải là -2 ngày trước Tết 2023 (22/01)"
    assert days_to_tet("2026-02-15") == -2, "15/02/2026 phải là -2 ngày trước Tết 2026 (17/02)"
    assert days_to_tet("2024-02-10") == 0, "10/02/2024 phải là đúng mùng 1 Tết 2024"
    assert days_to_tet("2024-02-15") == 5, "15/02/2024 phải là +5 ngày sau Tết 2024"
    print("✓ Kiểm tra days_to_tet: Chính xác 100% trên các mốc thực tế.")

    # 2. Thử nghiệm đổi trục mô phỏng dữ liệu 5 năm
    sample_dates = pd.date_range("2021-01-01", "2026-03-01", freq="W-SUN")
    # Giả lập tín hiệu đỉnh vào đúng 2 tuần trước Tết
    values = []
    for d in sample_dates:
        dtet = days_to_tet(d)
        val = 100.0 * np.exp(-0.5 * ((dtet - (-14)) / 7) ** 2) + 10.0
        values.append(val)
    
    s = pd.Series(values, index=sample_dates)
    aligned = get_tet_aligned_series(s)
    
    # Đỉnh khi gom theo ngày cách Tết phải nằm trong khoảng [-21, -7]
    peak_dtet = aligned.groupby("days_to_tet")["value"].mean().idxmax()
    print(f"✓ Đỉnh mùa vụ sau khi đổi trục: ngày {peak_dtet} (trước Tết ~2 tuần)")
    assert -21 <= peak_dtet <= -7, f"Đỉnh mùa vụ sai lệch: {peak_dtet}"

    # 3. Kiểm tra tính cửa sổ dịp và hạn chốt đơn
    tet_ev = next(e for e in SHOPPING_EVENTS if e["key"] == "tet")
    # Ngày 10/12/2026: Tết 2027 rơi vào 06/02/2027. Lead time 18 ngày -> cut off 19/01/2027.
    # Ngày 10/12/2026 nằm trong khoảng chuẩn bị (cách cut-off 40 ngày) -> phải ACTIVE, không được bỏ qua sang năm sau!
    win_tet = calculate_occasion_window(tet_ev, date(2026, 12, 10))
    assert win_tet is not None
    assert win_tet["status"] == "active", f"Tết ngày 10/12/2026 phải active, nhưng nhận {win_tet['status']}"
    assert win_tet["days_to_cut_off"] == 40
    print(f"✓ Cửa sổ Tết ngày 10/12/2026: {win_tet['status']} - {win_tet['phase_label']}")

    # Noel 2026 (24/12): lead time 12 ngày -> cut-off 12/12. Ngày 10/12 -> còn 2 ngày chốt đơn -> peak phase!
    noel_ev = next(e for e in SHOPPING_EVENTS if e["key"] == "noel")
    win_noel = calculate_occasion_window(noel_ev, date(2026, 12, 10))
    assert win_noel is not None
    assert win_noel["status"] == "active" and win_noel["days_to_cut_off"] == 2
    print(f"✓ Cửa sổ Noel ngày 10/12/2026: {win_noel['status']} - {win_noel['phase_label']}")

    # 4. Kiểm tra hỗ trợ tới 2030
    assert get_tet_date(2030) == pd.Timestamp("2030-02-03")
    print("✓ get_tet_date(2030) hoạt động chuẩn xác.")

    print("✅ TẤT CẢ SELF-CHECKS CỦA CALENDAR_VN.PY ĐÃ PASS!")
