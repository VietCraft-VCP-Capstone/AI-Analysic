import threading

import numpy as np
import pytest
from PIL import Image

from app.core.f29 import factors_v3, image_check
from app.core.listing_intel.vision import dhash, quality, quality_issues

URL = "https://res.cloudinary.com/a/image/upload/{}.jpg"
REAL_ANALYZE = image_check.analyze


@pytest.fixture(autouse=True)
def real_analyze(monkeypatch):
    monkeypatch.setattr(image_check, "analyze", REAL_ANALYZE)


def checker(size=256, tile=16):
    idx = np.indices((size, size)).sum(axis=0) // tile % 2
    return Image.fromarray((idx * 150 + 50).astype(np.uint8)).convert("RGB")


def noise(seed):
    rng = np.random.default_rng(seed)
    return Image.fromarray(rng.integers(0, 256, (256, 256, 3), dtype=np.uint8))


def jitter(img, seed=0):
    rng = np.random.default_rng(seed)
    arr = np.asarray(img).astype(int) + rng.integers(-2, 3, (*np.asarray(img).shape[:2], 3))
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


def loaded(img, vec=None):
    return {"vec": vec, "display": quality(img), "dhash": format(dhash(img), "016x")}


def fake(items):
    def fetch(url, save=True):
        return items[url]

    return fetch


def test_near_identical_second_is_duplicate():
    urls = [URL.format(n) for n in ("one", "two", "other")]
    items = dict(zip(urls, [loaded(checker()), loaded(jitter(checker())), loaded(noise(1))]))
    out = image_check.analyze(urls, "áo thun", "fashion", fetch=fake(items))
    assert [r["duplicate"] for r in out["images"]] == [False, True, False]
    assert out["state"] == "scored"


def test_dark_blurred_image_reports_quality_issue():
    dark = Image.fromarray(np.full((600, 600, 3), 30, np.uint8))
    items = {URL.format("dark"): loaded(dark)}
    out = image_check.analyze([URL.format("dark")], "t", "fashion", fetch=fake(items))
    expected = {i["code"] for i in quality_issues(quality(dark))}
    assert "too_dark" in expected
    assert set(out["images"][0]["issues"]) == expected
    assert out["useful"] == 0


def test_all_fetches_raise_is_technical_failure():
    def boom(url, save=True):
        raise OSError("network down")

    urls = [URL.format("x"), URL.format("x") + "?v=2", URL.format("y")]
    out = image_check.analyze(urls, "t", "fashion", fetch=boom)
    assert out["state"] == "technical_failure"
    assert out["useful"] == 2
    assert out["method"] == "heuristic"


def test_fetch_past_budget_uses_fallback():
    gate = threading.Event()

    def stuck(url, save=True):
        gate.wait(5)
        return loaded(checker())

    try:
        out = image_check.analyze([URL.format("slow")], "t", "fashion", fetch=stuck, budget=0.05)
    finally:
        gate.set()
    assert out["state"] == "technical_failure"
    assert out["useful"] == 1 and out["unanalyzed"] == 1


def test_unanalyzed_images_count_by_url_and_are_flagged():
    dark = Image.fromarray(np.full((600, 600, 3), 30, np.uint8))
    urls = [URL.format("dark"), URL.format("lost")]
    out = image_check.analyze(urls, "t", "fashion", fetch=fake({urls[0]: loaded(dark)}))
    row = factors_v3.image_row(out, 2)
    assert out["useful"] == 1 and out["unanalyzed"] == 1
    assert row["method"] == "heuristic" and row["evidence"]["unanalyzed"] == 1
    assert row["reason"] == "Có 1 ảnh đạt, sản phẩm cùng loại thường có 2 ảnh (1 ảnh chưa phân tích được, tạm tính theo đường dẫn)"


def test_siglip_vectors_only_set_flag_and_keep_heuristic_method():
    analysis = {"state": "scored", "useful": 2, "unanalyzed": 0, "images": [], "method": "ml_unvalidated"}
    row = factors_v3.image_row(analysis, 4)
    assert row["method"] == "heuristic" and row["evidence"]["siglip"] is True


def test_category_match_is_argmax_and_none_without_vectors(monkeypatch):
    bank = (["fashion", "home"], np.eye(2, dtype=np.float32))
    monkeypatch.setattr(image_check, "_group_bank", lambda: bank)
    urls = [URL.format("a"), URL.format("b")]
    items = {urls[0]: loaded(checker(), vec=np.array([0.9, 0.1], np.float32)), urls[1]: loaded(noise(2), vec=None)}
    out = image_check.analyze(urls, "t", "fashion", fetch=fake(items))
    assert [r["category_match"] for r in out["images"]] == [True, None]
    assert out["method"] == "ml_unvalidated"


def test_no_urls_is_seller_missing():
    out = image_check.analyze([], "t", None, fetch=fake({}))
    assert out == {"state": "seller_missing", "useful": 0, "images": [], "method": "heuristic"}


def test_non_plain_background_is_not_flagged_as_busy():
    img = Image.fromarray((np.indices((600, 600)).sum(0) % 256).astype(np.uint8)).convert("RGB")
    out = image_check.analyze([URL.format("bg")], "t", "fashion", fetch=fake({URL.format("bg"): loaded(img)}))
    assert "busy_background" not in out["images"][0]["issues"]
