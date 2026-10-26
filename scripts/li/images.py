import hashlib
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from app.core.listing_intel.image_fetch import fetch
from scripts.li import paths

LONG_SIDE = 256
QUALITY = 85
THREADS = 8
MAX_FAIL = 0.2
MIN_PROBE = 50


def image_file(url: str):
    folder = paths.DATA_DIR / "images"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{hashlib.sha1(url.encode()).hexdigest()}.jpg"


def _download(url: str) -> bool:
    img = fetch(url)
    if img is None:
        return False
    img.thumbnail((LONG_SIDE, LONG_SIDE))
    dst = image_file(url)
    tmp = dst.with_suffix(".part")
    img.save(tmp, "JPEG", quality=QUALITY)
    tmp.replace(dst)
    return True


def all_urls() -> list[str]:
    frames = [pd.read_parquet(paths.clean(f"{n}.parquet"), columns=["image_url"]) for n in ("tiki26", "tikifashion")]
    return list(dict.fromkeys(pd.concat(frames)["image_url"].dropna()))


def main() -> None:
    urls = all_urls()
    todo = [u for u in urls if not image_file(u).exists()]
    done = failed = 0
    with ThreadPoolExecutor(THREADS) as pool:
        for ok in pool.map(_download, todo):
            done += 1
            failed += not ok
            if done >= MIN_PROBE and failed / done > MAX_FAIL:
                pool.shutdown(cancel_futures=True)
                raise SystemExit(f"Stopped: {failed}/{done} downloads failed (> {MAX_FAIL:.0%})")
    rate = failed / done if done else 0.0
    print(f"images: {len(urls)} urls, {len(urls) - len(todo)} cached, {done} fetched, {failed} failed ({rate:.1%}); "
          f"missing overall {failed}/{len(urls)} ({failed / max(len(urls), 1):.2%})")


if __name__ == "__main__":
    main()
