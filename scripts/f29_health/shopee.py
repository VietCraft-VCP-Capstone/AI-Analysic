import os
from pathlib import Path

import pandas as pd

from scripts.f29_health import frames
from scripts.li.labels import split_by_seller, top25

SHOPEE_DIR = Path(
    os.environ.get("F29_SHOPEE_DIR")
    or Path(__file__).resolve().parents[3] / "ai-data-train-prod" / "shopee-data" / "product-details" / "data"
)
MIN_AGE_DAYS = 30
COLUMNS = [
    "listing_id", "source", "seller", "group", "n_images", "desc_len",
    "price", "price_ref", "sold", "age_days", "top25", "split",
]


def _read(folder: Path) -> pd.DataFrame:
    files = sorted(folder.glob("*.parquet"))
    if not files:
        raise FileNotFoundError(f"Không thấy dữ liệu Shopee tại {folder}")
    return pd.concat([pd.read_parquet(f) for f in files], ignore_index=True).drop_duplicates("itemId")


def load(folder: Path | None = None) -> pd.DataFrame:
    raw = _read(folder or SHOPEE_DIR).dropna(subset=["catId"])
    age = (raw["_lastSeenAt"] - pd.to_datetime(raw["createdAt"], utc=True)).dt.days.astype(float)
    df = pd.DataFrame({
        "listing_id": raw["itemId"].astype(str),
        "source": "shopee",
        "seller": raw["shopId"].astype(str),
        "group": raw["catId"].astype(str),
        "n_images": raw["images"].map(len),
        "desc_len": raw["description"].fillna("").str.strip().str.len(),
        "price": raw["priceMin"].astype(float) / 1e5,
        "age_days": age,
        "sold": raw["ratingCount"].fillna(0) / age.clip(lower=MIN_AGE_DAYS),
    })
    df = df[df["price"] > 0].reset_index(drop=True)
    df["top25"] = top25(df, "sold", ["group"])
    df["split"] = split_by_seller(df, "seller")
    df["price_ref"] = df.groupby("group")["price"].transform(frames._loo)
    return df[COLUMNS]
