import json
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

from app.core.listing_intel.normalize import fold
from app.core.listing_intel.trend_store import weekly_series
from scripts.li import paths

BANDS = [0.80, 0.85, 0.88, 0.90, 0.92, 1.01]
PER_BAND = 20
GENERIC_DF = 3
FEATURES = paths.DATA_DIR / "features"
SAMPLE = FEATURES / "trend_calib_sample.csv"
JUDGED = Path("app/core/listing_intel/model/reference/trend_calib_judged.json")
ROOT = Path(__file__).resolve().parents[2]


def judged():
    path = ROOT / JUDGED
    if not path.exists():
        return None
    pairs = pd.DataFrame(json.loads(path.read_text("utf-8"))["pairs"])
    by = pairs.groupby("band")[["strict", "lenient"]].agg(["sum", "size"])
    return {"file": str(JUDGED), "n": int(len(pairs)), "strict": int(pairs["strict"].sum()),
            "lenient": int(pairs["lenient"].sum()),
            "by_band": {b: {"n": int(r[("strict", "size")]), "strict": int(r[("strict", "sum")]),
                            "lenient": int(r[("lenient", "sum")])} for b, r in by.iterrows()}}


def _unit(m):
    m = np.asarray(m, np.float32)
    return m / np.linalg.norm(m, axis=1, keepdims=True)


def _inputs():
    z = dict(np.load(FEATURES / "emb.npz"))
    kw = np.load(FEATURES / "context" / "trend_kw_vecs.npz")
    series = weekly_series()
    names = kw["keywords"].tolist()
    kws = [k for k in names if k in series]
    vecs = _unit(np.stack([kw["vecs"][names.index(k)] for k in kws]))
    t26 = pd.read_parquet(paths.clean("tiki26.parquet"))
    pos = {i: n for n, (s, i) in enumerate(zip(z["source"], z["listing_id"])) if s == "tiki26"}
    txt = _unit(z["txt"][[pos[i] for i in t26["listing_id"]]])
    return t26["title"].fillna("").astype(str).tolist(), kws, txt @ vecs.T


def run(seed=0):
    titles, kws, cos = _inputs()
    df = Counter(t for k in kws for t in set(fold(k).split()))
    generic = {t for t, n in df.items() if n >= GENERIC_DF}
    words = [set(fold(t).split()) for t in titles]
    lex = np.array([[f" {fold(k)} " in f" {fold(t)} " for k in kws] for t in titles])
    share = np.array([[bool((set(fold(k).split()) - generic) & w) for k in kws] for w in words])
    free = ~lex.any(1)
    out = {"n_titles": len(titles), "n_keywords": len(kws), "literal_rows": round(float(lex.any(1).mean()), 3),
           "cos_quantiles": dict(zip(("p50", "p90", "p99"), np.quantile(cos, [0.5, 0.9, 0.99]).round(3).tolist())),
           "generic_tokens": sorted(generic), "thresholds": {}}
    for th in BANDS[:-1]:
        hit = (cos >= th) & free[:, None]
        out["thresholds"][str(th)] = {"rows_vector_only": round(float(hit.any(1).mean()), 3),
                                      "rows_vector_overlap": round(float((hit & share).any(1).mean()), 3),
                                      "mean_matches": round(float(hit.sum(1)[hit.any(1)].mean()), 2) if hit.any() else 0}
    i, j = np.nonzero((cos >= BANDS[0]) & free[:, None])
    pairs = pd.DataFrame({"title": [titles[a] for a in i], "keyword": [kws[b] for b in j],
                          "cos": cos[i, j].round(3), "overlap": share[i, j]})
    pairs["band"] = pd.cut(pairs["cos"], BANDS, right=False).astype(str)
    sample = pairs.groupby("band").sample(n=PER_BAND, random_state=seed).sort_values("cos")
    if not SAMPLE.exists():
        sample.to_csv(SAMPLE, index=False)
    out["sample_file"] = str(SAMPLE)
    out["judged"] = judged()
    out["band_pairs"] = pairs["band"].value_counts().sort_index().to_dict()
    return out


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=1))
