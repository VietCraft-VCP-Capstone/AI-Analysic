import math

import cv2
import numpy as np

LONG_SIDE = 512
BORDER_FRAC = 0.05
BORDER_TOL = 12
CENTER_FRAC = 0.6
CANNY_SIGMA = 0.33
CANNY_LO = (20, 100)
CANNY_HI = (50, 200)
MSER_MAX_AREA = 14400
TEXT_ASPECT = (0.1, 1.5)
TEXT_HEIGHT = (8, 0.15)
MIN_SIDE = 500
MIN_SHARPNESS = 4.0
BRIGHTNESS_RANGE = (0.25, 0.9)
MIN_BORDER_UNIFORM = 0.4
MIN_BRIGHT_CONTRAST = 0.02
MAX_TEXT_RATIO = 0.08
ASPECT_RANGE = (0.75, 1.34)

ISSUES = {
    "low_resolution": ("img_w", "Ảnh có cạnh ngắn dưới 500px, nên dùng ảnh lớn hơn để hiển thị rõ nét."),
    "blurry": ("img_sharpness", "Ảnh bị mờ, hãy chụp lại với tiêu cự rõ nét."),
    "too_dark": ("img_brightness", "Ảnh quá tối, hãy bổ sung ánh sáng."),
    "too_bright": ("img_brightness", "Ảnh bị cháy sáng, hãy giảm độ sáng khi chụp."),
    "busy_background": ("img_border_uniform", "Nền ảnh rối, nên dùng nền trơn để sản phẩm nổi bật."),
    "text_overlay": ("img_text_ratio", "Ảnh chèn nhiều chữ, nên giữ ảnh sản phẩm sạch."),
    "bad_aspect": ("img_aspect", "Tỉ lệ ảnh lệch, nên dùng ảnh vuông hoặc gần vuông."),
}


def _gray(img):
    rgb = np.asarray(img.convert("RGB"))
    g = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    h, w = g.shape
    scale = LONG_SIDE / max(h, w)
    interp = cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR
    return cv2.resize(g, (max(1, round(w * scale)), max(1, round(h * scale))), interpolation=interp)


def _border_uniform(g):
    h, w = g.shape
    bh, bw = max(1, int(h * BORDER_FRAC)), max(1, int(w * BORDER_FRAC))
    mask = np.ones(g.shape, bool)
    mask[bh:h - bh, bw:w - bw] = False
    vals = g[mask].astype(np.float32)
    return float(np.mean(np.abs(vals - np.median(vals)) < BORDER_TOL))


def _center_edges(g):
    h, w = g.shape
    med = float(np.median(g))
    lo = int(np.clip((1 - CANNY_SIGMA) * med, *CANNY_LO))
    hi = int(np.clip((1 + CANNY_SIGMA) * med, *CANNY_HI))
    edges = cv2.Canny(g, lo, hi)
    m = (1 - CENTER_FRAC) / 2
    return float(np.mean(edges[int(h * m):int(h * (1 - m)), int(w * m):int(w * (1 - m))] > 0))


def _text_ratio(g):
    mser = cv2.MSER_create(max_area=MSER_MAX_AREA)
    mser.setMinDiversity(0)
    regions, boxes = mser.detectRegions(g)
    h, w = g.shape
    lo_h, hi_h = TEXT_HEIGHT[0], TEXT_HEIGHT[1] * h
    mask = np.zeros(g.shape, np.uint8)
    for pts, (_, _, bw, bh) in zip(regions, boxes):
        if lo_h <= bh <= hi_h and TEXT_ASPECT[0] <= bw / bh <= TEXT_ASPECT[1]:
            mask[pts[:, 1], pts[:, 0]] = 1
    return float(mask.sum() / (h * w))


def quality(img) -> dict[str, float]:
    w, h = img.size
    g = _gray(img)
    return {
        "img_w": float(w),
        "img_h": float(h),
        "img_aspect": w / h,
        "img_sharpness": math.log1p(float(cv2.Laplacian(g, cv2.CV_64F).var())),
        "img_brightness": float(g.mean()) / 255,
        "img_contrast": float(g.std()) / 255,
        "img_border_uniform": _border_uniform(g),
        "img_center_edges": _center_edges(g),
        "img_text_ratio": _text_ratio(g),
    }


def dhash(img) -> int:
    g = cv2.resize(_gray(img), (9, 8), interpolation=cv2.INTER_AREA)
    bits = (g[:, 1:] > g[:, :-1]).flatten()
    return int("".join("1" if b else "0" for b in bits), 2)


def hamming(a: int, b: int) -> int:
    return (a ^ b).bit_count()


def quality_issues(q) -> list[dict]:
    lo_b, hi_b = BRIGHTNESS_RANGE
    flags = {
        "low_resolution": min(q["img_w"], q["img_h"]) < MIN_SIDE,
        "blurry": q["img_sharpness"] < MIN_SHARPNESS,
        "too_dark": q["img_brightness"] < lo_b,
        "too_bright": q["img_brightness"] > hi_b
        and (q["img_border_uniform"] < MIN_BORDER_UNIFORM or q["img_contrast"] < MIN_BRIGHT_CONTRAST),
        "busy_background": q["img_border_uniform"] < MIN_BORDER_UNIFORM,
        "text_overlay": q["img_text_ratio"] > MAX_TEXT_RATIO,
        "bad_aspect": not ASPECT_RANGE[0] <= q["img_aspect"] <= ASPECT_RANGE[1],
    }
    return [{"code": c, "message": ISSUES[c][1], "field": ISSUES[c][0]} for c, on in flags.items() if on]
