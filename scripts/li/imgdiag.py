import joblib
import numpy as np
import pandas as pd

from app.core.listing_intel import embedder
from app.core.listing_intel import features as F
from app.core.listing_intel.context import load_context
from app.core.listing_intel.types import ListingInput
from app.core.listing_intel.vision import quality
from scripts.li import imgcheck, paths
from scripts.li.embed_cache import load_image
from scripts.li.fit import axis_cols, predict


def one_by_one(ims):
    return np.stack([embedder.embed_images([im])[0] for im in ims])


def _med(v):
    return round(float(np.median(v)), 4)


class _Scorer:
    def __init__(self, rows, bundle_dir):
        z = np.load(paths.DATA_DIR / "features" / "emb.npz")
        pos = {(s, i): k for k, (s, i) in enumerate(zip(z["source"], z["listing_id"]))}
        keys = [pos[("tiki26", i)] for i in rows["listing_id"]]
        self.rows, self.title, self.stored = rows, z["txt"][keys].astype(np.float32), z["img"][keys].astype(np.float32)
        self.ctx = load_context(bundle_dir / "reference", trend_series={})
        self.model = joblib.load(bundle_dir / "axis_image.joblib")
        self.dist = dict(np.load(bundle_dir / "reference" / "axis_dist.npz"))

    def pct(self, quals, vecs):
        feats = []
        for r, q, v, t in zip(self.rows.itertuples(), quals, vecs, self.title):
            inp = ListingInput(title=r.title, group=r.group, price=r.price, image_urls=[r.image_url])
            feats.append(F.assemble(inp, {**q, "vec": v}, self.ctx, title_vec=t))
        df = pd.DataFrame(feats, index=self.rows.index).assign(group=self.rows["group"])
        p = predict(self.model, df, axis_cols("image"))
        return np.array([imgcheck.percentile(self.dist, g, x) for g, x in zip(self.rows["group"], p)])


def run(table, bundle_dir):
    if not embedder.available():
        return None
    rows = imgcheck.sample_rows(table)
    sc = _Scorer(rows, bundle_dir)
    base = [load_image(u) for u in rows["image_url"]]
    qb, vb = [quality(im) for im in base], one_by_one(base)
    batch = embedder.embed_images(base)
    p0 = sc.pct(qb, vb)
    out = {"n": int(len(rows)), "cos_single_vs_batch": {"median": _med((vb * batch).sum(1)),
                                                        "min": round(float((vb * batch).sum(1).min()), 4)},
           "cos_single_vs_table": _med((vb * sc.stored).sum(1)), "variants": {}}
    for name, f in imgcheck.VARIANTS.items():
        ims = [f(im) for im in base]
        qv, vv = [quality(im) for im in ims], one_by_one(ims)
        out["variants"][name] = {"cos_embedding": _med((vb * vv).sum(1)),
                                 "shift_only_quality": round(float(np.median(np.abs(sc.pct(qv, vb) - p0))), 2),
                                 "shift_only_embedding": round(float(np.median(np.abs(sc.pct(qb, vv) - p0))), 2),
                                 "shift_both": round(float(np.median(np.abs(sc.pct(qv, vv) - p0))), 2)}
    return out
