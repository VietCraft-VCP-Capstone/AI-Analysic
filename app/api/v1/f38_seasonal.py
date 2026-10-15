import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from fastapi import APIRouter

from app.api.v1._mart import db
from app.api.v1._template import CurrentShop, insufficient, mart_not_ready, meta_from_record, ok

router = APIRouter()

MART = "seasonal_profile"
LUI_SAN_XUAT = 21       # BR-209: in + giao
TOP_N = 10


def _cua_so_ra_hang(tuan: int, hom_nay: date):
    """Từ tuần đỉnh lùi về cửa sổ nên tung hàng, cho lần TỚI sắp đến.

    Năm phải suy từ hôm nay, không phải từ ngày mẫu lịch sử: đỉnh "quà tết" quan
    sát được ở tuần 1 năm 2023 thì cửa sổ tung hàng cần tính cho Tết SẮP TỚI.
    Lấy nhầm năm mẫu thì lịch ra 2023 — đã vào dĩ vãng, người bán mở ra là vô dụng.
    """
    tuan = max(1, min(52, tuan))
    for nam in (hom_nay.year, hom_nay.year + 1, hom_nay.year + 2):
        try:
            dinh = date.fromisocalendar(nam, tuan, 1)
        except ValueError:
            continue
        if dinh - timedelta(days=LUI_SAN_XUAT + 21) > hom_nay:
            break
    else:
        return None
    return {"peak_week": f"{dinh.isocalendar()[0]}-W{tuan:02d}",
            "peak_date": dinh.isoformat(),
            "start": (dinh - timedelta(days=LUI_SAN_XUAT + 21)).isoformat(),
            "end": (dinh - timedelta(days=LUI_SAN_XUAT)).isoformat(),
            "basis": f"lùi {LUI_SAN_XUAT} ngày cho in và giao (BR-209), cộng 3 tuần bán"}


@router.get("/api/analytics/forecast/seasonal", tags=["F38 · Hưng"])
def seasonal(shop_id: str = CurrentShop, categoryId: Optional[str] = None,
             keyword: Optional[str] = None):
    coll = db()[MART]
    if coll.estimated_document_count() == 0:
        mart_not_ready(MART)

    loc = {"entity_id": keyword} if keyword else {}
    if categoryId and not keyword:
        tag_cat = [t["tag_id"] for t in db()["tags"].find(
            {"category_id": {"$regex": f"^{categoryId}"}}, {"tag_id": 1})]
        if tag_cat:
            loc = {"tag_ids": {"$in": tag_cat}}

    rows = list(coll.find(loc, {"_id": 0}).sort("amplitude", -1).limit(TOP_N))
    if not rows:
        return insufficient(
            f"Chưa có chuỗi mùa vụ nào khớp bộ lọc. Job chỉ phân rã từ khoá có "
            f"từ 104 tuần dữ liệu trở lên (BR-208).")

    meta = meta_from_record(rows[0], scope="keyword", scope_id=rows[0]["entity_id"],
                            collection=MART, mode="live",   # Google Trends VN thật
                            sample_size=len(rows), identity_linked=False, confidence="high")

    # Mốc "hôm nay" lấy từ dữ liệu, không lấy đồng hồ hệ thống — cùng lý do với
    # các endpoint khác: dữ liệu dừng ở 2026-08-30.
    ld = db()["listing_daily"].find_one({}, {"date": 1}, sort=[("date", -1)])
    hom_nay = datetime.strptime(ld["date"], "%Y-%m-%d").date() if ld else date.today()

    co_mua = [r for r in rows if r.get("has_seasonality")]

    if not co_mua:
        return insufficient(
            "MSG150 — ngành hàng này có nhu cầu ổn định quanh năm, không có đỉnh mùa vụ "
            "đủ rõ để đặt lịch tung hàng.", meta)

    chinh = co_mua[0]
    return ok({
        "keyword": chinh["entity_id"],
        "tag_ids": chinh.get("tag_ids"),
        "decomposition": {
            "trend": chinh["trend"],
            "seasonal": chinh["seasonal"],
            "residual": chinh["residual"],
            "window": "52 tuần gần nhất",
        },
        "amplitude": chinh["amplitude"],
        "n_points": chinh.get("n_points"),
        "events": [{
            "name": r["entity_id"],
            "peak_week_of_year": int(r["period_value"]),
            "amplitude": r["amplitude"],
            "launch_window": _cua_so_ra_hang(int(r["period_value"]), hom_nay),
        } for r in co_mua],
        "flat_keywords": [r["entity_id"] for r in rows if not r.get("has_seasonality")],
        "method": "STL Loess, period=52 tuần, robust=True",
        "limitation": ("Phân rã trên Google Trends — đo NHU CẦU TÌM KIẾM, không phải "
                       "doanh số. Đỉnh tìm kiếm thường đi trước đỉnh mua hàng."),
    }, meta)
