"""Tách phôi khỏi nền ảnh (salient object segmentation) bằng BiRefNet-lite qua ONNX.

Dùng cho mockup POD: biết chính xác pixel nào là phôi thì mới đổi màu phôi được mà không
tô nhầm nền nhiều màu hay bóng đổ. Model tách vật thể nổi bật, bóng đổ dưới phôi nằm ngoài mask.

Giấy phép: BiRefNet (MIT). Không dùng BRIA RMBG vì cấm thương mại.
Model tải một lần về SEG_MODEL_DIR (mặc định ~/.cache/vietcraft-seg) bằng scripts/seg/fetch_model.py.
"""

from __future__ import annotations

import io
import os
import threading
from pathlib import Path

import numpy as np
from PIL import Image

# name -> (file, input size, mean, std, sigmoid?)
MODELS = {
    "birefnet-general-lite": (
        "birefnet-general-lite.onnx", 1024, (0.485, 0.456, 0.406), (0.229, 0.224, 0.225), True,
    ),
    "isnet-general-use": (
        "isnet-general-use.onnx", 1024, (0.5, 0.5, 0.5), (1.0, 1.0, 1.0), False,
    ),
}
MODEL_NAME = os.environ.get("SEG_MODEL", "birefnet-general-lite")
MODEL_DIR = Path(os.environ.get("SEG_MODEL_DIR") or "~/.cache/vietcraft-seg").expanduser()
MAX_SIDE = 4096

_lock = threading.Lock()
_session = None


def _spec():
    if MODEL_NAME not in MODELS:
        raise RuntimeError(f"SEG_MODEL không hỗ trợ: {MODEL_NAME}")
    return MODELS[MODEL_NAME]


def model_path() -> Path:
    return MODEL_DIR / _spec()[0]


def available() -> bool:
    return model_path().exists()


def _get_session():
    global _session
    if _session is None:
        with _lock:
            if _session is None:
                import onnxruntime as ort

                opts = ort.SessionOptions()
                opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
                _session = ort.InferenceSession(str(model_path()), opts, providers=["CPUExecutionProvider"])
    return _session


def _flatten_alpha(img: Image.Image) -> Image.Image:
    """Ảnh PNG trong suốt: đặt lên nền trắng để model thấy giống ảnh chụp."""
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        rgba = img.convert("RGBA")
        bg = Image.new("RGB", rgba.size, (255, 255, 255))
        bg.paste(rgba, mask=rgba.split()[3])
        return bg
    return img.convert("RGB")


def predict_mask(image: Image.Image) -> Image.Image:
    """Trả về mask xám (L) cùng kích thước ảnh: 255 = phôi, 0 = nền."""
    _, size, mean, std, use_sigmoid = _spec()
    rgb = _flatten_alpha(image)
    w, h = rgb.size

    x = np.asarray(rgb.resize((size, size), Image.BILINEAR), dtype=np.float32) / 255.0
    x = (x - np.array(mean, dtype=np.float32)) / np.array(std, dtype=np.float32)
    x = x.transpose(2, 0, 1)[None, ...].astype(np.float32)

    sess = _get_session()
    out = sess.run(None, {sess.get_inputs()[0].name: x})[0]
    pred = out[0, 0] if out.ndim == 4 else out[0]
    if use_sigmoid:
        pred = 1.0 / (1.0 + np.exp(-pred))
    lo, hi = float(pred.min()), float(pred.max())
    pred = (pred - lo) / (hi - lo) if hi - lo > 1e-6 else np.zeros_like(pred)

    mask = Image.fromarray((pred * 255).clip(0, 255).astype(np.uint8), mode="L")
    return mask.resize((w, h), Image.BILINEAR)


def segment_bytes(data: bytes) -> tuple[bytes, float]:
    """Ảnh (bytes) -> (PNG mask bytes, tỉ lệ diện tích phôi 0..1)."""
    img = Image.open(io.BytesIO(data))
    img.load()
    if max(img.size) > MAX_SIDE:
        img.thumbnail((MAX_SIDE, MAX_SIDE))
    mask = predict_mask(img)
    coverage = float((np.asarray(mask) > 127).mean())
    buf = io.BytesIO()
    mask.save(buf, format="PNG", optimize=True)
    return buf.getvalue(), coverage
