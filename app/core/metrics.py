"""
metrics.py — Chỉ số đo sai số dự báo.

Vì sao KHÔNG dùng MAPE
----------------------
`baselines.json` hiện tại dùng MAPE. MAPE hỏng theo ba cách:

  1. Chia cho 0. MAPE = mean(|e| / y). Chuỗi nhu cầu có rất nhiều y = 0.
  2. Bất đối xứng. Phạt dự báo thừa nặng hơn dự báo thiếu, nên mô hình tối ưu
     theo MAPE sẽ tự học cách dự báo thấp đi một cách có hệ thống.
  3. Không so sánh được giữa các chuỗi. Trong chính baselines.json của dự án:
       "áo thun"     MAPE 12,7%  nhưng MAE 15,45
       "áo phông nữ" MAPE 27,8%  nhưng MAE  1,17
     Chuỗi thứ hai dễ dự báo hơn nhiều; MAPE lớn chỉ vì mẫu số nhỏ.

Dùng MASE thay thế
------------------
                 mean(|y_t - ŷ_t|)                     trên tập kiểm tra
    MASE  =  ──────────────────────────────
             (1/(n-m)) · Σ |y_t - y_(t-m)|             trên tập huấn luyện

Mẫu số là MAE của dự báo NGÂY THƠ MÙA VỤ tính trên tập HUẤN LUYỆN, với m là chu
kỳ mùa. Đọc kết quả: MASE < 1 nghĩa là tốt hơn naive; MASE = 0,62 nghĩa là sai
số chỉ bằng 62% của naive, tức tốt hơn 38%.

MASE chạy được với số 0, đối xứng, và so sánh được giữa mọi chuỗi.
RMSSE là biến thể bình phương, chính là chỉ số của cuộc thi M5.

Tham chiếu: Hyndman & Koehler (2006), "Another look at measures of forecast accuracy".
"""

import numpy as np
from typing import Dict, Sequence, Union

Number = Union[float, int]


def _clean(name: str, values: Sequence[Number]) -> np.ndarray:
    arr = np.asarray(values, dtype=float)
    if arr.size == 0:
        raise ValueError(f"{name} rỗng")
    if not np.all(np.isfinite(arr)):
        raise ValueError(f"{name} chứa NaN hoặc vô cực")
    return arr


def mae(actual: Sequence[Number], predicted: Sequence[Number]) -> float:
    a, p = _clean("actual", actual), _clean("predicted", predicted)
    if a.size != p.size:
        raise ValueError("actual và predicted phải cùng độ dài")
    return float(np.mean(np.abs(a - p)))


def rmse(actual: Sequence[Number], predicted: Sequence[Number]) -> float:
    a, p = _clean("actual", actual), _clean("predicted", predicted)
    if a.size != p.size:
        raise ValueError("actual và predicted phải cùng độ dài")
    return float(np.sqrt(np.mean((a - p) ** 2)))


def naive_scale(train: Sequence[Number], period: int = 1) -> float:
    """
    Mẫu số của MASE: MAE của dự báo ngây thơ mùa vụ trên tập huấn luyện.

    period = 1 cho naive thường (lấy giá trị kỳ trước).
    period = m cho naive mùa vụ (lấy giá trị cùng kỳ mùa trước).
    """
    t = _clean("train", train)
    if period < 1:
        raise ValueError("period phải từ 1 trở lên")
    if t.size <= period:
        raise ValueError(f"Tập huấn luyện cần nhiều hơn {period} điểm để tính thang naive")
    return float(np.mean(np.abs(t[period:] - t[:-period])))


def mase(actual: Sequence[Number], predicted: Sequence[Number],
         train: Sequence[Number], period: int = 1) -> float:
    """MASE. Trả về vô cực khi chuỗi huấn luyện hằng số (thang naive = 0)."""
    scale = naive_scale(train, period)
    if scale == 0:
        return float("inf")
    return mae(actual, predicted) / scale


def rmsse(actual: Sequence[Number], predicted: Sequence[Number],
          train: Sequence[Number], period: int = 1) -> float:
    """RMSSE — chỉ số chính thức của cuộc thi M5."""
    t = _clean("train", train)
    if t.size <= period:
        raise ValueError(f"Tập huấn luyện cần nhiều hơn {period} điểm")
    denom = float(np.mean((t[period:] - t[:-period]) ** 2))
    if denom == 0:
        return float("inf")
    a, p = _clean("actual", actual), _clean("predicted", predicted)
    if a.size != p.size:
        raise ValueError("actual và predicted phải cùng độ dài")
    return float(np.sqrt(np.mean((a - p) ** 2) / denom))


def mape(actual: Sequence[Number], predicted: Sequence[Number]) -> Union[float, None]:
    """
    Giữ lại để đối chiếu với baselines.json cũ. KHÔNG dùng để chọn mô hình.
    Trả về None khi có giá trị thực bằng 0, thay vì trả về vô cực im lặng.
    """
    a, p = _clean("actual", actual), _clean("predicted", predicted)
    if np.any(a == 0):
        return None
    return float(np.mean(np.abs((a - p) / a)) * 100)


def evaluate(actual: Sequence[Number], predicted: Sequence[Number],
             train: Sequence[Number], period: int = 1) -> Dict[str, Union[float, None]]:
    """Bộ chỉ số đầy đủ cho một lần dự báo."""
    return {
        "mae": round(mae(actual, predicted), 4),
        "rmse": round(rmse(actual, predicted), 4),
        "mase": round(mase(actual, predicted, train, period), 4),
        "rmsse": round(rmsse(actual, predicted, train, period), 4),
        "mape": (lambda v: None if v is None else round(v, 4))(mape(actual, predicted)),
        "n_test": len(actual),
        "n_train": len(train),
        "seasonal_period": period,
    }


if __name__ == "__main__":
    print("=== TỰ KIỂM TRA MODULE METRICS.PY ===")

    # 1. Dự báo hoàn hảo cho sai số bằng 0.
    y = [10.0, 12.0, 11.0, 15.0]
    assert mae(y, y) == 0.0 and rmse(y, y) == 0.0
    print("✓ Dự báo hoàn hảo: MAE = RMSE = 0")

    # 2. PHÉP THỬ KHUNG ĐO — quan trọng nhất.
    #    Chạy chính seasonal_naive qua khung đo thì MASE phải ra ≈ 1,0.
    #    Không ra 1,0 nghĩa là khung đo sai, không phải mô hình sai.
    rng = np.random.default_rng(7)
    m = 52
    n = 260
    t = np.arange(n + 12)
    series = 100 + 20 * np.sin(2 * np.pi * t / m) + rng.normal(0, 5, n + 12)
    train, test = series[:n], series[n:]
    naive_pred = series[n - m:n - m + len(test)]      # cùng kỳ mùa trước
    score = mase(test, naive_pred, train, period=m)
    assert 0.75 < score < 1.35, f"Khung đo hỏng: seasonal_naive ra MASE {score:.3f}"
    print(f"✓ PHÉP THỬ KHUNG ĐO: seasonal_naive qua chính khung này ra MASE {score:.3f} (≈ 1,0)")

    # 3. Mô hình tốt hơn naive phải cho MASE < 1.
    better = test + rng.normal(0, 1.0, len(test))
    assert mase(test, better, train, period=m) < score
    print(f"✓ Mô hình tốt hơn: MASE {mase(test, better, train, period=m):.3f} < {score:.3f}")

    # 4. MASE chạy được với chuỗi có nhiều số 0 (chỗ MAPE chết).
    sparse_train = [0.0, 0.0, 3.0, 0.0, 0.0, 1.0, 0.0, 0.0, 2.0, 0.0]
    sparse_test = [0.0, 2.0, 0.0]
    pred = [0.5, 1.0, 0.5]
    v = mase(sparse_test, pred, sparse_train, period=1)
    assert np.isfinite(v), "MASE phải chạy được với chuỗi thưa"
    assert mape(sparse_test, pred) is None, "MAPE phải trả None khi có y = 0"
    print(f"✓ Chuỗi thưa nhiều số 0: MASE = {v:.3f}, MAPE = None (không im lặng trả vô cực)")

    # 5. Chuỗi huấn luyện hằng số: thang naive = 0, trả vô cực chứ không chia cho 0.
    assert mase([1.0, 2.0], [1.0, 2.0], [5.0] * 10, period=1) == float("inf")
    print("✓ Chuỗi huấn luyện hằng số: trả vô cực, không ném ZeroDivisionError")

    # 6. RMSSE phạt sai số lớn nặng hơn MASE.
    a = [10.0, 10.0, 10.0, 10.0]
    spread = [10.0, 10.0, 10.0, 22.0]     # một sai số lớn
    even = [13.0, 13.0, 13.0, 13.0]       # bốn sai số nhỏ, cùng tổng tuyệt đối
    tr = list(np.arange(20, dtype=float))
    assert mae(a, spread) == mae(a, even)
    assert rmsse(a, spread, tr) > rmsse(a, even, tr)
    print("✓ RMSSE phạt một sai số lớn nặng hơn nhiều sai số nhỏ cùng tổng")

    # 7. Từ chối đầu vào bẩn.
    for bad, label in (([float("nan"), 1.0], "NaN"), ([float("inf"), 1.0], "vô cực"), ([], "rỗng")):
        try:
            mae(bad, [1.0, 2.0][:len(bad)] or [1.0])
            raise AssertionError(f"Phải từ chối {label}")
        except ValueError:
            pass
    try:
        mae([1.0, 2.0], [1.0])
        raise AssertionError("Phải từ chối lệch độ dài")
    except ValueError:
        pass
    try:
        naive_scale([1.0, 2.0], period=52)
        raise AssertionError("Phải từ chối tập huấn luyện ngắn hơn chu kỳ")
    except ValueError:
        pass
    print("✓ Từ chối NaN, vô cực, chuỗi rỗng, lệch độ dài, train ngắn hơn chu kỳ")

    # 8. evaluate trả đủ bộ chỉ số.
    ev = evaluate(test, naive_pred, train, period=m)
    assert set(ev) >= {"mae", "rmse", "mase", "rmsse", "mape", "n_test", "n_train"}
    print(f"✓ evaluate(): {ev}")

    print("\n✅ TẤT CẢ SELF-CHECKS CỦA METRICS.PY ĐÃ PASS!")
