from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[5]
DATA = ROOT / "agent-skills/ai-data-train-prod/data-li"
TIKI_SOURCES = ("tiki23", "tiki26")


def _tiki() -> dict:
    d = np.load(DATA / "features/emb.npz")
    keys = pd.DataFrame({"listing_id": d["listing_id"], "source": d["source"]})
    meta = pd.concat([pd.read_parquet(DATA / f"clean/{s}.parquet").assign(source=s)[["listing_id", "source", "title", "seller"]]
                      for s in TIKI_SOURCES])
    rows = keys.merge(meta, on=["listing_id", "source"], how="left")
    assert len(rows) == len(keys)
    return {"img": d["img"], "txt": d["txt"], "text": rows["title"].fillna("").to_numpy(),
            "seller": rows["seller"].to_numpy(), "src": d["source"]}


def _fashion() -> dict:
    d = np.load(DATA / "features/emb_tikifashion.npz")
    caption = pd.read_parquet(DATA / "clean/tikifashion.parquet").set_index("listing_id")["caption"]
    n = len(d["listing_id"])
    return {"img": d["img"], "txt": d["txt"], "text": caption.loc[d["listing_id"]].to_numpy(),
            "seller": np.full(n, None, dtype=object), "src": np.full(n, "tikifashion")}


def load_all() -> dict:
    a, b = _tiki(), _fashion()
    d = {k: np.concatenate([a[k], b[k]]) for k in a}
    keep = np.isfinite(d["img"].astype(np.float32)).all(axis=1) & np.isfinite(d["txt"].astype(np.float32)).all(axis=1)
    out = {k: v[keep] for k, v in d.items()}
    out["img"], out["txt"] = out["img"].astype(np.float32), out["txt"].astype(np.float32)
    return out
