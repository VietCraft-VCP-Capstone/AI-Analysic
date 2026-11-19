from concurrent.futures import ThreadPoolExecutor, wait
from functools import cache

import numpy as np

from app.core.f29.scoring import normalize_image
from app.core.listing_intel import image_load
from app.core.listing_intel.axes import DUP_HAMMING
from app.core.listing_intel.features import unit
from app.core.listing_intel.fusion import bundle_dir
from app.core.listing_intel.vision import hamming, quality_issues

BUDGET_S = 1.5
THREADS = 4


@cache
def _group_bank():
    z = np.load(bundle_dir() / "reference" / "prompt_vecs.npz")
    keys = [k for k in z.files if not k.startswith("style_")]
    return keys, np.stack([unit(z[k]) for k in keys])


def _category_match(vec, group):
    if vec is None:
        return None
    keys, bank = _group_bank()
    if group not in keys:
        return None
    return keys[int(np.argmax(bank @ unit(vec)))] == group


def _unique(urls):
    first = {}
    for url in urls:
        first.setdefault(normalize_image(url), url)
    first.pop("", None)
    return list(first.values())


def _safe(fetch, url):
    try:
        return fetch(url, save=False)
    except Exception:
        return None


def _fetch_all(urls, fetch, budget):
    pool = ThreadPoolExecutor(max_workers=THREADS)
    futures = [pool.submit(_safe, fetch, url) for url in urls]
    wait(futures, timeout=budget)
    pool.shutdown(wait=False, cancel_futures=True)
    return [f.result() if f.done() else None for f in futures]


def _row(url, item, hashes, group):
    row = {"url": url, "duplicate": False, "issues": [], "category_match": None}
    if item is None:
        return row
    h = int(item["dhash"], 16)
    row["duplicate"] = any(hamming(h, o) <= DUP_HAMMING for o in hashes)
    hashes.append(h)
    row["issues"] = [i["code"] for i in quality_issues(item["display"])]
    row["category_match"] = _category_match(item["vec"], group)
    return row


def analyze(urls: list[str], title: str, group: str | None, fetch=image_load.load,
            budget: float = BUDGET_S) -> dict:
    uniq = _unique(urls)
    if not uniq:
        return {"state": "seller_missing", "useful": 0, "images": [], "method": "heuristic"}
    loaded = _fetch_all(uniq, fetch, budget)
    hashes: list[int] = []
    images = [_row(url, item, hashes, group) for url, item in zip(uniq, loaded)]
    done = [item for item in loaded if item is not None]
    useful = sum(1 for r in images if not r["duplicate"] and not r["issues"])
    return {
        "state": "scored" if done else "technical_failure",
        "useful": useful,
        "unanalyzed": len(loaded) - len(done),
        "images": images,
        "method": "ml_unvalidated" if any(item["vec"] is not None for item in done) else "heuristic",
    }
