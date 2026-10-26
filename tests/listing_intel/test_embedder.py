import threading
import time
import unicodedata
from collections import Counter

import numpy as np
import pytest
from PIL import Image

from app.core.listing_intel import embedder

pytestmark = pytest.mark.skipif(not embedder.available(), reason="model ONNX chua tai")


def solid(color):
    return Image.new("RGB", (300, 200), color)


def test_shapes_and_norm():
    v = embedder.embed_images([solid((255, 0, 0)), solid((0, 0, 255))])
    assert v.shape[0] == 2 and v.ndim == 2 and v.dtype == np.float32
    assert np.allclose(np.linalg.norm(v, axis=1), 1, atol=1e-3)


def test_text_image_alignment():
    img = embedder.embed_images([solid((255, 0, 0))])[0]
    red, green = embedder.embed_texts(["một bức ảnh màu đỏ", "một bức ảnh màu xanh lá"])
    assert img @ red > img @ green


def test_padding_fixed_64():
    assert len(embedder._tokenizer().encode("x").ids) == 64
    assert len(embedder._tokenizer().encode("áo thun nam cotton " * 30).ids) == 64
    v = embedder.embed_texts(["áo thun nam cotton " * 30])
    assert v.shape[0] == 1
    assert np.allclose(np.linalg.norm(v, axis=1), 1, atol=1e-3)


def test_batches_over_16_and_latency():
    imgs = [solid((i * 15, 100, 200 - i * 10)) for i in range(16)]
    embedder.embed_images(imgs[:1])
    t = time.perf_counter()
    v = embedder.embed_images(imgs)
    print(f"\n16 anh: {time.perf_counter() - t:.2f}s")
    assert v.shape[0] == 16
    assert embedder.embed_images(imgs + imgs[:2]).shape[0] == 18


def test_empty_inputs_keep_dim():
    for v in (embedder.embed_images([]), embedder.embed_texts([])):
        assert v.shape == (0, 768) and v.dtype == np.float32


def test_nfc_nfd_same_vector():
    a, b = (
        embedder.embed_texts([unicodedata.normalize(f, "Áo dài Việt Nam")])[0]
        for f in ("NFC", "NFD")
    )
    assert a @ b > 0.999


def test_transparent_images_composite_on_white():
    white = embedder.embed_images([solid((255, 255, 255))])[0]
    pal = Image.new("P", (300, 200), 0)
    pal.info["transparency"] = 0
    clear = [
        Image.new("RGBA", (300, 200), (255, 0, 0, 0)),
        Image.new("LA", (300, 200), (0, 0)),
        pal,
    ]
    for v in embedder.embed_images(clear):
        assert v @ white > 0.999


def test_cold_start_loads_each_model_once(monkeypatch):
    real = embedder.ort.InferenceSession
    loads = Counter()

    def counting(path, *a, **k):
        loads[path.rsplit("/", 1)[-1]] += 1
        return real(path, *a, **k)

    monkeypatch.setattr(embedder.ort, "InferenceSession", counting)
    monkeypatch.setattr(embedder, "_cache", {})
    img = [solid((9, 9, 9))]
    jobs = [lambda: embedder.embed_texts(["áo"]), lambda: embedder.embed_images(img)] * 4
    threads = [threading.Thread(target=j) for j in jobs]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert loads == {"text_model_int8.onnx": 1, "vision_model_int8.onnx": 1}


def test_image_embedding_is_batch_invariant():
    rng = np.random.default_rng(1)
    imgs = [Image.fromarray(rng.integers(0, 255, (90, 120, 3), dtype=np.uint8)) for _ in range(16)]
    alone = embedder.embed_images(imgs[:1])[0]
    batched = embedder.embed_images(imgs)[0]
    assert alone @ batched > 0.9999


def test_text_embedding_is_batch_invariant():
    texts = [f"áo thun nam cotton mẫu {i} form rộng" for i in range(32)]
    alone = embedder.embed_texts(texts[:1])[0]
    batched = embedder.embed_texts(texts)[0]
    assert alone @ batched > 0.9999
