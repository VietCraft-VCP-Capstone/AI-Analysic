import subprocess
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.li import paths

REVIEWS_URL = (
    "https://www.kaggle.com/api/v1/datasets/download/"
    "farmingfree/vietnamese-e-commerce-suspicious-reviews-dataset"
)
GROUP_KEYWORDS = [
    ("bags", r"\btúi\b"),
    ("shoes", r"\b(?:giày|dép)\b"),
    ("fashion", r"\b(?:áo|quần|váy|đầm)\b"),
]
MIN_REVIEWS = 5000
TYPES = {"group": "object", "month": "int64", "index": "float64", "n_reviews": "int64"}


def empty_monthly() -> pd.DataFrame:
    return pd.DataFrame({k: pd.Series(dtype=v) for k, v in TYPES.items()})


def monthly_from_frame(df: pd.DataFrame, min_reviews: int = MIN_REVIEWS) -> pd.DataFrame:
    df = df.dropna(subset=["name", "review_created_date"])
    names = df["name"].str.normalize("NFC").str.lower()
    conds = [names.str.contains(rx, regex=True) for _, rx in GROUP_KEYWORDS]
    when = pd.to_datetime(df["review_created_date"], errors="coerce")
    frame = pd.DataFrame(
        {"group": np.select(conds, [g for g, _ in GROUP_KEYWORDS], default="home"),
         "year": when.dt.year, "month": when.dt.month}
    ).dropna()
    counts = frame.groupby(["group", "year", "month"]).size().unstack(fill_value=0)
    counts = counts.reindex(columns=range(1, 13), fill_value=0)
    counts = counts[(counts > 0).all(axis=1)]
    index = counts.div(counts.mean(axis=1), axis=0).groupby("group").mean()
    n_reviews = counts.groupby("group").sum()
    keep = n_reviews.index[n_reviews.sum(axis=1) >= min_reviews]
    if len(keep) == 0:
        return empty_monthly()
    out = pd.concat({"index": index.loc[keep].stack(), "n_reviews": n_reviews.loc[keep].stack()}, axis=1)
    out = out.rename_axis(["group", "month"]).reset_index()
    return out.astype(TYPES)


def monthly_index(zip_path: Path) -> pd.DataFrame:
    return monthly_from_frame(pd.read_csv(zip_path, usecols=["name", "review_created_date"]))


def build_reviews() -> pd.DataFrame:
    zip_path = paths.raw("tikireviews.zip")
    try:
        if not zip_path.exists():
            curl = ["curl", "-fL", "-sS", "--max-time", "900", REVIEWS_URL, "-o", str(zip_path)]
            subprocess.run(curl, check=True)
        out = monthly_index(zip_path)
    except (subprocess.CalledProcessError, zipfile.BadZipFile, OSError, ValueError) as exc:
        print(f"WARNING: tikireviews unavailable ({exc}); writing empty monthly index")
        out = empty_monthly()
    zip_path.unlink(missing_ok=True)
    return out
