import io
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from PIL import Image

from . import embedder, image_fetch, store
from .vision import dhash, quality

TRAIN_SIDE = 256
TRAIN_QUALITY = 85
THREADS = 4


def as_trained(img: Image.Image) -> Image.Image:
    small = img.copy()
    small.thumbnail((TRAIN_SIDE, TRAIN_SIDE))
    buf = io.BytesIO()
    small.convert("RGB").save(buf, "JPEG", quality=TRAIN_QUALITY)
    buf.seek(0)
    with Image.open(buf) as im:
        return im.convert("RGB")


def _compute(url: str, save: bool):
    img = image_fetch.fetch(url)
    if img is None:
        return None
    small = as_trained(img)
    vec = embedder.embed_images([small])[0] if embedder.available() else None
    metrics = {"model": quality(small), "display": quality(img), "dhash": format(dhash(img), "016x")}
    if vec is None:
        return {"vec": None, **metrics}
    vec = np.asarray(vec, dtype=np.float16).astype(np.float32)
    if save:
        store.put_embedding(url, vec, metrics)
    return {"vec": vec, **metrics}


_MEMORY: dict = {}
MEMORY_MAX = 2000


def load(url: str, save: bool = True):
    if url in _MEMORY:
        return _MEMORY[url]
    hit = store.get_embedding(url)
    item = {"vec": hit[0], **hit[1]} if hit is not None else _compute(url, save)
    if item is not None:
        if len(_MEMORY) >= MEMORY_MAX:
            _MEMORY.clear()
        _MEMORY[url] = item
    return item


def load_all(urls: list[str], save: bool = True) -> list:
    if not urls:
        return []
    with ThreadPoolExecutor(min(THREADS, len(urls))) as pool:
        return list(pool.map(lambda u: load(u, save), urls))
