import io
import json

import joblib
import numpy as np
import pandas as pd
from PIL import Image, ImageEnhance

from app.core.listing_intel import embedder
from app.core.listing_intel import features as F
from app.core.listing_intel.context import load_context
from app.core.listing_intel.image_load import as_trained
from app.core.listing_intel.types import ListingInput
from app.core.listing_intel.vision import dhash, hamming, quality
from scripts.li import paths
from scripts.li.embed_cache import load_image
from scripts.li.fit import axis_cols, predict
from scripts.li.reference import formula_values

N_IMAGES = 50
MAX_SHIFT = 5.0


def _jpeg(im, q=70):
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=q)
    buf.seek(0)
    return Image.open(buf).convert("RGB")


VARIANTS = {
    "sáng +10%": lambda im: ImageEnhance.Brightness(im).enhance(1.1),
    "tối -10%": lambda im: ImageEnhance.Brightness(im).enhance(0.9),
    "JPEG q70": _jpeg,
}


def percentile(dist, group, p):
    return float(np.interp(p, dist.get(f"image__{group}", dist["image__all"]), np.arange(101)))


def sample_rows(table):
    test = table[(table["source"] == "tiki26") & (table["split"] == "test") & table["image_url"].notna()]
    test = test[[load_image(u) is not None for u in test["image_url"]]]
    return test.sample(min(N_IMAGES, len(test)), random_state=42)


def features_for(rows, ims, title_vecs, ctx):
    ims = [as_trained(im) for im in ims]
    vecs = embedder.embed_images(ims)
    out = []
    for r, im, v, tv in zip(rows.itertuples(), ims, vecs, title_vecs):
        inp = ListingInput(title=r.title, group=r.group, price=r.price, image_urls=[r.image_url])
        out.append(F.assemble(inp, {**quality(im), "vec": v}, ctx, title_vec=tv))
    return pd.DataFrame(out, index=rows.index).assign(group=rows["group"])


def _pcts(dist, df, p):
    return np.array([percentile(dist, g, x) for g, x in zip(df["group"], p)])


def scorers(bundle_dir):
    model, cols = joblib.load(bundle_dir / "axis_image.joblib"), axis_cols("image")
    ref = bundle_dir / "reference"
    axis, form = dict(np.load(ref / "axis_dist.npz")), dict(np.load(ref / "formula_dist.npz"))
    return {"model": lambda df: _pcts(axis, df, predict(model, df, cols)),
            "formula": lambda df: _pcts(form, df, formula_values(df, "image"))}


def _shifts(pct):
    med = {n: round(float(np.median(np.abs(pct[n] - pct["gốc"]))), 2) for n in VARIANTS}
    return {"median_shift_pct": med, "pass": all(v <= MAX_SHIFT for v in med.values()),
            "p90_shift_pct": {n: round(float(np.percentile(np.abs(pct[n] - pct["gốc"]), 90)), 2) for n in VARIANTS}}


def run(table, bundle_dir):
    if not embedder.available():
        return None
    rows = sample_rows(table)
    z = np.load(paths.DATA_DIR / "features" / "emb.npz")
    pos = {(s, i): k for k, (s, i) in enumerate(zip(z["source"], z["listing_id"]))}
    txt = z["txt"]
    title_vecs = [txt[pos[("tiki26", i)]].astype(np.float32) for i in rows["listing_id"]]
    ctx = load_context(bundle_dir / "reference", trend_series={})
    meta = json.loads((bundle_dir / "meta.json").read_text("utf-8"))
    served = ((meta.get("axis_modes") or {}).get("image") or {}).get("mode", "model")
    base = [load_image(u) for u in rows["image_url"]]
    images = {"gốc": base} | {name: [f(im) for im in base] for name, f in VARIANTS.items()}
    feats = {name: features_for(rows, ims, title_vecs, ctx) for name, ims in images.items()}
    score = scorers(bundle_dir)
    by_mode = {m: _shifts({n: f(df) for n, df in feats.items()}) for m, f in score.items()}
    hashes = {n: [dhash(im) for im in ims] for n, ims in images.items()}
    dup = {n: float(np.median([hamming(a, b) for a, b in zip(hashes["gốc"], hashes[n])])) for n in VARIANTS}
    other = [hamming(a, b) for a, b in zip(hashes["gốc"], hashes["gốc"][1:] + hashes["gốc"][:1])]
    parity = np.abs(score[served](rows) - score[served](feats["gốc"]))
    return {
        "n": int(len(rows)), "max_shift": MAX_SHIFT, "served_mode": served, **by_mode[served], "by_mode": by_mode,
        "parity_median_abs_pct": round(float(np.median(parity)), 2),
        "dhash_median_hamming": dup, "dhash_median_hamming_other": float(np.median(other)),
    }
