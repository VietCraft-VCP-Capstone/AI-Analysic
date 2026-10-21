from app.api.v1._live_data import doanh_thu_ngay
from app.api.v1._template import build_meta, insufficient
from app.core.build_marts import TOI_THIEU_LICH_SU, du_bao_chuoi


def _meta(shop_id: str, model: str, n: int, can: int):
    return build_meta(model_version=model, scope="shop", scope_id=shop_id, database="vietcraft",
                      collection="orders", mode="live", attributed_to_live_shop=True, sample_size=n,
                      confidence="medium" if n >= can else "low",
                      unlock={"requirement": "ngày lịch sử doanh thu", "unit": "ngày",
                              "current": n, "target": can})


def forecast_live(shop_id: str, h: int):
    ngay, y = doanh_thu_ngay(shop_id)
    meta = _meta(shop_id, "live-forecast-1.0", len(ngay), TOI_THIEU_LICH_SU)
    kq = du_bao_chuoi(ngay, y) if ngay else None
    if kq is None:
        return insufficient(
            f"Shop mới có {len(ngay)} ngày lịch sử doanh thu, cần tối thiểu {TOI_THIEU_LICH_SU} "
            f"ngày để mô hình có căn cứ.", meta)
    return kq["points"][:h], kq["so_sanh"], meta
