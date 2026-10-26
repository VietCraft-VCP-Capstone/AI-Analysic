import os
import threading
import unicodedata
from pathlib import Path

import numpy as np
import onnxruntime as ort
from PIL import Image
from tokenizers import Tokenizer

MODEL_ID = "onnx-community/siglip2-base-patch16-224-ONNX"
_LOCAL_DIR = Path(__file__).resolve().parents[4] / "ai-data-train-prod" / "models" / "siglip2-base-patch16-224"
MODEL_DIR = Path(
    os.environ.get("LI_MODEL_DIR") or (_LOCAL_DIR if _LOCAL_DIR.exists() else "~/.cache/vietcraft-li/siglip2-base-patch16-224")
).expanduser()
FILES = ("onnx/vision_model_int8.onnx", "onnx/text_model_int8.onnx", "tokenizer.json")
IMAGE_SIZE = 224
TEXT_LEN = 64
EMBED_DIM = 768

_lock = threading.Lock()
_cache: dict = {}


def available() -> bool:
    return all((MODEL_DIR / f).exists() for f in FILES)


def _cached(key: str, build):
    if key not in _cache:
        with _lock:
            if key not in _cache:
                _cache[key] = build()
    return _cache[key]


def _session(name: str) -> ort.InferenceSession:
    return _cached(
        name,
        lambda: ort.InferenceSession(
            str(MODEL_DIR / f"onnx/{name}_model_int8.onnx"),
            providers=["CPUExecutionProvider"],
        ),
    )


def _tokenizer() -> Tokenizer:
    def build():
        tok = Tokenizer.from_file(str(MODEL_DIR / "tokenizer.json"))
        tok.enable_padding(length=TEXT_LEN, pad_id=0, pad_token="<pad>")
        tok.enable_truncation(TEXT_LEN)
        return tok

    return _cached("tokenizer", build)


def _pooled(name: str, feed: dict) -> np.ndarray:
    sess = _session(name)
    names = [o.name for o in sess.get_outputs()]
    outs = dict(zip(names, sess.run(None, feed)))
    out = outs.get("pooler_output")
    if out is None:
        out = next(o for o in outs.values() if o.ndim == 2)
    out = out.astype(np.float32)
    return out / np.maximum(np.linalg.norm(out, axis=1, keepdims=True), 1e-12)


def _rgb(img: Image.Image) -> Image.Image:
    if img.mode in ("RGBA", "LA", "PA") or "transparency" in img.info:
        rgba = img.convert("RGBA")
        white = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        return Image.alpha_composite(white, rgba).convert("RGB")
    return img.convert("RGB")


def _prep(img: Image.Image) -> np.ndarray:
    img = _rgb(img).resize((IMAGE_SIZE, IMAGE_SIZE), Image.BILINEAR)
    arr = np.asarray(img, dtype=np.float32) / 255.0
    return ((arr - 0.5) / 0.5).transpose(2, 0, 1)


def _each(items: list, fn) -> np.ndarray:
    if not items:
        return np.zeros((0, EMBED_DIM), dtype=np.float32)
    return np.concatenate([fn(x) for x in items])


def embed_images(images: list[Image.Image]) -> np.ndarray:
    return _each(images, lambda i: _pooled("vision", {"pixel_values": _prep(i)[None]}))


def embed_texts(texts: list[str]) -> np.ndarray:
    def run(text):
        ids = _tokenizer().encode(unicodedata.normalize("NFC", text).lower()).ids
        return _pooled("text", {"input_ids": np.array([ids], dtype=np.int64)})

    return _each(texts, run)
