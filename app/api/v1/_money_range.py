from datetime import date, datetime, timedelta
from typing import List, Optional, Tuple

from app.api.v1._live_data import GIO_VN, cac_ngay
from app.api.v1._mart import doc_khoang
from app.api.v1._template import invalid_param

THANG = {"thisMonth": "tháng này", "lastMonth": "tháng trước"}
TOI_DA_NGAY = 366


def _ngay_tu_chon(tu: Optional[str], den: Optional[str], hom_nay: date) -> Tuple[date, date]:
    try:
        a, b = date.fromisoformat(tu or ""), date.fromisoformat(den or "")
    except ValueError:
        invalid_param("from_date", "YYYY-MM-DD")
    if a > b or b > hom_nay or (b - a).days >= TOI_DA_NGAY:
        invalid_param("from_date", f"from_date <= to_date <= hôm nay, tối đa {TOI_DA_NGAY} ngày")
    return a, b


def doc_khoang_tien(time_range: str, hom_nay: Optional[date] = None,
                    tu: Optional[str] = None, den: Optional[str] = None) -> Tuple[List[str], str]:
    """(các ngày trong khoảng, nhãn để hiển thị). Nhận 7d/30d/90d, tháng dương lịch, hoặc custom + tu/den."""
    cuoi = hom_nay or datetime.now(GIO_VN).date()
    if time_range == "custom":
        dau, cuoi = _ngay_tu_chon(tu, den, cuoi)
        nhan = f"{dau:%d/%m} – {cuoi:%d/%m/%Y}"
    elif time_range not in THANG:
        n = doc_khoang(time_range)
        return cac_ngay(n), f"{n} ngày qua"
    else:
        dau = cuoi.replace(day=1)
        nhan = THANG[time_range]
    if time_range == "lastMonth":
        cuoi = dau - timedelta(days=1)
        dau = cuoi.replace(day=1)
    return [(dau + timedelta(days=i)).isoformat() for i in range((cuoi - dau).days + 1)], nhan
