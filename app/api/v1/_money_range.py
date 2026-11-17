from datetime import date, datetime, timedelta
from typing import List, Optional, Tuple

from app.api.v1._live_data import GIO_VN, cac_ngay
from app.api.v1._mart import doc_khoang

THANG = {"thisMonth": "tháng này", "lastMonth": "tháng trước"}


def doc_khoang_tien(time_range: str, hom_nay: Optional[date] = None) -> Tuple[List[str], str]:
    """(các ngày trong khoảng, nhãn để hiển thị). Ngoài 7d/30d/90d còn nhận tháng dương lịch."""
    if time_range not in THANG:
        n = doc_khoang(time_range)
        return cac_ngay(n), f"{n} ngày qua"
    cuoi = hom_nay or datetime.now(GIO_VN).date()
    dau = cuoi.replace(day=1)
    if time_range == "lastMonth":
        cuoi = dau - timedelta(days=1)
        dau = cuoi.replace(day=1)
    return [(dau + timedelta(days=i)).isoformat() for i in range((cuoi - dau).days + 1)], THANG[time_range]
