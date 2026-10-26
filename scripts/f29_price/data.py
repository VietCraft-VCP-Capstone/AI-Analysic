import pandas as pd

from scripts.li import paths

SOURCES = ["tiki23", "tiki26"]
COLS = ["group", "title", "price"]


def _clean(src):
    df = pd.read_parquet(paths.clean(f"{src}.parquet"))
    title = df["title"].fillna("").str.strip()
    return df[(df["price"] > 0) & (title != "")]


def _part(frames, split):
    return pd.concat([f[f["split"] == split][COLS] for f in frames], ignore_index=True)


def load():
    frames = [_clean(src) for src in SOURCES]
    out = {"train": _part(frames, "train"), "val": _part(frames, "val")}
    out |= {f"{src}_test": f[f["split"] == "test"][COLS] for src, f in zip(SOURCES, frames)}
    return out
