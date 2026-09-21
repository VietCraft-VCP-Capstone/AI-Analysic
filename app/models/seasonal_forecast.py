"""
seasonal_forecast.py — Dự báo mùa vụ có nhận biết Tết âm lịch.

Bài toán
--------
Tết trượt tới gần 4 tuần trên lịch dương: 2021 rơi 12/02, 2023 rơi 22/01,
2026 rơi 17/02. Mô hình mùa vụ chu kỳ 52 tuần cố định giả định đỉnh rơi đúng
tuần đó mỗi năm, nên nó BÔI đỉnh Tết thành một gò thấp và rộng, làm mất hoàn
toàn độ cao thật.

Cách làm
--------
Bóc hiệu ứng Tết theo TRỤC ÂM LỊCH trước, rồi mới phân rã phần còn lại bằng
STL trên trục dương lịch:

  1. mức nền    = trung vị trượt 52 tuần (bỏ xu hướng, giữ mùa vụ)
  2. phần lệch  = giá trị − mức nền
  3. hiệu ứng Tết = trung vị phần lệch, gom theo bucket 7 ngày của days_to_tet
                    trong cửa sổ [−70, +35] ngày quanh mùng 1
  4. chuỗi đã bóc Tết = giá trị − hiệu ứng Tết
  5. STL(chuỗi đã bóc Tết, period=52) -> xu hướng + mùa vụ dương lịch
  6. dự báo = ngoại suy xu hướng + mùa vụ theo pha + hiệu ứng Tết theo
              days_to_tet của NGÀY TƯƠNG LAI

Bước 6 là điểm mấu chốt: ngày tương lai được tra hiệu ứng Tết theo khoảng cách
âm lịch của chính nó, nên đỉnh được đặt đúng chỗ dù Tết năm đó rơi vào tuần nào.

Đây chính là kỹ thuật "biến hồi quy sự kiện có cửa sổ trước/sau" mà
X-13ARIMA-SEATS dùng cho lễ di động, chỉ là cài đặt trực tiếp thay vì qua
regARIMA. Tham chiếu: Lin & Liu (2003) về điều chỉnh Tết Trung Hoa.

GIỚI HẠN: chỉ quan sát được 5 mùa Tết, nên mỗi bucket 7 ngày chỉ có ~5 quan sát.
Hiệu ứng Tết ước lượng được là thô. Số mẫu mỗi bucket được trả ra trong kết quả.
"""

import numpy as np
import pandas as pd
from typing import Any, Dict, List, Sequence, Tuple

try:
    from app.services.stl_service import STLService
    from app.core.calendar_vn import days_to_tet
except ImportError:
    import os
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    from app.services.stl_service import STLService
    from app.core.calendar_vn import days_to_tet

TET_WINDOW = (-70, 35)
BUCKET_DAYS = 7
DEFAULT_PERIOD = 52
TREND_FIT_POINTS = 52      # số điểm cuối dùng để ngoại suy xu hướng


# --------------------------------------------------------------------------- #
# mốc so sánh
# --------------------------------------------------------------------------- #

def seasonal_naive(train: Sequence[float], horizon: int, period: int = DEFAULT_PERIOD) -> List[float]:
    """Mốc so sánh: lấy giá trị cùng kỳ mùa trước. Mọi mô hình phải thắng được cái này."""
    t = np.asarray(train, dtype=float)
    if t.size < period:
        # Không đủ một mùa: lùi về naive thường.
        return [float(t[-1])] * horizon
    return [float(t[-period + (i % period)]) for i in range(horizon)]


# --------------------------------------------------------------------------- #
# hiệu ứng Tết
# --------------------------------------------------------------------------- #

def _bucket_of(day_offset: int) -> int:
    lo, hi = TET_WINDOW
    if not (lo <= day_offset <= hi):
        return 99
    return int(np.floor(day_offset / BUCKET_DAYS))


def estimate_tet_effect(dates: Sequence[Any], values: Sequence[float],
                        period: int = DEFAULT_PERIOD) -> Dict[int, Dict[str, float]]:
    """
    Ước lượng độ nâng của Tết theo khoảng cách âm lịch.

    Trả về {bucket: {"effect": float, "n": int}}. Trung vị được dùng thay trung
    bình vì chỉ có ~5 quan sát mỗi bucket, một năm bất thường sẽ kéo lệch hết.
    """
    v = np.asarray(values, dtype=float)
    n = v.size
    if n < period:
        return {}

    level = pd.Series(v).rolling(period, center=True, min_periods=max(3, period // 3)).median().to_numpy()
    level = np.where(np.isnan(level), float(np.nanmedian(level)), level)
    deviation = v - level

    buckets: Dict[int, List[float]] = {}
    for i in range(n):
        try:
            b = _bucket_of(days_to_tet(dates[i]))
        except (ValueError, TypeError):
            continue
        if b == 99:
            continue
        buckets.setdefault(b, []).append(float(deviation[i]))

    return {b: {"effect": float(np.median(vals)), "n": len(vals)} for b, vals in buckets.items()}


def _tet_value(effect: Dict[int, Dict[str, float]], date: Any) -> float:
    try:
        b = _bucket_of(days_to_tet(date))
    except (ValueError, TypeError):
        return 0.0
    entry = effect.get(b)
    return entry["effect"] if entry else 0.0


# --------------------------------------------------------------------------- #
# mô hình
# --------------------------------------------------------------------------- #

def tet_aware_forecast(dates: Sequence[Any], values: Sequence[float],
                       future_dates: Sequence[Any],
                       period: int = DEFAULT_PERIOD,
                       clip_min: float = 0.0) -> Dict[str, Any]:
    """
    Dự báo có nhận biết Tết. Trả về dự báo kèm các thành phần đã tách, để kết
    quả giải thích được chứ không phải hộp đen.
    """
    v = np.asarray(values, dtype=float)
    n = v.size
    horizon = len(future_dates)
    if horizon == 0:
        raise ValueError("future_dates rỗng")
    if n < period * 2:
        # Chưa đủ hai mùa để phân rã: trả mốc so sánh và nói rõ.
        return {
            "predictions": seasonal_naive(v, horizon, period),
            "method": "seasonal_naive_fallback",
            "tet_buckets": 0,
            "note": f"Chỉ có {n} điểm, cần ít nhất {period * 2} để bóc mùa vụ.",
        }

    effect = estimate_tet_effect(dates, v, period)
    tet_hist = np.array([_tet_value(effect, d) for d in dates], dtype=float)
    adjusted = v - tet_hist

    parts = STLService.decompose(list(adjusted), period=period, robust=True)
    trend = np.asarray(parts["trend"], dtype=float)
    seasonal = np.asarray(parts["seasonal"], dtype=float)

    # Ngoại suy xu hướng bằng hồi quy tuyến tính trên đoạn cuối. Dùng đoạn cuối
    # thay vì toàn chuỗi để bám theo mức hiện tại, không bị kéo bởi quá khứ xa.
    k = min(TREND_FIT_POINTS, n)
    xs = np.arange(k, dtype=float)
    slope, intercept = np.polyfit(xs, trend[-k:], 1)

    # Mùa vụ dương lịch theo pha: lấy trung vị các năm ở cùng pha.
    phase_median = {}
    for phase in range(period):
        same = seasonal[phase::period] if phase < n else np.array([])
        idx = [i for i in range(n) if i % period == phase]
        if idx:
            phase_median[phase] = float(np.median(seasonal[idx]))

    predictions, components = [], []
    for h, fd in enumerate(future_dates, start=1):
        trend_hat = float(intercept + slope * (k - 1 + h))
        phase = (n + h - 1) % period
        seasonal_hat = phase_median.get(phase, 0.0)
        tet_hat = _tet_value(effect, fd)
        yhat = max(clip_min, trend_hat + seasonal_hat + tet_hat)
        predictions.append(yhat)
        components.append({
            "date": str(fd), "trend": round(trend_hat, 2),
            "seasonal": round(seasonal_hat, 2), "tet": round(tet_hat, 2),
            "yhat": round(yhat, 2),
        })

    return {
        "predictions": predictions,
        "components": components,
        "method": "tet_aware_stl",
        "tet_buckets": len(effect),
        "tet_bucket_sample_sizes": {str(b): e["n"] for b, e in sorted(effect.items())},
        "trend_slope_per_week": round(float(slope), 4),
    }


def stl_no_tet_forecast(dates: Sequence[Any], values: Sequence[float],
                        future_dates: Sequence[Any],
                        period: int = DEFAULT_PERIOD,
                        clip_min: float = 0.0) -> Dict[str, Any]:
    """Cùng mô hình nhưng KHÔNG bóc Tết — dùng để đo riêng đóng góp của trục âm lịch."""
    v = np.asarray(values, dtype=float)
    n = v.size
    horizon = len(future_dates)
    if n < period * 2:
        return {"predictions": seasonal_naive(v, horizon, period), "method": "seasonal_naive_fallback"}

    parts = STLService.decompose(list(v), period=period, robust=True)
    trend = np.asarray(parts["trend"], dtype=float)
    seasonal = np.asarray(parts["seasonal"], dtype=float)

    k = min(TREND_FIT_POINTS, n)
    slope, intercept = np.polyfit(np.arange(k, dtype=float), trend[-k:], 1)
    phase_median = {}
    for phase in range(period):
        idx = [i for i in range(n) if i % period == phase]
        if idx:
            phase_median[phase] = float(np.median(seasonal[idx]))

    preds = []
    for h in range(1, horizon + 1):
        trend_hat = float(intercept + slope * (k - 1 + h))
        preds.append(max(clip_min, trend_hat + phase_median.get((n + h - 1) % period, 0.0)))
    return {"predictions": preds, "method": "stl_no_tet"}


if __name__ == "__main__":
    print("=== TỰ KIỂM TRA MODULE SEASONAL_FORECAST.PY ===")

    weeks = pd.date_range("2021-08-15", periods=262, freq="W-SUN")
    dates = [d.strftime("%Y-%m-%d") for d in weeks]

    # 1. seasonal_naive lặp đúng chu kỳ.
    tr = list(np.arange(104, dtype=float))
    sn = seasonal_naive(tr, 5, period=52)
    assert sn == [52.0, 53.0, 54.0, 55.0, 56.0], sn
    print(f"✓ seasonal_naive lấy đúng cùng kỳ mùa trước: {sn}")

    # 2. Chuỗi ngắn: lùi về naive và khai báo rõ.
    short = tet_aware_forecast(dates[:60], [1.0] * 60, dates[60:64])
    assert short["method"] == "seasonal_naive_fallback" and "cần ít nhất" in short["note"]
    print(f"✓ Chuỗi ngắn: {short['method']}, có ghi lý do")

    # 3. Ước lượng hiệu ứng Tết trên chuỗi tổng hợp có đỉnh ĐÚNG NGÀY ÂM LỊCH.
    rng = np.random.default_rng(3)
    vals = []
    for d in weeks:
        dt = days_to_tet(d)
        bump = 300 * np.exp(-0.5 * (((dt + 14) / 12.0) ** 2))   # đỉnh ở T−14 ngày
        vals.append(30 + bump + rng.normal(0, 4))
    effect = estimate_tet_effect(dates, vals)
    assert len(effect) >= 10, f"Phải ước lượng được nhiều bucket, chỉ có {len(effect)}"
    peak_bucket = max(effect, key=lambda b: effect[b]["effect"])
    assert -4 <= peak_bucket <= -1, f"Đỉnh phải ở bucket âm (trước Tết), nhận {peak_bucket}"
    print(f"✓ Hiệu ứng Tết: {len(effect)} bucket, đỉnh ở bucket {peak_bucket} "
          f"(≈ {peak_bucket * 7} tới {(peak_bucket + 1) * 7} ngày so với mùng 1), "
          f"độ nâng {effect[peak_bucket]['effect']:.0f}")

    # 4. Mô hình bóc Tết phải THẮNG seasonal_naive trên chuỗi có Tết di động.
    import sys as _sys
    _sys.path.insert(0, ".")
    from app.core.metrics import mase

    cut = 210
    tr_d, tr_v = dates[:cut], vals[:cut]
    te_d, te_v = dates[cut:cut + 12], vals[cut:cut + 12]
    tet_pred = tet_aware_forecast(tr_d, tr_v, te_d)["predictions"]
    no_tet_pred = stl_no_tet_forecast(tr_d, tr_v, te_d)["predictions"]
    naive_pred = seasonal_naive(tr_v, 12)

    m_tet = mase(te_v, tet_pred, tr_v, period=52)
    m_no = mase(te_v, no_tet_pred, tr_v, period=52)
    m_naive = mase(te_v, naive_pred, tr_v, period=52)
    print(f"✓ MASE  bóc Tết {m_tet:.3f}  |  STL thường {m_no:.3f}  |  seasonal_naive {m_naive:.3f}")
    assert m_tet < m_naive, "Mô hình bóc Tết phải thắng seasonal_naive"

    # 5. Dự báo không âm và đúng độ dài.
    out = tet_aware_forecast(dates[:250], vals[:250], dates[250:262])
    assert len(out["predictions"]) == 12
    assert all(p >= 0 for p in out["predictions"])
    assert len(out["components"]) == 12 and "tet" in out["components"][0]
    print(f"✓ Dự báo 12 tuần: đủ độ dài, không âm, có tách thành phần trend/seasonal/tet")

    # 6. Số mẫu mỗi bucket được khai báo — người đọc biết ước lượng thô cỡ nào.
    assert out["tet_bucket_sample_sizes"], "Phải khai báo số mẫu mỗi bucket"
    sizes = list(out["tet_bucket_sample_sizes"].values())
    print(f"✓ Số mẫu mỗi bucket Tết: {min(sizes)}–{max(sizes)} quan sát (chỉ 5 mùa Tết)")

    # 7. Từ chối horizon rỗng.
    try:
        tet_aware_forecast(dates, vals, [])
        raise AssertionError("Phải từ chối future_dates rỗng")
    except ValueError:
        pass
    print("✓ Từ chối future_dates rỗng")

    print("\n✅ TẤT CẢ SELF-CHECKS CỦA SEASONAL_FORECAST.PY ĐÃ PASS!")
