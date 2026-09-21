"""
zscore_service.py — Phát hiện bất thường trên PHẦN DƯ STL bằng thống kê bền vững.

Vì sao không chấm điểm trên chuỗi thô
-------------------------------------
Chuỗi có mùa vụ mạnh (doanh thu ngày, lượt xem, chỉ số tìm kiếm) đạt đỉnh vào
Tết, 8/3, 20/10. Tính z-score toàn cục trên chuỗi thô thì TOÀN BỘ mùa cao điểm
bị gắn nhãn bất thường — đều đặn mỗi năm một lần. Đỉnh mùa vụ lặp lại KHÔNG
phải bất thường; bất thường là cái còn sót lại sau khi bóc xu hướng và mùa vụ:

    STL(chuỗi) -> trend + seasonal + residual  ->  chấm điểm trên residual

Vì sao không dùng mean và std
-----------------------------
Trung bình và độ lệch chuẩn BỊ CHÍNH CÁC ĐIỂM NGOẠI LAI LÀM NHIỄM: điểm gãy 0%,
một điểm xấu là hỏng ước lượng. Trung vị và MAD có điểm gãy 50%.

    z_mod = (x - median) / scale          Iglewicz & Hoaglin (1993)

Ba quyết định thiết kế đều dựa trên ĐO ĐẠC, không lấy hằng số sách giáo khoa
-----------------------------------------------------------------------------
1. THANG ĐO LẤY TỪ SAI PHÂN LIÊN TIẾP, không lấy MAD thường.
   STL hấp thụ bớt nhiễu vào trend/seasonal nên MAD của phần dư ước lượng
   THẤP hơn nhiễu thật. Đo trên 6 lần chạy mô phỏng với nhiễu thật std = 3,0:

       MAD thường     -> 1,56   (thấp hơn 1,9 lần)
       MAD sai phân   -> 1,78   (thấp hơn 1,7 lần)

   Sai phân liên tiếp ít bị ảnh hưởng bởi việc làm trơn hơn, nên dùng nó.

2. NGƯỠNG MẶC ĐỊNH LÀ 7.0, KHÔNG PHẢI 3.5.
   Vì thang đo vẫn bị co, ngưỡng 3,5 của sách giáo khoa (vốn hiệu chuẩn cho
   phân phối chuẩn) gắn cờ quá nhiều. Đo trên 20 chuỗi sạch, 260 điểm:

       ngưỡng 3,5  -> báo động giả 7,38%  (tệ nhất 11,54%)
       ngưỡng 5,0  -> báo động giả 2,77%  (tệ nhất  5,38%)
       ngưỡng 6,0  -> báo động giả 1,15%  (tệ nhất  3,46%)
       ngưỡng 7,0  -> báo động giả 0,60%  (tệ nhất  1,92%)

   Ngưỡng 7,0 vẫn bắt 20/20 đột biến cỡ +50% biên độ mùa vụ.

3. CẢNH BÁO KHI SỐ CHU KỲ QUÁ ÍT — giới hạn quan trọng nhất.
   Với period = 52 và 5 năm dữ liệu tuần, mỗi pha mùa vụ chỉ có 5 quan sát.
   Một điểm chiếm 20% dữ liệu của pha đó, nên LOESS KHÔNG phân biệt được
   "pha này năm nay cao thật" với "ngoại lai" — nó hút luôn đột biến vào
   thành phần mùa vụ. Đo được: chèn một đột biến gấp 3 lần nền vào chuỗi
   5 chu kỳ thì thành phần mùa vụ cùng pha qua các năm ra

       -15,5   -13,8   +92,2   -12,2   -16,7

   và phần dư chỉ còn 1,4 — đột biến TÀNG HÌNH. Hiện tượng này không đổi khi
   chỉnh seasonal_win (thử 7, 11, 53 đều như nhau): đây là vấn đề không định
   danh được, không phải tham số sai.

   Vì vậy khi số chu kỳ < MIN_CYCLES_FOR_SEASONAL, module HẠ CỜ TIN CẬY và
   nói rõ đột biến có thể bị che. Đầu vào đúng của tính năng này là chuỗi
   NGÀY của listing/shop với period = 7 (18 tháng cho ~78 chu kỳ), không phải
   chuỗi tuần chỉ số tìm kiếm với period = 52.

Giới hạn còn lại: Tết là lễ di động
-----------------------------------
Tết 2023 rơi 22/01 còn 2024 rơi 10/02, lệch tới 3 tuần. Mô hình chu kỳ dương
lịch cố định dự đoán đỉnh ở tuần mà năm đó chưa tới Tết, sinh phần dư ÂM rất
lớn quanh Tết. Khi truyền kèm `dates`, các điểm trong cửa sổ Tết được đánh dấu
`calendar_sensitive` để nơi tiêu thụ biết phần dư ở đó kém tin cậy.
"""

import numpy as np
from typing import Any, Dict, List, Sequence, Tuple, Union

try:
    from app.services.stl_service import STLService
    from app.core.calendar_vn import days_to_tet
except ImportError:  # chạy trực tiếp file này thay vì import từ gốc repo
    import os
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    from app.services.stl_service import STLService
    from app.core.calendar_vn import days_to_tet


# 0.6745 là phân vị 75% của phân phối chuẩn tắc; chia cho nó đưa MAD về cùng
# thang với độ lệch chuẩn. Sai phân của hai điểm độc lập có phương sai gấp đôi
# nên còn chia thêm căn 2.
MAD_TO_SIGMA = 0.6745
DIFF_VARIANCE_FACTOR = np.sqrt(2.0)
MEAN_AD_TO_SIGMA = 1.253314

DEFAULT_THRESHOLD = 7.0          # hiệu chuẩn bằng đo đạc, xem docstring mục 2
DEFAULT_PERIOD = 7               # chuỗi ngày, chu kỳ tuần — đầu vào đúng của F30
MAX_ANOMALY_RATE = 0.05          # vượt ngưỡng này nghĩa là giả định bị vi phạm
MIN_CYCLES_FOR_SEASONAL = 12     # dưới mức này, mùa vụ có thể nuốt mất đột biến
TET_WINDOW = (-70, 35)           # ngày quanh mùng 1 Tết mà chu kỳ cố định lệch pha


class ZScoreService:

    # ------------------------------------------------------------------ #
    @staticmethod
    def robust_scale(residual: np.ndarray) -> Tuple[float, str]:
        """
        Ước lượng thang đo bền vững của phần dư.

        Ưu tiên MAD của SAI PHÂN LIÊN TIẾP vì nó ít bị co lại do STL làm trơn.
        Hai mức dự phòng phía sau để không bao giờ chia cho 0, và mỗi mức đều
        được GỌI TÊN trong kết quả chứ không im lặng thay thế.
        """
        if residual.size >= 3:
            d = np.median(np.abs(np.diff(residual)))
            if d > 0:
                return float(d / MAD_TO_SIGMA / DIFF_VARIANCE_FACTOR), "mad_of_successive_differences"

        median = float(np.median(residual)) if residual.size else 0.0
        mad = float(np.median(np.abs(residual - median))) if residual.size else 0.0
        if mad > 0:
            return mad / MAD_TO_SIGMA, "mad"

        mean_ad = float(np.mean(np.abs(residual - median))) if residual.size else 0.0
        if mean_ad > 0:
            return mean_ad * MEAN_AD_TO_SIGMA, "mean_absolute_deviation"

        return 0.0, "degenerate_no_spread"

    # ------------------------------------------------------------------ #
    @staticmethod
    def robust_scores(values: Union[Sequence[float], np.ndarray]) -> Tuple[np.ndarray, float, str]:
        """Điểm z hiệu chỉnh: lệch khỏi trung vị, chia cho thang đo bền vững."""
        arr = np.asarray(values, dtype=float)
        if arr.size == 0:
            return np.array([]), 0.0, "empty"
        scale, method = ZScoreService.robust_scale(arr)
        if scale <= 0:
            return np.zeros_like(arr), 0.0, method
        return (arr - float(np.median(arr))) / scale, scale, method

    # ------------------------------------------------------------------ #
    @staticmethod
    def _calendar_flags(dates: Sequence[Any], n: int) -> List[Union[bool, None]]:
        """Đánh dấu điểm nằm trong cửa sổ Tết, nơi mô hình chu kỳ cố định lệch pha."""
        lo, hi = TET_WINDOW
        flags: List[Union[bool, None]] = []
        for i in range(n):
            try:
                d = days_to_tet(dates[i])
                flags.append(bool(lo <= d <= hi))
            except (ValueError, TypeError, IndexError):
                # Ngoài bảng ngày Tết đã cấu hình: không biết, và nói là không biết.
                flags.append(None)
        return flags

    # ------------------------------------------------------------------ #
    @staticmethod
    def analyze(
        data: Sequence[float],
        dates: Union[Sequence[Any], None] = None,
        threshold: float = DEFAULT_THRESHOLD,
        period: int = DEFAULT_PERIOD,
        decompose: bool = True,
        max_anomaly_rate: float = MAX_ANOMALY_RATE,
        top_n: int = 10,
    ) -> Dict[str, Any]:
        """
        Phân rã chuỗi rồi chấm điểm bất thường trên phần dư.

        `period` tính theo SỐ ĐIỂM dữ liệu: 7 cho chuỗi ngày có chu kỳ tuần,
        52 cho chuỗi tuần có chu kỳ năm, 365 cho chuỗi ngày có chu kỳ năm.
        `dates` không bắt buộc; có thì điểm trong cửa sổ Tết được đánh dấu.
        """
        if threshold <= 0:
            raise ValueError("threshold phải lớn hơn 0")
        if period < 2:
            raise ValueError("period phải từ 2 trở lên")
        if not 0 < max_anomaly_rate <= 1:
            raise ValueError("max_anomaly_rate phải nằm trong khoảng (0, 1]")

        n = len(data)
        if n == 0:
            return {
                "status": "insufficient_data", "method": "empty", "period": period,
                "threshold": threshold, "scale": 0.0, "decomposed": False,
                "seasonality_removed": False, "cycles_observed": 0.0,
                "anomaly_count": 0, "anomaly_rate": 0.0, "calendar_sensitive_count": 0,
                "sample_size": 0, "points": [], "top_anomalies": [],
                "reliability_note": "Chuỗi rỗng; không có gì để đánh giá.",
                "limitation": "Không đủ dữ liệu.",
            }

        arr = np.asarray(data, dtype=float)
        if not np.all(np.isfinite(arr)):
            raise ValueError("Chuỗi chứa NaN hoặc vô cực; hãy làm sạch trước khi chấm bất thường")
        if dates is not None and len(dates) != n:
            raise ValueError("dates phải cùng độ dài với data")

        cycles = n / period
        full_stl = decompose and n >= max(4, period * 2)

        if decompose and n >= 4:
            parts = STLService.decompose(list(arr), period=period, robust=True)
            trend = np.asarray(parts["trend"], dtype=float)
            seasonal = np.asarray(parts["seasonal"], dtype=float)
            residual = np.asarray(parts["residual"], dtype=float)
            method_base = "stl_residual" if full_stl else "rolling_trend_residual"
        else:
            trend = np.full(n, np.nan)
            seasonal = np.full(n, np.nan)
            residual = arr - float(np.median(arr))
            method_base = "raw_series"

        scores, scale, scale_method = ZScoreService.robust_scores(residual)
        flags = np.abs(scores) > threshold
        cal = ZScoreService._calendar_flags(dates, n) if dates is not None else [None] * n

        points = []
        for i in range(n):
            score = float(scores[i])
            is_anomaly = bool(flags[i])
            points.append({
                "index": i,
                "date": None if dates is None else str(dates[i]),
                "value": float(arr[i]),
                "trend": None if np.isnan(trend[i]) else round(float(trend[i]), 4),
                "seasonal": None if np.isnan(seasonal[i]) else round(float(seasonal[i]), 4),
                "residual": round(float(residual[i]), 4),
                "score": round(score, 4),
                # Giữ tên cũ để nơi gọi cũ không vỡ; giá trị nay là điểm z hiệu chỉnh.
                "z_score": round(score, 4),
                "is_anomaly": is_anomaly,
                "direction": ("high" if score > 0 else "low") if is_anomaly else None,
                "calendar_sensitive": cal[i],
            })

        count = int(flags.sum())
        rate = count / n

        # Thứ tự kiểm tra đi từ giới hạn nghiêm trọng nhất xuống.
        if not full_stl and decompose:
            status = "limited_no_seasonality"
            note = (f"Chuỗi {n} điểm chưa đủ hai chu kỳ {period}; mùa vụ chưa bóc được "
                    f"nên đỉnh mùa vụ vẫn có thể bị báo nhầm là bất thường.")
        elif full_stl and cycles < MIN_CYCLES_FOR_SEASONAL:
            status = "limited_few_cycles"
            note = (f"Chỉ quan sát được {cycles:.1f} chu kỳ (cần từ {MIN_CYCLES_FOR_SEASONAL}). "
                    f"Mỗi pha mùa vụ chỉ có ~{cycles:.0f} quan sát nên LOESS có thể HÚT ĐỘT BIẾN "
                    f"VÀO THÀNH PHẦN MÙA VỤ và làm nó tàng hình. Kết quả chỉ nên dùng tham khảo. "
                    f"Hãy dùng chuỗi ngày với period=7 thay vì chuỗi tuần với period=52.")
        elif rate > max_anomaly_rate:
            status = "unreliable_high_rate"
            note = (f"Gắn cờ {count}/{n} điểm ({rate:.1%}), vượt ngưỡng {max_anomaly_rate:.0%}. "
                    f"Chuỗi quá nhọn hoặc phương sai không đồng nhất so với giả định của mô hình "
                    f"— hãy coi đây là tín hiệu 'chuỗi không phù hợp', không phải danh sách "
                    f"bất thường. Cân nhắc gộp lên cấp cao hơn.")
        else:
            status = "ok"
            note = f"Gắn cờ {count}/{n} điểm ({rate:.1%}), nằm trong ngưỡng kỳ vọng."

        cal_count = sum(1 for p in points if p["is_anomaly"] and p["calendar_sensitive"])
        if cal_count:
            note += (f" {cal_count} điểm bất thường rơi vào cửa sổ Tết — Tết là lễ di động nên "
                     f"mô hình chu kỳ cố định lệch pha ở đó; phần dư kém tin cậy.")

        top = sorted((p for p in points if p["is_anomaly"]),
                     key=lambda p: abs(p["score"]), reverse=True)[:top_n]

        return {
            "status": status,
            "method": f"{method_base}_{scale_method}",
            "period": period,
            "threshold": threshold,
            "scale": round(float(scale), 6),
            "decomposed": bool(decompose and n >= 4),
            "seasonality_removed": bool(full_stl),
            "cycles_observed": round(cycles, 2),
            "anomaly_count": count,
            "anomaly_rate": round(rate, 4),
            "calendar_sensitive_count": cal_count,
            "sample_size": n,
            "reliability_note": note,
            "top_anomalies": top,
            "points": points,
            "limitation": (
                "Bất thường tính trên phần dư sau khi bóc xu hướng và mùa vụ bằng STL, chấm bằng "
                "trung vị và MAD của sai phân liên tiếp. Đỉnh mùa vụ lặp lại không bị coi là bất "
                "thường. Ngưỡng hiệu chuẩn bằng mô phỏng, không phải bảo đảm thống kê. Mô hình "
                "dùng chu kỳ dương lịch cố định nên lệch pha quanh Tết âm lịch."
            ),
        }

    # ------------------------------------------------------------------ #
    @staticmethod
    def detect_anomalies(
        data: Sequence[float],
        threshold: float = DEFAULT_THRESHOLD,
        period: int = DEFAULT_PERIOD,
    ) -> List[Dict[str, Any]]:
        """Giữ nguyên chữ ký cũ: trả về danh sách điểm. Dùng `analyze` để có metadata."""
        return ZScoreService.analyze(data, threshold=threshold, period=period)["points"]


if __name__ == "__main__":
    print("=== TỰ KIỂM TRA MODULE ZSCORE_SERVICE.PY (STL + MAD) ===")

    def daily_series(seed, days=540, spike_at=None, spike_to=None):
        """Chuỗi ngày có chu kỳ tuần — đầu vào đúng của tính năng này."""
        rng = np.random.default_rng(seed)
        t = np.arange(days)
        weekly = 12 * np.sin(2 * np.pi * t / 7)          # cuối tuần bán nhiều hơn
        trend = 100 + 0.05 * t
        v = trend + weekly + rng.normal(0, 5.0, days)
        if spike_at is not None:
            v[spike_at] = spike_to
        return v.tolist()

    # 1. Chuỗi hằng số: không có độ phân tán thì không có bất thường.
    flat = ZScoreService.analyze([5.0] * 120, period=7)
    assert flat["anomaly_count"] == 0 and flat["scale"] == 0.0
    print(f"✓ Chuỗi hằng số: 0 bất thường, phương pháp {flat['method']}")

    # 2. Chuỗi ngày sạch, ~77 chu kỳ: báo động giả phải rất thấp và status ok.
    rates = []
    for seed in range(8):
        r = ZScoreService.analyze(daily_series(seed), period=7)
        assert r["status"] == "ok", f"seed {seed}: status {r['status']} — {r['reliability_note']}"
        rates.append(r["anomaly_rate"])
    print(f"✓ Chuỗi ngày sạch ({8} lần chạy, 540 điểm, 77 chu kỳ): "
          f"báo động giả TB {np.mean(rates):.2%}, tệ nhất {np.max(rates):.2%}")

    # 3. Mùa vụ tuần lặp lại KHÔNG được coi là bất thường.
    clean = ZScoreService.analyze(daily_series(0), period=7)
    weekend_idx = [i for i in range(540) if i % 7 == 1]      # đỉnh chu kỳ tuần
    assert not any(clean["points"][i]["is_anomaly"] for i in weekend_idx), \
        "Đỉnh chu kỳ tuần bị báo nhầm là bất thường"
    print(f"✓ {len(weekend_idx)} đỉnh chu kỳ tuần: không điểm nào bị gắn cờ")

    # 4. Đối chứng: cách cũ (z toàn cục, chuỗi thô, ngưỡng 2.0) bắt nhầm đỉnh mùa vụ.
    arr = np.asarray(daily_series(0))
    old_z = (arr - arr.mean()) / arr.std()
    old_bad = [i for i in weekend_idx if abs(old_z[i]) > 2.0]
    assert old_bad, "Kỳ vọng cách cũ bắt nhầm đỉnh mùa vụ"
    print(f"✓ Đối chứng cách cũ: báo nhầm {len(old_bad)} đỉnh chu kỳ tuần là bất thường")

    # 5. Đột biến tăng và sụt giảm đều phải bắt được, và xếp đầu bảng.
    up = ZScoreService.analyze(daily_series(1, spike_at=300, spike_to=400.0), period=7)
    assert up["points"][300]["is_anomaly"] and up["points"][300]["direction"] == "high"
    assert up["top_anomalies"][0]["index"] == 300
    down = ZScoreService.analyze(daily_series(1, spike_at=300, spike_to=0.0), period=7)
    assert down["points"][300]["is_anomaly"] and down["points"][300]["direction"] == "low"
    print(f"✓ Đột biến tăng (z={up['points'][300]['score']}) và sụt giảm "
          f"(z={down['points'][300]['score']}): bắt được, đứng đầu top_anomalies")

    # 6. GIỚI HẠN ĐÃ BIẾT: ít chu kỳ thì hạ cờ tin cậy, không im lặng.
    rng = np.random.default_rng(0)
    w = 52 * 5
    t = np.arange(w)
    few = (60 + 120 * np.exp(-0.5 * ((t % 52 - 4) / 2.5) ** 2) + rng.normal(0, 3.0, w)).tolist()
    fc = ZScoreService.analyze(few, period=52)
    assert fc["status"] == "limited_few_cycles", f"Kỳ vọng limited_few_cycles, nhận {fc['status']}"
    assert fc["cycles_observed"] == 5.0
    assert "HÚT ĐỘT BIẾN" in fc["reliability_note"]
    print(f"✓ Chỉ {fc['cycles_observed']} chu kỳ: status {fc['status']}, có cảnh báo đột biến bị che")

    # 7. Chốt chặn tỉ lệ trên chuỗi đuôi nặng.
    noisy = (rng.standard_t(df=1.5, size=540) * 10).tolist()
    nz = ZScoreService.analyze(noisy, period=7)
    if nz["anomaly_rate"] > MAX_ANOMALY_RATE:
        assert nz["status"] == "unreliable_high_rate"
        print(f"✓ Chốt chặn tỉ lệ: {nz['anomaly_rate']:.1%} -> status {nz['status']}")
    else:
        print(f"✓ Chuỗi nhiễu nặng đuôi: {nz['anomaly_rate']:.1%}, trong ngưỡng")

    # 8. Dự phòng khi mọi sai phân bằng 0.
    fb = ZScoreService.analyze([1.0] * 119 + [99.0], period=7, decompose=False)
    assert fb["anomaly_count"] >= 1, "Dự phòng phải bắt được điểm lệch"
    print(f"✓ Dự phòng khi sai phân = 0: {fb['method']}, bắt {fb['anomaly_count']} bất thường")

    # 9. Chuỗi quá ngắn: khai báo rõ chưa bóc được mùa vụ.
    short = ZScoreService.analyze([1.0, 5.0, 2.0, 3.0, 40.0], period=52)
    assert short["seasonality_removed"] is False and short["status"] == "limited_no_seasonality"
    print(f"✓ Chuỗi ngắn: status {short['status']}")

    # 10. Đánh dấu cửa sổ Tết khi có dates.
    dates = [str(np.datetime64("2023-01-01") + np.timedelta64(i, "D")) for i in range(540)]
    cal = ZScoreService.analyze(daily_series(2, spike_at=14, spike_to=500.0),
                                dates=dates, period=7)
    assert cal["points"][14]["calendar_sensitive"] is True, "Điểm sát Tết phải được đánh dấu"
    assert cal["points"][300]["calendar_sensitive"] is False
    print(f"✓ Đánh dấu cửa sổ Tết: 2023-01-15 calendar_sensitive=True, "
          f"{cal['calendar_sensitive_count']} bất thường rơi vào cửa sổ Tết")

    # 11. Đầu vào bẩn bị từ chối thay vì trả kết quả rác.
    for bad, label in ((float("nan"), "NaN"), (float("inf"), "vô cực")):
        try:
            ZScoreService.analyze([1.0, 2.0, bad, 4.0], period=2)
            raise AssertionError(f"Phải từ chối chuỗi chứa {label}")
        except ValueError:
            pass
    try:
        ZScoreService.analyze([1.0, 2.0, 3.0, 4.0], threshold=0.0)
        raise AssertionError("Phải từ chối threshold <= 0")
    except ValueError:
        pass
    try:
        ZScoreService.analyze([1.0, 2.0, 3.0, 4.0], period=1)
        raise AssertionError("Phải từ chối period < 2")
    except ValueError:
        pass
    try:
        ZScoreService.analyze([1.0, 2.0, 3.0, 4.0], max_anomaly_rate=0.0)
        raise AssertionError("Phải từ chối max_anomaly_rate = 0")
    except ValueError:
        pass
    try:
        ZScoreService.analyze([1.0, 2.0], dates=["2023-01-01"], period=2)
        raise AssertionError("Phải từ chối dates lệch độ dài")
    except ValueError:
        pass
    print("✓ Từ chối NaN, vô cực, tham số không hợp lệ và dates lệch độ dài")

    # 12. Chữ ký cũ vẫn dùng được.
    legacy = ZScoreService.detect_anomalies(daily_series(3), period=7)
    assert isinstance(legacy, list) and "z_score" in legacy[0]
    print("✓ Tương thích ngược: detect_anomalies vẫn trả danh sách có khoá z_score")

    print("\n✅ TẤT CẢ SELF-CHECKS CỦA ZSCORE_SERVICE.PY ĐÃ PASS!")
