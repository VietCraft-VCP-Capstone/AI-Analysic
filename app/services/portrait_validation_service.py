"""
portrait_validation_service.py — Kiểm tra ảnh chân dung KYC.

Tính năng:
  1. Phát hiện khuôn mặt (OpenCV Haar Cascade)
  2. Kiểm tra chất lượng ảnh chân dung (blur, brightness, resolution, face ratio)
  3. Phát hiện ảnh AI-generated (phân tích tần số, texture, color artifacts)

Kiến trúc: Được gọi qua FastAPI endpoint, KHÔNG truy vấn DB.
"""

import logging
from typing import Any, Dict, List

import numpy as np

logger = logging.getLogger("portrait_validation")


# ═══════════════════════════════════════════════════════════════════════════
# 1. PHÁT HIỆN KHUÔN MẶT (OpenCV Haar Cascade)
# ═══════════════════════════════════════════════════════════════════════════

def detect_faces(img_array: np.ndarray) -> Dict[str, Any]:
    """Phát hiện khuôn mặt trong ảnh chân dung.

    Trả về: số lượng khuôn mặt, vị trí, tỷ lệ khuôn mặt so với ảnh.
    """
    import cv2

    gray = cv2.cvtColor(img_array, cv2.COLOR_BGR2GRAY) if len(img_array.shape) == 3 else img_array

    # Dùng Haar Cascade — đã có sẵn trong OpenCV, không cần tải thêm
    face_cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    )

    # Detect ở nhiều scale để bắt cả mặt gần và xa
    faces = face_cascade.detectMultiScale(
        gray,
        scaleFactor=1.1,
        minNeighbors=5,
        minSize=(60, 60),
    )

    h, w = img_array.shape[:2]
    img_area = h * w

    face_list = []
    for (x, y, fw, fh) in faces:
        face_area = fw * fh
        face_list.append({
            "x": int(x), "y": int(y),
            "width": int(fw), "height": int(fh),
            "area_ratio": round(face_area / img_area, 4),
        })

    # Sắp xếp theo diện tích lớn nhất
    face_list.sort(key=lambda f: f["area_ratio"], reverse=True)

    # Khuôn mặt chính (lớn nhất)
    primary_face = face_list[0] if face_list else None

    result: Dict[str, Any] = {
        "face_count": len(face_list),
        "faces": face_list[:5],  # Giới hạn 5 mặt
        "primary_face": primary_face,
        "has_single_face": len(face_list) == 1,
        "warnings": [],
    }

    if len(face_list) == 0:
        result["warnings"].append(
            "Không phát hiện khuôn mặt trong ảnh. Vui lòng tải lên ảnh chân dung rõ mặt, nhìn thẳng."
        )
    elif len(face_list) > 1:
        result["warnings"].append(
            f"Phát hiện {len(face_list)} khuôn mặt. Ảnh chân dung KYC chỉ nên có 1 khuôn mặt duy nhất."
        )

    # Kiểm tra tỷ lệ khuôn mặt — quá nhỏ hoặc quá lớn
    if primary_face:
        ratio = primary_face["area_ratio"]
        if ratio < 0.03:
            result["warnings"].append(
                "Khuôn mặt quá nhỏ trong ảnh. Vui lòng chụp cận hơn để thấy rõ khuôn mặt."
            )
        elif ratio > 0.7:
            result["warnings"].append(
                "Khuôn mặt chiếm quá nhiều khung hình. Nên chụp thấy cả vai và cổ."
            )

    return result


# ═══════════════════════════════════════════════════════════════════════════
# 2. KIỂM TRA CHẤT LƯỢNG ẢNH CHÂN DUNG
# ═══════════════════════════════════════════════════════════════════════════

def check_portrait_quality(img_array: np.ndarray) -> Dict[str, Any]:
    """Kiểm tra chất lượng ảnh chân dung: blur, brightness, resolution."""
    import cv2

    h, w = img_array.shape[:2]
    gray = cv2.cvtColor(img_array, cv2.COLOR_BGR2GRAY) if len(img_array.shape) == 3 else img_array

    # Blur score (Laplacian variance)
    blur_score = cv2.Laplacian(gray, cv2.CV_64F).var()

    # Brightness
    brightness = float(np.mean(gray))

    # Contrast (standard deviation of intensity)
    contrast = float(np.std(gray))

    result: Dict[str, Any] = {
        "resolution": f"{w}x{h}",
        "is_resolution_ok": w >= 200 and h >= 200,
        "blur_score": round(blur_score, 2),
        "is_sharp": blur_score >= 40.0,
        "brightness": round(brightness, 2),
        "is_brightness_ok": 30 < brightness < 235,
        "contrast": round(contrast, 2),
        "is_contrast_ok": contrast > 20,
        "warnings": [],
    }

    if not result["is_resolution_ok"]:
        result["warnings"].append(f"Ảnh quá nhỏ ({w}×{h}). Cần tối thiểu 200×200 pixel.")
    if not result["is_sharp"]:
        result["warnings"].append("Ảnh chân dung bị mờ. Vui lòng chụp lại rõ nét hơn.")
    if brightness <= 30:
        result["warnings"].append("Ảnh quá tối. Vui lòng chụp ở nơi có đủ ánh sáng.")
    elif brightness >= 235:
        result["warnings"].append("Ảnh bị lóa sáng. Vui lòng chụp lại tránh ánh sáng trực tiếp.")
    if not result["is_contrast_ok"]:
        result["warnings"].append("Ảnh có độ tương phản quá thấp. Kiểm tra lại chất lượng ảnh.")

    return result


# ═══════════════════════════════════════════════════════════════════════════
# 3. PHÁT HIỆN ẢNH AI-GENERATED
# ═══════════════════════════════════════════════════════════════════════════
#
# Phương pháp: Kết hợp nhiều heuristic phân tích tần số và texture.
# Ảnh AI-generated (Stable Diffusion, Midjourney, DALL-E) thường có:
#   - Phổ tần số mượt bất thường (thiếu noise tự nhiên)
#   - Texture đồng nhất quá mức
#   - Color channel correlation bất thường
#   - JPEG quantization artifacts khác ảnh thật
# ═══════════════════════════════════════════════════════════════════════════

def _analyze_frequency_spectrum(img_array: np.ndarray) -> Dict[str, Any]:
    """Phân tích phổ tần số FFT — ảnh AI thường có high-frequency rolloff mượt hơn ảnh thật."""
    import cv2

    gray = cv2.cvtColor(img_array, cv2.COLOR_BGR2GRAY) if len(img_array.shape) == 3 else img_array

    # Resize để chuẩn hóa FFT
    resized = cv2.resize(gray, (256, 256))

    f_transform = np.fft.fft2(resized.astype(float))
    f_shift = np.fft.fftshift(f_transform)
    magnitude = np.log1p(np.abs(f_shift))

    h, w = magnitude.shape
    cy, cx = h // 2, w // 2

    # Tính năng lượng ở 3 vùng tần số
    # Tần số thấp (trung tâm), trung bình, cao (rìa)
    r_low = min(h, w) // 8
    r_mid = min(h, w) // 4
    r_high = min(h, w) // 2

    mask_low = np.zeros_like(magnitude, dtype=bool)
    mask_mid = np.zeros_like(magnitude, dtype=bool)
    mask_high = np.zeros_like(magnitude, dtype=bool)

    for y in range(h):
        for x in range(w):
            d = np.sqrt((y - cy) ** 2 + (x - cx) ** 2)
            if d <= r_low:
                mask_low[y, x] = True
            elif d <= r_mid:
                mask_mid[y, x] = True
            elif d <= r_high:
                mask_high[y, x] = True

    energy_low = float(np.mean(magnitude[mask_low])) if np.any(mask_low) else 0
    energy_mid = float(np.mean(magnitude[mask_mid])) if np.any(mask_mid) else 0
    energy_high = float(np.mean(magnitude[mask_high])) if np.any(mask_high) else 0

    # Ảnh AI thường có tỷ lệ energy_high/energy_mid thấp hơn ảnh thật
    # (AI tạo ra ảnh "mượt" hơn, ít high-frequency noise)
    hm_ratio = energy_high / energy_mid if energy_mid > 0 else 0

    return {
        "energy_low": round(energy_low, 3),
        "energy_mid": round(energy_mid, 3),
        "energy_high": round(energy_high, 3),
        "high_mid_ratio": round(hm_ratio, 4),
    }


def _analyze_texture_uniformity(img_array: np.ndarray) -> Dict[str, Any]:
    """Phân tích tính đồng nhất texture — ảnh AI thường có texture quá mượt hoặc lặp lại."""
    import cv2

    gray = cv2.cvtColor(img_array, cv2.COLOR_BGR2GRAY) if len(img_array.shape) == 3 else img_array
    resized = cv2.resize(gray, (256, 256))

    # Chia ảnh thành 8x8 blocks, tính variance của mỗi block
    block_size = 32
    variances = []
    for y in range(0, 256, block_size):
        for x in range(0, 256, block_size):
            block = resized[y:y + block_size, x:x + block_size]
            variances.append(float(np.var(block)))

    # Ảnh thật có variance giữa các block dao động mạnh hơn
    # Ảnh AI có variance giữa các block đồng đều hơn
    variance_of_variances = float(np.var(variances))
    mean_variance = float(np.mean(variances))

    # Coefficient of Variation của block variances
    cv_blocks = (np.std(variances) / np.mean(variances)) if np.mean(variances) > 0 else 0

    return {
        "mean_block_variance": round(mean_variance, 2),
        "variance_of_variances": round(variance_of_variances, 2),
        "cv_blocks": round(float(cv_blocks), 4),
    }


def _analyze_color_statistics(img_array: np.ndarray) -> Dict[str, Any]:
    """Phân tích thống kê màu sắc — ảnh AI có color distribution khác ảnh thật."""
    if len(img_array.shape) != 3 or img_array.shape[2] != 3:
        return {"skipped": True, "reason": "Ảnh không phải RGB"}

    # Tính correlation giữa các channel
    b, g, r = img_array[:, :, 0].flatten().astype(float), \
              img_array[:, :, 1].flatten().astype(float), \
              img_array[:, :, 2].flatten().astype(float)

    # Ảnh AI thường có channel correlation cao bất thường
    rg_corr = float(np.corrcoef(r, g)[0, 1])
    rb_corr = float(np.corrcoef(r, b)[0, 1])
    gb_corr = float(np.corrcoef(g, b)[0, 1])
    avg_corr = (abs(rg_corr) + abs(rb_corr) + abs(gb_corr)) / 3

    # Phân tích saturation distribution
    import cv2
    hsv = cv2.cvtColor(img_array, cv2.COLOR_BGR2HSV)
    saturation = hsv[:, :, 1].flatten().astype(float)
    sat_std = float(np.std(saturation))
    sat_mean = float(np.mean(saturation))

    return {
        "rg_correlation": round(rg_corr, 4),
        "rb_correlation": round(rb_corr, 4),
        "gb_correlation": round(gb_corr, 4),
        "avg_channel_correlation": round(avg_corr, 4),
        "saturation_mean": round(sat_mean, 2),
        "saturation_std": round(sat_std, 2),
    }


def _analyze_noise_pattern(img_array: np.ndarray) -> Dict[str, Any]:
    """Phân tích pattern noise — ảnh thật có sensor noise tự nhiên, ảnh AI thì không."""
    import cv2

    gray = cv2.cvtColor(img_array, cv2.COLOR_BGR2GRAY) if len(img_array.shape) == 3 else img_array
    resized = cv2.resize(gray, (256, 256)).astype(float)

    # Trừ gaussian blur để lấy noise residual
    blurred = cv2.GaussianBlur(resized, (5, 5), 1.0)
    noise = resized - blurred

    # Thống kê noise
    noise_std = float(np.std(noise))
    noise_kurtosis = float(
        np.mean((noise - np.mean(noise)) ** 4) / (np.std(noise) ** 4)
    ) if np.std(noise) > 0 else 0

    # Ảnh thật: noise_std thường 2-15, kurtosis ~3 (Gaussian)
    # Ảnh AI: noise_std thường < 2 (quá mượt) hoặc noise pattern lặp lại

    return {
        "noise_std": round(noise_std, 3),
        "noise_kurtosis": round(noise_kurtosis, 3),
    }


def detect_ai_generated(img_array: np.ndarray) -> Dict[str, Any]:
    """Tổng hợp các phân tích để phát hiện ảnh AI-generated.

    Kết hợp 4 tín hiệu:
      1. Frequency spectrum (thiếu high-freq noise)
      2. Texture uniformity (quá mượt)
      3. Color statistics (channel correlation bất thường)
      4. Noise pattern (thiếu sensor noise)

    Trả về: is_likely_ai, confidence_score, chi tiết từng phân tích.
    """
    freq = _analyze_frequency_spectrum(img_array)
    texture = _analyze_texture_uniformity(img_array)
    color = _analyze_color_statistics(img_array)
    noise = _analyze_noise_pattern(img_array)

    # ── Scoring system ──
    # Mỗi tín hiệu AI cho 1 điểm, tối đa 4 điểm
    ai_signals: List[str] = []

    # Signal 1: High-frequency rolloff — ảnh AI có hm_ratio thấp
    if freq["high_mid_ratio"] < 0.45:
        ai_signals.append("Phổ tần số cao bất thường thấp (ảnh quá mượt, thiếu chi tiết tự nhiên)")

    # Signal 2: Texture quá đồng nhất
    if texture["cv_blocks"] < 0.35:
        ai_signals.append("Texture ảnh đồng nhất bất thường (thiếu biến đổi tự nhiên giữa các vùng)")

    # Signal 3: Noise quá thấp (ảnh AI không có sensor noise)
    if noise["noise_std"] < 1.5:
        ai_signals.append("Ảnh gần như không có nhiễu cảm biến (sensor noise), đặc điểm của ảnh AI")

    # Signal 4: Noise kurtosis bất thường (> 10 = có artifact pattern)
    if noise["noise_kurtosis"] > 10:
        ai_signals.append("Pattern nhiễu bất thường, có thể là artifact từ AI generation")

    # Signal 5: Channel correlation quá cao (ảnh AI thường có color correlation > 0.95)
    if not color.get("skipped") and color["avg_channel_correlation"] > 0.96:
        ai_signals.append("Tương quan giữa các kênh màu quá cao, không tự nhiên")

    # Tính confidence
    total_signals = 5
    ai_score = len(ai_signals) / total_signals

    # >= 3/5 signals → likely AI
    is_likely_ai = len(ai_signals) >= 3

    warnings: List[str] = []
    if is_likely_ai:
        warnings.append(
            "⚠ Ảnh có nhiều dấu hiệu được tạo bởi AI (Deepfake/AI-generated). "
            "Vui lòng tải lên ảnh chân dung thật chụp bằng điện thoại hoặc máy ảnh."
        )
    elif len(ai_signals) >= 2:
        warnings.append(
            "Ảnh có một số đặc điểm bất thường. Nếu đây là ảnh thật, "
            "vui lòng đảm bảo ảnh được chụp trực tiếp (không qua chỉnh sửa quá nhiều)."
        )

    return {
        "is_likely_ai": is_likely_ai,
        "ai_confidence": round(ai_score, 2),
        "ai_signals_count": len(ai_signals),
        "ai_signals": ai_signals,
        "warnings": warnings,
        "details": {
            "frequency": freq,
            "texture": texture,
            "color": {k: v for k, v in color.items() if k != "skipped"},
            "noise": noise,
        },
    }


# ═══════════════════════════════════════════════════════════════════════════
# 4. HÀM CHÍNH: VALIDATE PORTRAIT
# ═══════════════════════════════════════════════════════════════════════════

def validate_portrait(image_bytes: bytes) -> Dict[str, Any]:
    """Kiểm tra toàn diện ảnh chân dung KYC.

    Trả về: face_detection, quality, ai_detection, overall verdict.
    """
    import cv2

    # Decode ảnh
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    if img is None:
        return {
            "success": False,
            "error": "Không thể đọc file ảnh. Vui lòng tải lên ảnh JPG, PNG hoặc WebP.",
            "face_detection": None,
            "quality": None,
            "ai_detection": None,
            "verdict": None,
        }

    # ── Bước 1: Phát hiện khuôn mặt ──
    face_result = detect_faces(img)

    # ── Bước 2: Kiểm tra chất lượng ──
    quality_result = check_portrait_quality(img)

    # ── Bước 3: Phát hiện ảnh AI ──
    ai_result = detect_ai_generated(img)

    # ── Bước 4: Tổng hợp verdict ──
    all_warnings: List[str] = []
    all_warnings.extend(face_result.get("warnings", []))
    all_warnings.extend(quality_result.get("warnings", []))
    all_warnings.extend(ai_result.get("warnings", []))

    checks = {
        "has_face": face_result["face_count"] > 0,
        "single_face": face_result["has_single_face"],
        "image_quality_ok": (
            quality_result["is_resolution_ok"]
            and quality_result["is_sharp"]
            and quality_result["is_brightness_ok"]
        ),
        "not_ai_generated": not ai_result["is_likely_ai"],
    }

    passed = sum(1 for v in checks.values() if v)
    total = len(checks)
    confidence = round(passed / total, 2)

    # Ảnh hợp lệ khi: có mặt + chất lượng OK + không phải AI
    is_valid = checks["has_face"] and checks["image_quality_ok"] and checks["not_ai_generated"]

    verdict = {
        "is_valid": is_valid,
        "confidence_score": confidence,
        "checks": checks,
        "status": "PASSED" if is_valid else "FAILED",
        "message": (
            "Ảnh chân dung hợp lệ."
            if is_valid
            else "Ảnh chân dung không đạt yêu cầu. Vui lòng kiểm tra các cảnh báo bên dưới."
        ),
    }

    return {
        "success": True,
        "face_detection": {
            "face_count": face_result["face_count"],
            "has_single_face": face_result["has_single_face"],
            "primary_face": face_result["primary_face"],
        },
        "quality": {
            "resolution": quality_result["resolution"],
            "blur_score": quality_result["blur_score"],
            "is_sharp": quality_result["is_sharp"],
            "brightness": quality_result["brightness"],
        },
        "ai_detection": {
            "is_likely_ai": ai_result["is_likely_ai"],
            "ai_confidence": ai_result["ai_confidence"],
            "ai_signals_count": ai_result["ai_signals_count"],
            "ai_signals": ai_result["ai_signals"],
        },
        "verdict": verdict,
        "warnings": all_warnings,
    }
