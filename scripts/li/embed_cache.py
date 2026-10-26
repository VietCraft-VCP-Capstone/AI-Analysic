import numpy as np
import pandas as pd
from PIL import Image

from app.core.listing_intel.embedder import EMBED_DIM, embed_images, embed_texts
from app.core.listing_intel.vision import quality
from scripts.li import paths
from scripts.li.images import image_file

CHUNK = 256


def features_dir():
    folder = paths.DATA_DIR / "features"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def as_f16(m) -> np.ndarray:
    return np.asarray(m, dtype=np.float16).astype(np.float32)


def load_image(url):
    if not isinstance(url, str) or not image_file(url).exists():
        return None
    with Image.open(image_file(url)) as im:
        return im.convert("RGB")


def has_image(urls) -> np.ndarray:
    return np.array([isinstance(u, str) and image_file(u).exists() for u in urls], dtype=bool)


def embed_urls(urls: list) -> np.ndarray:
    vecs = np.full((len(urls), EMBED_DIM), np.nan, np.float32)
    for start in range(0, len(urls), CHUNK):
        part = [(i, load_image(u)) for i, u in enumerate(urls[start:start + CHUNK], start)]
        part = [(i, im) for i, im in part if im is not None]
        if part:
            idx, ims = zip(*part)
            vecs[list(idx)] = embed_images(list(ims))
    return vecs


def qualities(urls: list) -> list:
    return [None if (im := load_image(u)) is None else quality(im) for u in urls]


def _fresh(path, ids, src, has) -> bool:
    if not path.exists():
        return False
    z = np.load(path)
    same = np.array_equal(z["listing_id"], ids) and np.array_equal(z["source"], src)
    return same and np.array_equal(~np.isnan(z["img"][:, 0]), has)


def embeddings(df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    path = features_dir() / "emb.npz"
    ids, src, urls = df["listing_id"].to_numpy(), df["source"].to_numpy(str), df["image_url"].tolist()
    if not _fresh(path, ids, src, has_image(urls)):
        txt = embed_texts(df["title"].tolist()).astype(np.float16)
        img = embed_urls(urls).astype(np.float16)
        np.savez_compressed(path, listing_id=ids, source=src, txt=txt, img=img)
    z = np.load(path)
    return as_f16(z["txt"]), as_f16(z["img"])


def tikifashion() -> None:
    path = features_dir() / "emb_tikifashion.npz"
    if path.exists():
        return
    df = pd.read_parquet(paths.clean("tikifashion.parquet"))
    img = embed_urls(df["image_url"].tolist())
    ok = ~np.isnan(img[:, 0])
    txt = embed_texts(df.loc[ok, "caption"].tolist())
    np.savez_compressed(path, listing_id=df["listing_id"].to_numpy()[ok], img=img[ok], txt=txt,
                        category=df.loc[ok, "category"].to_numpy(str))
    print(f"emb_tikifashion: {int(ok.sum())}/{len(df)} with image")
