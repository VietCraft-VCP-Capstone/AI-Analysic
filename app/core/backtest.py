"""
backtest.py — Đánh giá dự báo bằng phương pháp TRƯỢT ĐIỂM CẮT (rolling origin).

Vì sao một lát cắt là chưa đủ
-----------------------------
`baselines.json` hiện dùng MỘT điểm cắt duy nhất (2026-05-24). Điều đó cho ta
MỘT mẫu về năng lực mô hình. Nếu 12 tuần đó tình cờ dễ hoặc khó, con số sẽ đánh
lừa và không ai biết.

Rolling origin trượt điểm cắt qua nhiều vị trí, mỗi lần huấn luyện lại và dự
báo, rồi báo cáo trung bình KÈM ĐỘ LỆCH CHUẨN:

    origin 1: train [.. 2025-09]  test [2025-10 .. 2025-12]
    origin 2: train [.. 2025-12]  test [2026-01 .. 2026-03]
    origin 3: train [.. 2026-03]  test [2026-04 .. 2026-06]

Dùng cửa sổ MỞ RỘNG (tập train lớn dần) vì dữ liệu chỉ có 262 điểm — cắt bớt
quá khứ sẽ mất luôn số mùa vụ ít ỏi.

Chi tiết dễ bỏ sót: với dữ liệu mùa vụ năm, các điểm cắt PHẢI rơi vào những pha
mùa vụ khác nhau. Nếu cả 8 origin đều cắt vào tháng 5 thì không bao giờ đo được
mô hình xử lý Tết ra sao. Tham số `step` điều khiển việc này.

Tham chiếu: Tashman (2000), "Out-of-sample tests of forecasting accuracy".
"""

import numpy as np
from typing import Any, Callable, Dict, List, Sequence

try:
    from app.core.metrics import evaluate
except ImportError:
    import os
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    from app.core.metrics import evaluate


def rolling_origin(
    dates: Sequence[Any],
    values: Sequence[float],
    forecaster: Callable[[Sequence[Any], Sequence[float], Sequence[Any]], Sequence[float]],
    horizon: int = 12,
    n_origins: int = 8,
    step: int = 6,
    period: int = 52,
    min_train: int = 104,
) -> Dict[str, Any]:
    """
    Chạy đánh giá trượt điểm cắt.

    `forecaster(train_dates, train_values, future_dates) -> predictions`.
    `step` là khoảng cách giữa các điểm cắt, tính bằng số điểm dữ liệu; đặt nhỏ
    hơn chu kỳ mùa để các origin phủ nhiều pha khác nhau.
    """
    v = np.asarray(values, dtype=float)
    n = v.size
    if len(dates) != n:
        raise ValueError("dates và values phải cùng độ dài")
    if horizon < 1 or n_origins < 1 or step < 1:
        raise ValueError("horizon, n_origins và step phải từ 1 trở lên")

    # Điểm cắt cuối cùng phải chừa đủ `horizon` điểm để kiểm tra.
    last_cut = n - horizon
    cuts = [last_cut - i * step for i in range(n_origins)][::-1]
    cuts = [c for c in cuts if c >= max(min_train, period + 1)]
    if not cuts:
        return {
            "status": "insufficient_data",
            "reason": (f"Chuỗi {n} điểm không đủ cho {n_origins} điểm cắt, "
                       f"horizon {horizon}, tối thiểu {min_train} điểm huấn luyện."),
            "origins": [], "n_origins": 0,
        }

    origins = []
    for cut in cuts:
        train_v, train_d = v[:cut], list(dates[:cut])
        test_v, test_d = v[cut:cut + horizon], list(dates[cut:cut + horizon])
        try:
            pred = list(forecaster(train_d, train_v, test_d))
        except Exception as e:
            origins.append({"cut_index": int(cut), "cut_date": str(dates[cut]),
                            "status": "failed", "error": str(e)})
            continue
        if len(pred) != len(test_v):
            origins.append({"cut_index": int(cut), "cut_date": str(dates[cut]),
                            "status": "failed", "error": "độ dài dự báo không khớp"})
            continue
        m = evaluate(test_v, pred, train_v, period=period)
        origins.append({"cut_index": int(cut), "cut_date": str(dates[cut]),
                        "status": "ok", **m})

    ok = [o for o in origins if o["status"] == "ok" and np.isfinite(o["mase"])]
    if not ok:
        return {"status": "no_valid_origin", "origins": origins, "n_origins": 0}

    def agg(key):
        vals = [o[key] for o in ok if o.get(key) is not None and np.isfinite(o[key])]
        if not vals:
            return None
        return {"mean": round(float(np.mean(vals)), 4),
                "std": round(float(np.std(vals)), 4),
                "min": round(float(np.min(vals)), 4),
                "max": round(float(np.max(vals)), 4)}

    return {
        "status": "ok",
        "n_origins": len(ok),
        "horizon": horizon,
        "step": step,
        "seasonal_period": period,
        "window": "expanding",
        "mase": agg("mase"),
        "rmsse": agg("rmsse"),
        "mae": agg("mae"),
        "origins": origins,
    }


if __name__ == "__main__":
    print("=== TỰ KIỂM TRA MODULE BACKTEST.PY ===")

    import pandas as pd
    try:
        from app.models.seasonal_forecast import seasonal_naive
    except ImportError:
        import sys
        sys.path.insert(0, ".")
        from app.models.seasonal_forecast import seasonal_naive

    weeks = pd.date_range("2021-08-15", periods=262, freq="W-SUN")
    dates = [d.strftime("%Y-%m-%d") for d in weeks]
    rng = np.random.default_rng(11)
    t = np.arange(262)
    vals = (100 + 25 * np.sin(2 * np.pi * t / 52) + rng.normal(0, 6, 262)).tolist()

    # 1. PHÉP THỬ KHUNG ĐO: seasonal_naive qua chính khung này phải ra MASE ≈ 1,0.
    r = rolling_origin(dates, vals,
                       lambda td, tv, fd: seasonal_naive(tv, len(fd), 52),
                       horizon=12, n_origins=8, step=6)
    assert r["status"] == "ok", r
    assert 0.7 < r["mase"]["mean"] < 1.4, f"Khung đo hỏng: MASE {r['mase']['mean']}"
    print(f"✓ PHÉP THỬ KHUNG ĐO: seasonal_naive ra MASE {r['mase']['mean']} "
          f"± {r['mase']['std']} trên {r['n_origins']} điểm cắt")

    # 2. Các điểm cắt phải rơi vào nhiều tháng khác nhau, không dồn một chỗ.
    months = {o["cut_date"][5:7] for o in r["origins"] if o["status"] == "ok"}
    assert len(months) >= 3, f"Điểm cắt dồn cục: chỉ {len(months)} tháng khác nhau"
    print(f"✓ {r['n_origins']} điểm cắt phủ {len(months)} tháng khác nhau: {sorted(months)}")

    # 3. Mô hình hoàn hảo (biết trước tương lai) phải cho MASE ≈ 0.
    idx = {d: i for i, d in enumerate(dates)}
    r2 = rolling_origin(dates, vals,
                        lambda td, tv, fd: [vals[idx[d]] for d in fd],
                        horizon=12, n_origins=6, step=6)
    assert r2["mase"]["mean"] < 0.01, r2["mase"]
    print(f"✓ Mô hình hoàn hảo: MASE {r2['mase']['mean']} ≈ 0")

    # 4. Chuỗi quá ngắn: khai báo rõ, không ném lỗi.
    short = rolling_origin(dates[:60], vals[:60],
                           lambda td, tv, fd: seasonal_naive(tv, len(fd), 52),
                           horizon=12, n_origins=8, step=6)
    assert short["status"] == "insufficient_data" and "không đủ" in short["reason"]
    print(f"✓ Chuỗi ngắn: {short['status']}")

    # 5. Mô hình ném lỗi ở một origin không làm sập cả lượt chạy.
    calls = {"n": 0}
    def flaky(td, tv, fd):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("lỗi cố ý")
        return seasonal_naive(tv, len(fd), 52)
    r3 = rolling_origin(dates, vals, flaky, horizon=12, n_origins=5, step=6)
    assert r3["status"] == "ok" and r3["n_origins"] == 4
    assert any(o["status"] == "failed" for o in r3["origins"])
    print(f"✓ Một origin lỗi: vẫn chạy tiếp, {r3['n_origins']}/5 origin hợp lệ, lỗi được ghi lại")

    # 6. Báo cáo kèm độ lệch chuẩn, không chỉ một con số trung bình.
    assert {"mean", "std", "min", "max"} <= set(r["mase"])
    print(f"✓ Báo cáo đầy đủ: MASE mean {r['mase']['mean']}, std {r['mase']['std']}, "
          f"min {r['mase']['min']}, max {r['mase']['max']}")

    # 7. Từ chối tham số sai.
    for kw in ({"horizon": 0}, {"n_origins": 0}, {"step": 0}):
        try:
            rolling_origin(dates, vals, lambda td, tv, fd: [0.0] * len(fd), **kw)
            raise AssertionError(f"Phải từ chối {kw}")
        except ValueError:
            pass
    try:
        rolling_origin(dates[:10], vals, lambda td, tv, fd: [0.0] * len(fd))
        raise AssertionError("Phải từ chối dates/values lệch độ dài")
    except ValueError:
        pass
    print("✓ Từ chối tham số sai và dữ liệu lệch độ dài")

    print("\n✅ TẤT CẢ SELF-CHECKS CỦA BACKTEST.PY ĐÃ PASS!")
