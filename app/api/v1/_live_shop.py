from typing import Optional

from app.api.v1._live_data import cac_ngay, doanh_thu_ngay
from app.api.v1._template import build_meta, insufficient
from app.core.build_marts import SO_NGAY_TOI_THIEU_BAT_THUONG, TOI_THIEU_LICH_SU, bat_thuong_chuoi, du_bao_chuoi

LY_DO_BO_QUA = {
    "qua_ngan": "Shop mới có {n} ngày lịch sử doanh thu, cần ít nhất {can} ngày để biết mức bình thường.",
    "qua_thua": "Dưới 40% số ngày có doanh thu nên mức nền là 0, mọi ngày có bán sẽ bị coi là đột biến. Chưa dò được.",
    "khong_tin_cay": "Chuỗi doanh thu quá nhọn, tỉ lệ cảnh báo vượt ngưỡng tin cậy nên không đưa ra cảnh báo.",
    "loi": "Không phân tích được chuỗi doanh thu của shop.",
}


def _meta(shop_id: str, model: str, n: int, can: int):
    return build_meta(model_version=model, scope="shop", scope_id=shop_id, database="vietcraft",
                      collection="orders", mode="live", attributed_to_live_shop=True, sample_size=n,
                      confidence="medium" if n >= can else "low",
                      unlock={"requirement": "ngày lịch sử doanh thu", "unit": "ngày",
                              "current": n, "target": can})


def alerts_live(shop_id: str, so_ngay: Optional[int]):
    ngay, gia_tri = doanh_thu_ngay(shop_id)
    su_kien, ly_do = bat_thuong_chuoi(ngay, gia_tri) if ngay else (None, "qua_ngan")
    tu = cac_ngay(so_ngay)[0] if so_ngay else ""
    rows = sorted((e for e in su_kien or [] if e["event_date"] >= tu),
                  key=lambda e: e["event_date"], reverse=True)
    limitation = None if su_kien is not None else LY_DO_BO_QUA[ly_do].format(
        n=len(ngay), can=SO_NGAY_TOI_THIEU_BAT_THUONG)
    return rows, su_kien is not None, limitation, _meta(
        shop_id, "live-anomaly-1.0", len(ngay), SO_NGAY_TOI_THIEU_BAT_THUONG)


def forecast_live(shop_id: str, h: int):
    ngay, y = doanh_thu_ngay(shop_id)
    meta = _meta(shop_id, "live-forecast-1.0", len(ngay), TOI_THIEU_LICH_SU)
    kq = du_bao_chuoi(ngay, y) if ngay else None
    if kq is None:
        return insufficient(
            f"Shop mới có {len(ngay)} ngày lịch sử doanh thu, cần tối thiểu {TOI_THIEU_LICH_SU} "
            f"ngày để mô hình có căn cứ.", meta)
    return kq["points"][:h], kq["so_sanh"], meta
