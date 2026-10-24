import json
import sys
import time
from collections import Counter
from datetime import date

import numpy as np
import pandas as pd

from app.api.v1._live import db_live
from app.core.listing_intel import features as F
from app.core.listing_intel import intel, live_data
from scripts.li.embed_cache import features_dir
from scripts.li.train import FEATURES, finite

OUT = features_dir() / "vietcraft_check.json"
AXES = ("image", "text", "tags", "market", "trend")
PSI_COLS = F.META_COLS + F.TEXT_COLS + ["img_sharpness", "img_brightness", "img_contrast", "img_border_uniform",
                                         "img_text_ratio", "sim_title", "sim_category"] + F.MARKET_COLS + F.TREND_COLS
MIN_ROWS = 5


def psi(ref, cur, bins=10):
    ref, cur = np.asarray(ref, float), np.asarray(cur, float)
    ref, cur = ref[~np.isnan(ref)], cur[~np.isnan(cur)]
    if len(cur) < MIN_ROWS or not len(ref):
        return None
    edges = np.unique(np.quantile(ref, np.linspace(0, 1, bins + 1)))
    n = max(len(edges) - 1, 1)
    share = lambda x: np.bincount(np.clip(np.searchsorted(edges, x, side="right") - 1, 0, n - 1), minlength=n) / len(x)
    a, b = share(ref) + 1e-4, share(cur) + 1e-4
    return round(float(np.sum((b - a) * np.log(b / a))), 2)


def _row(pid, at):
    inp = live_data.load_listing(pid)
    if inp is None:
        return None
    parts = intel.build(inp, at, False)
    t0 = time.perf_counter()
    out = intel.analyze(inp, at, persist=False, store_embeddings=False)
    secs = time.perf_counter() - t0
    return {"pid": pid, "title": inp.title[:60], "group": parts["inp"].group,
            "has_image": not np.isnan(parts["feats"]["emb_pca_0"]), "score": out["score"], "secs": secs,
            "no_material": bool(out["material"]["missing"]), "codes": [a["code"] for a in out["advice"]],
            "add_images": next((a["impact"] for a in out["advice"] if a["code"] == "no_images"), np.nan),
            **{f"ax_{a}": out["axes"][a]["score"] for a in AXES}, **{c: parts["feats"][c] for c in PSI_COLS}}


def _shift(df, train):
    out = {}
    for g, d in df.groupby("group"):
        ref = train[train["group"] == g]
        if len(d) < MIN_ROWS or ref.empty:
            continue
        vals = {c: v for c in PSI_COLS if (v := psi(ref[c], d[c])) is not None}
        top = sorted(vals, key=lambda c: -vals[c])[:8]
        out[g] = {"n": int(len(d)), "n_image": int(d["has_image"].sum()), "psi_over_0_25": sum(v > 0.25 for v in vals.values()),
                  "psi_features": len(vals), "top": {c: {"psi": vals[c], "tiki_median": round(float(ref[c].median()), 3),
                                                          "vietcraft_median": round(float(d[c].median()), 3)} for c in top}}
    return out


def _add_images(v):
    out = {"n": int(len(v)), "positive": int((v > 0).sum())}
    return {**out, **{k: round(float(v.agg(k)), 1) for k in ("min", "median", "max")}} if len(v) else out


def run(at=date(2026, 10, 21), remote=False):
    db = db_live()
    if not remote and db.client.address[0] not in ("127.0.0.1", "localhost"):
        raise SystemExit("chỉ chạy trên Mongo local")
    rows = [r for p in db.products.find({}, {"_id": 1}) if (r := _row(str(p["_id"]), at))]
    df = pd.DataFrame(rows)
    table = pd.read_parquet(FEATURES / "table.parquet")
    score = lambda s: {k: round(float(v), 2) for k, v in s.describe()[["min", "25%", "50%", "75%", "max"]].items()}
    return {"database": db.name, "date": at.isoformat(), "n": int(len(df)), "n_shops": len(db.products.distinct("shop_id")),
            "groups": df["group"].fillna("không rõ").value_counts().to_dict(), "n_image": int(df["has_image"].sum()),
            "axis_coverage": {a: round(float(df[f"ax_{a}"].notna().mean()), 3) for a in AXES},
            "score": score(df["score"]), "score_median_by_image": {
                "có ảnh": round(float(df[df["has_image"]]["score"].median()), 2),
                "không ảnh": round(float(df[~df["has_image"]]["score"].median()), 2)},
            "no_image_advice": _add_images(df["add_images"].dropna()),
            "no_material": int(df["no_material"].sum()),
            "advice_top": dict(Counter(c for cs in df["codes"] for c in cs).most_common(8)),
            "seconds": {k: round(float(df["secs"].agg(k)), 2) for k in ("median", "max", "sum")},
            "shift": _shift(df, table[table["split"] == "train"]),
            "examples": df[df["has_image"]].sort_values("score", ascending=False).head(5)[
                ["title", "group", "score", *(f"ax_{a}" for a in AXES)]].round(1).to_dict("records")}


if __name__ == "__main__":
    remote = "--remote" in sys.argv
    out = features_dir() / "vietcraft_check_atlas.json" if remote else OUT
    text = json.dumps(finite(run(remote=remote)), ensure_ascii=False, indent=1, allow_nan=False)
    out.write_text(text, "utf-8")
    print(text)
