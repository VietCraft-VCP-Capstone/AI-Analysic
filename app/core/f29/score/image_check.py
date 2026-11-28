from concurrent.futures import ThreadPoolExecutor, wait

from app.core.f29.score.scoring import normalize_image
from app.core.f29.shared.vision import dhash, flatten, hamming, quality, quality_issues

BUDGET_S = 1.5
DUP_HAMMING = 5
THREADS = 4


def counts_as_useful(row: dict) -> bool:
    return not row.get("duplicate") and not row.get("issues")


def unique(urls):
    first = {}
    for url in urls:
        first.setdefault(normalize_image(url), url)
    first.pop("", None)
    return list(first.values())


def item_of(img, vec) -> dict | None:
    if img is None:
        return None
    rgb = flatten(img)
    return {"vec": vec, "display": quality(rgb), "dhash": format(dhash(rgb), "016x")}


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


def _row(url, item, hashes):
    row = {"url": url, "duplicate": False, "issues": []}
    if item is None:
        return row
    h = int(item["dhash"], 16)
    row["duplicate"] = any(hamming(h, o) <= DUP_HAMMING for o in hashes)
    hashes.append(h)
    row["issues"] = [i["code"] for i in quality_issues(item["display"])]
    return row


def analyze(urls: list[str], fetch, budget: float = BUDGET_S) -> dict:
    uniq = unique(urls)
    if not uniq:
        return {"state": "seller_missing", "useful": 0, "images": [], "method": "heuristic"}
    loaded = _fetch_all(uniq, fetch, budget)
    hashes: list[int] = []
    images = [_row(url, item, hashes) for url, item in zip(uniq, loaded)]
    done = [item for item in loaded if item is not None]
    useful = sum(counts_as_useful(r) for r in images)
    return {
        "state": "scored" if done else "technical_failure",
        "useful": useful,
        "unanalyzed": len(loaded) - len(done),
        "images": images,
        "method": "ml_unvalidated" if any(item["vec"] is not None for item in done) else "heuristic",
    }
