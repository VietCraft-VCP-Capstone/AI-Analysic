import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from fastapi import APIRouter

from app.api.v1._mart import db
from app.api.v1._template import CurrentShop, mart_not_ready, meta_from_record, ok, build_meta
from app.core.listing_intel.trend_store import weekly_series

router = APIRouter()

MART = "mart_demand"
TOP_N = 10
MIN_POINTS = 8
NEN_TOI_THIEU = 5.0

# Ánh xạ từ khóa về trục ngành lớn (5–8 trục theo SRS 3.10.4)
AXIS_MAPPING = {
    "quà": "Quà tặng",
    "cốc": "Gia dụng & Đồ gốm",
    "ly": "Gia dụng & Đồ gốm",
    "áo": "Thời trang & May mặc",
    "túi": "Túi & Phụ kiện",
    "móc khóa": "Túi & Phụ kiện",
    "tranh": "Trang trí nhà cửa",
    "poster": "Trang trí nhà cửa",
    "sổ": "Văn phòng phẩm",
    "lì xì": "Lễ hội & Tết",
}


def _phan_vi(val: float, danh_sach: List[float]) -> float:
    if not danh_sach:
        return 50.0
    less_count = sum(1 for x in danh_sach if x <= val)
    return round((less_count / len(danh_sach)) * 100, 1)


@router.get("/api/analytics/forecast/radar", tags=["F40 · Tag đang tăng nhanh"])
def radar(shop_id: str = CurrentShop):
    all_series = weekly_series()
    if not all_series:
        # Fallback vào mart nếu chưa đọc được chuỗi
        rows = list(db()[MART].find({}, {"_id": 0}).sort("growth_pct", -1))
        if not rows:
            mart_not_ready(MART)
        meta = meta_from_record(rows[0], scope="platform", scope_id="all", collection=MART, mode="live")
        return ok({"top_tags": rows[:TOP_N], "radar": {"axes": [], "values": []}}, meta)

    # 1. Tính toán WoW và gia tốc 3 tuần (3-week acceleration) cho từng từ khóa duy nhất
    raw_metrics = []
    scores_for_percentile = []

    for kw, series in all_series.items():
        vals = [float(v) for v in series.values]
        if len(vals) < MIN_POINTS:
            continue
        
        y_t = vals[-1]
        y_prev1 = vals[-2]
        y_prev2 = vals[-3]
        y_prev3 = vals[-4]

        # WoW growth: (y_t - y_prev1) / y_prev1
        wow_growth_pct = round(((y_t - y_prev1) / y_prev1 * 100) if y_prev1 > 0 else 0.0, 1)
        
        # Log ratio chống nổ % trên nền nhỏ
        g_t = math.log(y_t + 1.0) - math.log(y_prev1 + 1.0)
        g_t_minus_2 = math.log(y_prev2 + 1.0) - math.log(y_prev3 + 1.0)
        acceleration = g_t - g_t_minus_2

        combined_momentum_raw = g_t + acceleration
        scores_for_percentile.append(combined_momentum_raw)

        # Xác định trục danh mục
        axis_name = "Khác"
        kw_low = kw.lower()
        for prefix, axis in AXIS_MAPPING.items():
            if prefix in kw_low:
                axis_name = axis
                break

        raw_metrics.append({
            "keyword": kw,
            "demand_index": round(y_t, 1),
            "wow_growth_pct": wow_growth_pct,
            "acceleration": round(acceleration, 2),
            "raw_score": combined_momentum_raw,
            "axis": axis_name,
            "low_base": y_t < NEN_TOI_THIEU,
            "trend": "rising" if wow_growth_pct > 10 else "falling" if wow_growth_pct < -10 else "flat",
            "sparkline_7w": [round(v, 1) for v in vals[-7:]]
        })

    # 2. Quy đổi momentum raw về phân vị chuẩn 0–100
    for item in raw_metrics:
        item["momentum"] = _phan_vi(item["raw_score"], scores_for_percentile)

    # 3. Gom nhóm theo trục ngành lớn (5–8 trục)
    theo_truc: Dict[str, List[float]] = defaultdict(list)
    for item in raw_metrics:
        theo_truc[item["axis"]].append(item["momentum"])

    # Chọn các trục có ít nhất 2 tín hiệu
    valid_axes = [ax for ax, scores in theo_truc.items() if len(scores) >= 2 and ax != "Khác"]
    valid_axes.sort(key=lambda ax: -sum(theo_truc[ax]) / len(theo_truc[ax]))
    
    axis_values = [round(sum(theo_truc[ax]) / len(theo_truc[ax]), 1) for ax in valid_axes]

    # 4. Sắp xếp top 10 tín hiệu tăng nhanh nhất (loại bỏ trùng lặp concept)
    raw_metrics.sort(key=lambda m: (-m["momentum"], -m["wow_growth_pct"]))
    top_tags = []
    seen_axes_count: Dict[str, int] = defaultdict(int)

    for i, m in enumerate(raw_metrics, 1):
        top_tags.append({
            "rank": len(top_tags) + 1,
            "tag_id": m["keyword"].replace(" ", "-"),
            "name_vi": m["keyword"].title(),
            "growth_pct": m["wow_growth_pct"],
            "momentum": m["momentum"] / 100.0,  # Thang 0–1 cho Recharts
            "momentum_pct": m["momentum"],       # Thang 0–100
            "demand_index": m["demand_index"],
            "acceleration": m["acceleration"],
            "low_base": m["low_base"],
            "axis": m["axis"],
            "trend": m["trend"],
            "sparkline": m["sparkline_7w"],
            "searches_per_week": None,  # Không bịa số lượt tìm theo BR-213
        })
        if len(top_tags) >= TOP_N:
            break

    meta = build_meta(
        scope="platform",
        scope_id="all",
        collection=MART,
        mode="derived",
        sample_size=len(raw_metrics),
        confidence="medium"
    )

    return ok({
        "week": "Tuần gần nhất (Google Trends VN)",
        "top_tags": top_tags,
        "radar": {
            "axes": valid_axes,
            "values": axis_values,
            "scale": "Momentum Score 0–100 (tính theo gia tốc 3 tuần)"
        },
        "limitation": (
            "Momentum Score phản ánh tốc độ gia tốc nhu cầu 3 tuần gần nhất (WoW + Acceleration). "
            "Các từ khóa có nhãn 'Nền thấp' có thể dao động mạnh do mẫu số nhỏ."
        )
    }, meta)
