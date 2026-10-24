import cv2
import numpy as np
from PIL import Image

from app.core.listing_intel import vision


def checker(size=256, tile=16):
    idx = np.indices((size, size)).sum(axis=0) // tile % 2
    return Image.fromarray((idx * 150 + 50).astype(np.uint8)).convert("RGB")


def noise(seed):
    rng = np.random.default_rng(seed)
    return Image.fromarray(rng.integers(0, 256, (256, 256, 3), dtype=np.uint8))


def brighten(img, k=1.1):
    return Image.fromarray(np.clip(np.asarray(img) * k, 0, 255).astype(np.uint8))


def test_blur_detected():
    sharp = checker()
    blurred = Image.fromarray(cv2.GaussianBlur(np.asarray(sharp), (21, 21), 0))
    qs, qb = vision.quality(sharp), vision.quality(blurred)
    assert qb["img_sharpness"] < qs["img_sharpness"]
    assert "blurry" in {i["code"] for i in vision.quality_issues(qb)}
    assert "blurry" not in {i["code"] for i in vision.quality_issues(qs)}


def test_white_border_uniform():
    arr = np.full((600, 600, 3), 255, np.uint8)
    arr[200:400, 200:400] = 0
    assert vision.quality(Image.fromarray(arr))["img_border_uniform"] > 0.9


def test_quality_issues_flags_and_fields():
    ok = {"img_w": 800, "img_h": 800, "img_aspect": 1.0, "img_sharpness": 9.0,
          "img_brightness": 0.5, "img_contrast": 0.25, "img_border_uniform": 0.9, "img_text_ratio": 0.0}
    assert vision.quality_issues(ok) == []
    bad = {**ok, "img_w": 300, "img_aspect": 2.0, "img_brightness": 0.1, "img_border_uniform": 0.1, "img_text_ratio": 0.2}
    got = {i["code"]: i for i in vision.quality_issues(bad)}
    assert set(got) == {"low_resolution", "too_dark", "busy_background", "text_overlay", "bad_aspect"}
    assert all(i["message"] and i["field"] for i in got.values())
    assert "too_bright" in {i["code"] for i in vision.quality_issues({**ok, "img_brightness": 0.95, "img_border_uniform": 0.2})}


def test_dhash_near_duplicate():
    base = checker()
    assert vision.hamming(vision.dhash(base), vision.dhash(brighten(base))) <= 6
    assert 0 <= vision.dhash(base) < 2 ** 64
    assert vision.hamming(vision.dhash(noise(1)), vision.dhash(noise(2))) > 20


def test_brightness_invariance():
    rng = np.random.default_rng(3)
    base = cv2.GaussianBlur(rng.integers(40, 200, (400, 500, 3), dtype=np.uint8), (0, 0), 2)
    base[150:250, 200:300] = 30
    img = Image.fromarray(base)
    a, b = vision.quality(img), vision.quality(brighten(img))
    for k in a:
        if k != "img_brightness":
            assert abs(a[k] - b[k]) <= 0.15 * max(abs(a[k]), 1e-6), k


def test_pale_product_on_white_has_center_edges():
    arr = np.full((600, 600, 3), 255, np.uint8)
    arr[200:400, 200:400] = 200
    assert vision.quality(Image.fromarray(arr))["img_center_edges"] > 0


def codes(img):
    return {i["code"] for i in vision.quality_issues(vision.quality(img))}


def test_white_background_dark_product_not_too_bright():
    arr = np.full((600, 600, 3), 255, np.uint8)
    arr[210:390, 210:390] = 40
    q = vision.quality(Image.fromarray(arr))
    assert q["img_brightness"] > vision.BRIGHTNESS_RANGE[1]
    assert "too_bright" not in codes(Image.fromarray(arr))


def test_washed_out_image_too_bright():
    rng = np.random.default_rng(5)
    arr = rng.integers(244, 256, (600, 600, 3), dtype=np.uint8)
    assert "too_bright" in codes(Image.fromarray(arr))


def test_overexposed_striped_scene_too_bright():
    levels = np.array([255, 235, 215], np.uint8)[np.arange(600) // 20 % 3]
    img = Image.fromarray(np.broadcast_to(levels[None, :, None], (600, 600, 3)).copy())
    q = vision.quality(img)
    assert q["img_brightness"] > 0.9 and q["img_border_uniform"] < vision.MIN_BORDER_UNIFORM
    assert "too_bright" in codes(img)
