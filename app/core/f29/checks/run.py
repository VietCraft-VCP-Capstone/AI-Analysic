import hashlib
import io
import json
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, wait
from functools import cache

import numpy as np
from PIL import Image, ImageOps
from bson import ObjectId

from app.api.v1._mart import client_dung_chung
from app.core.f29.score import image_check
from app.core.f29 import constants
from app.core.f29.score import factors
from app.core.f29.checks import describe, duplicates, image_match, make_check, print_check
from app.core.f29.checks.duplicates import fingerprint
from app.core.f29.paths import MODELS
from app.core.f29.shared import embedder, image_fetch, image_load, vision


THREADS = 4
TIMEOUT = 5
MAX_BYTES = 8_000_000


def rgba(url: str):
    try:
        if not image_fetch.allowed(url):
            return None
        deadline = time.monotonic() + TIMEOUT
        req = urllib.request.Request(url, headers={"User-Agent": image_fetch.USER_AGENT, "Accept": "image/*"})
        with image_fetch._open(req, TIMEOUT) as resp:
            if not image_fetch.allowed(resp.geturl()):
                return None
            if not resp.headers.get("Content-Type", "").lower().startswith("image/"):
                return None
            length = resp.headers.get("Content-Length")
            if length is not None and int(length) > MAX_BYTES:
                return None
            data = image_fetch._read_capped(resp, MAX_BYTES, deadline)
        if data is None:
            return None
        img = Image.open(io.BytesIO(data))
        if img.width * img.height > image_fetch.MAX_PIXELS:
            return None
        return ImageOps.exif_transpose(img)
    except Exception as e:
        print(f"[f29_checks] rgba {type(e).__name__}: {e}", flush=True)
        return None


def embed(img):
    try:
        if img is None or not embedder.available():
            return None
        return embedder.embed_images([image_load.as_trained(vision.flatten(img))])[0]
    except Exception as e:
        print(f"[f29_checks] embed {type(e).__name__}: {e}", flush=True)
        return None


def _task(url: str, with_vec: bool):
    img = rgba(url)
    return img, (embed(img) if with_vec else None)


def fetch_all(urls: list[str], budget: float, vec_urls: frozenset = frozenset()) -> dict:
    pool = ThreadPoolExecutor(max_workers=THREADS)
    futures = {u: pool.submit(_task, u, u in vec_urls) for u in urls}
    wait(list(futures.values()), timeout=budget)
    pool.shutdown(wait=False, cancel_futures=True)
    return {u: f.result() if f.done() and not f.cancelled() else (None, None) for u, f in futures.items()}


def txt(title: str | None):
    try:
        return embedder.embed_texts([title])[0] if title and embedder.available() else None
    except Exception as e:
        print(f"[f29_checks] txt {type(e).__name__}: {e}", flush=True)
        return None


IMAGE_FLAGS = ("duplicate_same_shop", "image_match")


def _live(checks: list[dict]) -> list[dict]:
    return [c for c in checks if c.get("mode", "live") == "live"]


def _flagged(checks: list[dict]) -> set[int]:
    out = set()
    for c in _live(checks):
        name, _, i = c.get("id", "").partition(":")
        if c.get("severity") == "warn" and name in IMAGE_FLAGS and i.isdigit():
            out.add(int(i))
    return out


def _image(row: dict, checks: list[dict]) -> dict:
    ev = row["evidence"]
    flagged = _flagged(checks)
    bad = sum(1 for i, img in enumerate(ev["images"]) if i in flagged and image_check.counts_as_useful(img))
    analysis = {"state": "scored", "useful": max(0, ev["useful"] - bad), "unanalyzed": ev["unanalyzed"],
                "images": ev["images"], "method": "ml_unvalidated" if ev["siglip"] else "heuristic"}
    return factors.image_row(analysis, ev["median"], ev["in_category"])


def apply(rows: list[dict], checks: list[dict]) -> list[dict]:
    return [_image(r, checks) if r["key"] == "image" and r["state"] == "scored" else r for r in rows]


DEFAULT_BUDGET = 25.0
THRESHOLDS = MODELS / "i_dupes" / "v1" / "thresholds.json"
ARTIFACTS = {"b1": "b1_type/v1", "b2": "b2_material/v1", "i": "i_dupes/v1", "im": image_match.VERSION}
NA_ACTION = "Chưa kiểm được mục này do lỗi hệ thống."


def versions() -> dict:
    return {**ARTIFACTS, "b3_attr": describe.version()}


@cache
def stamp() -> str:
    h = hashlib.md5()
    for p in sorted(p for p in MODELS.rglob("*") if p.is_file() and p.suffix != ".md"):
        h.update(p.relative_to(MODELS).as_posix().encode())
        h.update(p.read_bytes())
    return h.hexdigest()


def _safe(name: str, pillar: str, fn) -> list[dict]:
    try:
        return fn()
    except Exception as e:
        print(f"[f29_checks] {name}: {e}", flush=True)
        return [make_check(f"{name}:error", pillar, "na", {"error": type(e).__name__}, NA_ACTION, confidence=0.0)]


def _plain(checks: list[dict]) -> list[dict]:
    return json.loads(json.dumps(checks, default=lambda o: o.item() if hasattr(o, "item") else str(o)))


def _designs(live_db, product: dict) -> dict:
    ids = {str(layer["design_id"]) for p in product.get("design_placements") or []
           for layer in p.get("layers") or [] if layer.get("design_id")}
    oids = [ObjectId(i) for i in ids if ObjectId.is_valid(i)]
    if not oids:
        return {}
    return {str(d["_id"]): d for d in live_db["product_designs"].find({"_id": {"$in": oids}})}


def _print(product: dict, designs: dict, imgs: dict) -> list[dict]:
    if not product.get("design_placements"):
        return []
    blank = None
    if product.get("blank_id"):
        blank = client_dung_chung()["printing"]["blanks"].find_one({"_id": ObjectId(product["blank_id"])})
    return print_check.check_product(product, designs, blank, imgs.get)


def _mean(vecs: list) -> np.ndarray | None:
    vs = [np.asarray(v, dtype=float) for v in vecs if v is not None]
    if not vs:
        return None
    m = np.mean(vs, axis=0)
    return m / max(float(np.linalg.norm(m)), 1e-12)


def _duplicates(product: dict, image_urls: list[str], imgs: dict, vecs: list, index: bool) -> list[dict]:
    db = constants.store_db()
    images = [(u, imgs.get(u)) for u in image_urls]
    checks = duplicates.check_product(db, product, images, vecs, json.loads(THRESHOLDS.read_text("utf-8")))
    items = [(u, "product", fingerprint(img), v) for (u, img), v in zip(images, vecs) if img is not None]
    if index:
        duplicates.index_images(db, product, items, keep_urls=image_urls)
    return checks


def _checks(product: dict, variants: list, live_db, image_urls: list[str], image_budget: float,
            preloaded: dict, index: bool) -> list[dict]:
    designs = _designs(live_db, product)
    design_urls = [d["file_url"] for d in designs.values() if d.get("file_url")]
    want = [u for u in dict.fromkeys([*image_urls, *design_urls]) if u not in preloaded]
    loaded = {**preloaded, **(fetch_all(want, image_budget, frozenset(image_urls)) if want else {})}
    imgs = {u: p[0] for u, p in loaded.items()}
    vecs = [loaded.get(u, (None, None))[1] for u in image_urls]
    colors = [v["color"] for v in variants if v.get("is_active") and v.get("color")]
    title_vec = txt(product.get("title"))
    checks = [
        *_safe("print", "print", lambda: _print({**product, "active_colors": colors}, designs, imgs)),
        *_safe("describe", "description",
               lambda: describe.check_listing(product, _mean(vecs), title_vec, vecs)),
        *_safe("image_match", "image", lambda: image_match.image_checks(vecs, title_vec)),
        *_safe("duplicates", "duplicate", lambda: _duplicates(product, image_urls, imgs, vecs, index)),
    ]
    return _plain(checks)


def collect(product: dict, variants: list, live_db, image_urls: list[str],
            image_budget: float = DEFAULT_BUDGET, loaded: dict | None = None,
            index: bool = True) -> tuple[list[dict], dict]:
    try:
        checks = _checks(product, variants, live_db, image_urls, image_budget, loaded or {}, index)
    except Exception as e:
        print(f"[f29_checks] collect {type(e).__name__}: {e}", flush=True)
        err = make_check("checks:error", "image", "na", {"error": type(e).__name__},
                         "Chưa kiểm được, thử lại sau.", confidence=0.0)
        return [err], {}
    return checks, versions()
