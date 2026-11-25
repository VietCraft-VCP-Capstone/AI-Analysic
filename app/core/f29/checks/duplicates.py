import hashlib
from urllib.parse import urlparse

import numpy as np
from PIL import Image, ImageOps
from scipy.fft import dctn

from app.core.f29.checks import make_check
from app.core.f29.shared.vision import dhash, hamming


WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
HASH_SIDE = 32
DCT_KEEP = 8
BLANK_SHARE = 0.98
CROP_MARGIN = 0.1


def _has_alpha(img: Image.Image) -> bool:
    return "A" in img.getbands() or "transparency" in img.info


def _rgba(img: Image.Image) -> Image.Image:
    return ImageOps.exif_transpose(img).convert("RGBA")


def _render(img: Image.Image, bg: tuple) -> Image.Image:
    rgba = _rgba(img)
    return Image.alpha_composite(Image.new("RGBA", rgba.size, (*bg, 255)), rgba).convert("RGB")


def _mostly_white(img: Image.Image, white: Image.Image) -> bool:
    opaque = np.asarray(_rgba(img))[..., 3] > 0
    if not opaque.any():
        return False
    return (np.asarray(white.convert("L"))[opaque] > 245).mean() >= BLANK_SHARE


def _hash_base(img: Image.Image) -> Image.Image:
    white = _render(img, WHITE)
    if _has_alpha(img) and _mostly_white(img, white):
        return _render(img, BLACK)
    return white


def content_sha(img: Image.Image) -> str:
    rgb = _render(img, WHITE)
    return hashlib.sha256(f"{rgb.size}".encode() + rgb.tobytes()).hexdigest()


def _phash_of(rgb: Image.Image) -> int:
    g = np.asarray(rgb.convert("L").resize((HASH_SIDE, HASH_SIDE), Image.Resampling.LANCZOS), dtype=float)
    low = dctn(g, norm="ortho")[:DCT_KEEP, :DCT_KEEP].ravel()
    return int("".join("1" if b else "0" for b in low > np.median(low[1:])), 2)


def _phash_crop(base: Image.Image) -> int:
    w, h = base.size
    m = CROP_MARGIN
    return _phash_of(base.crop((int(w * m), int(h * m), int(w * (1 - m)), int(h * (1 - m)))))


def fingerprint(img: Image.Image) -> dict:
    base = _hash_base(img)
    return {"sha": content_sha(img), "phash": _phash_of(base), "phash_flip": _phash_of(ImageOps.mirror(base)),
            "phash_crop": _phash_crop(base), "dhash": dhash(base)}


INDEX = "f29_image_index"
CLOUDINARY = "res.cloudinary.com"
HASH_KEYS = ("phash", "phash_flip", "phash_crop")
ROW_HASH = ("phash", "phash_crop")
ACTIONS = {
    "external": "Ảnh lấy từ {host}. Hãy tải ảnh do shop tự chụp hoặc tự thiết kế.",
    "same": "Ảnh này đang dùng cho sản phẩm khác của chính shop.",
    "same_similar": "Ảnh này gần giống ảnh khác của chính shop. Kiểm tra lại nếu là cùng một sản phẩm.",
    "other": "Ảnh này cũng xuất hiện ở shop khác. Chỉ để tham khảo.",
}


def external_host(url: str) -> str | None:
    host = urlparse(url).hostname
    return None if host in (None, CLOUDINARY) else host


def _pid(product: dict) -> str:
    return str(product["_id"])


def _hex(h: int) -> str:
    return format(h, "016x")


def _vec(vec) -> bytes | None:
    return None if vec is None else np.asarray(vec, dtype=np.float16).tobytes()


def _decode(v) -> np.ndarray:
    if isinstance(v, (bytes, bytearray)):
        return np.frombuffer(v, dtype=np.float16).astype(float)
    return np.asarray(v, dtype=float)


def as_row(fp: dict, vec) -> dict:
    row = {"content_sha": fp["sha"], "vec": _vec(vec)}
    return row | {k: _hex(fp[k]) for k in (*HASH_KEYS, "dhash")}


def index_images(db, product: dict, items: list[tuple], keep_urls: list[str] | None = None) -> None:
    pid = _pid(product)
    keep = keep_urls if keep_urls is not None else [item[0] for item in items]
    db[INDEX].delete_many({"product_id": pid, "url": {"$nin": keep}})
    for url, kind, fp, vec in items:
        if fp is None:
            continue
        doc = {**as_row(fp, vec), "product_id": pid, "url": url,
               "shop_id": str(product["shop_id"]), "kind": kind}
        db[INDEX].update_one({"product_id": pid, "url": url}, {"$set": doc}, upsert=True)


def _cos(a, b) -> float | None:
    if a is None or b is None:
        return None
    a, b = _decode(a), _decode(b)
    return float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b)))


def pix_hd(fp: dict, row: dict) -> int:
    return min(hamming(fp[k], int(row[r], 16)) for k in HASH_KEYS for r in ROW_HASH)


def match_level(fp: dict, vec, row: dict, th: dict) -> str | None:
    if fp["sha"] == row["content_sha"]:
        return "exact"
    if pix_hd(fp, row) <= th["h"]:
        return "near"
    cos = _cos(vec, row.get("vec"))
    if cos is not None and cos >= th["c"]:
        return "similar"
    return None


def find_matches(rows: list[dict], product: dict, fp: dict, vec, th: dict) -> list[dict]:
    shop = str(product["shop_id"])
    out = []
    for row in rows:
        level = match_level(fp, vec, row, th)
        if level:
            cos = _cos(vec, row.get("vec"))
            out.append({"product_id": row["product_id"], "same_shop": row["shop_id"] == shop, "level": level,
                        "cos": None if cos is None else round(cos, 4)})
    return out


def _match_checks(i: int, matches: list[dict]) -> list[dict]:
    same = [m for m in matches if m["same_shop"]]
    other = [m for m in matches if not m["same_shop"]]
    out = []
    if same:
        strong = any(m["level"] != "similar" for m in same)
        out.append(make_check(f"duplicate_same_shop:{i}", "duplicate", "warn" if strong else "info",
                              {"matches": same}, ACTIONS["same" if strong else "same_similar"]))
    if other:
        out.append(make_check(f"duplicate_other_shop:{i}", "duplicate", "info",
                              {"matches": other}, ACTIONS["other"]))
    return out


ROW_FIELDS = dict.fromkeys(("product_id", "shop_id", "content_sha", "vec", *ROW_HASH), 1)


def check_product(db, product: dict, images: list[tuple], vecs: list, th: dict) -> list[dict]:
    checks = []
    rows = list(db[INDEX].find({"product_id": {"$ne": _pid(product)}}, ROW_FIELDS)) \
        if any(img is not None for _, img in images) else []
    for i, (url, img) in enumerate(images):
        vec = vecs[i] if i < len(vecs) else None
        host = external_host(url)
        if host:
            checks.append(make_check(f"duplicate_external:{i}", "duplicate", "warn", {"host": host},
                                     ACTIONS["external"].format(host=host)))
        if img is not None:
            checks += _match_checks(i, find_matches(rows, product, fingerprint(img), vec, th))
    return checks
