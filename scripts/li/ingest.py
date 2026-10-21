import json
import os
import shutil
from pathlib import Path

import pandas as pd

from scripts.li import paths
from scripts.li.labels import split_by_seller, top25
from scripts.li.reviews import build_reviews

DL = Path(
    os.environ.get("LI_DL_DIR")
    or "/tmp/claude-1000/-home-rio-Documents-CODE-nodejs-vietcraft/"
    "a6de79fb-f4f8-4967-8a37-cf5641336562/scratchpad/dl"
)
CATEGORY_MAP = Path(__file__).resolve().parents[2] / "app/core/listing_intel/data/category_map.json"
PREFIX = "vietnamese_tiki_products_"
SOURCES = {
    "tikifashion": f"{PREFIX}*.csv",
    "huyhoang1308_tiki-csv": "tiki_products_raw.csv",
    "giaphoangkim_tiki-fashion": "filtered_cleaned_caption.csv",
}
PLACEHOLDER_BRANDS = {"", "oem", "no brand", "không thương hiệu", "nan"}


def fetch_raw() -> None:
    for folder, pattern in SOURCES.items():
        for src in (DL / folder).glob(pattern):
            dst = paths.raw(src.name)
            if not dst.exists():
                shutil.copy2(src, dst)
    missing = [p for p in SOURCES.values() if not any(paths.raw("").glob(p))]
    if missing:
        raise SystemExit(
            f"Missing raw sources {missing}: put them in {paths.raw('')} or set LI_DL_DIR (now {DL})"
        )


def valid(df: pd.DataFrame) -> pd.DataFrame:
    df = df.dropna(subset=["name", "price"])
    return df[df["price"] > 0]


def label(df: pd.DataFrame, source: str, score: pd.Series) -> pd.DataFrame:
    df = df.assign(source=source, _score=score)
    df["top25"] = top25(df, "_score", ["source", "group"])
    df["split"] = split_by_seller(df, "seller")
    return df.drop(columns="_score")


def tiki23_score(df: pd.DataFrame) -> pd.Series:
    return df["sold"] / df["age_days"].clip(lower=30)


def resolve_seller(df: pd.DataFrame) -> pd.Series:
    brand = df["brand_name"].str.normalize("NFC").str.strip()
    brand = brand.mask(brand.str.lower().isin(PLACEHOLDER_BRANDS))
    return df["seller_id"].astype("string").fillna(brand)


def build_tiki23(cmap: dict) -> pd.DataFrame:
    frames = []
    for path in sorted(paths.raw("").glob(f"{PREFIX}*.csv")):
        df = pd.read_csv(path)
        df["group"] = cmap["tiki23"].get(path.stem.removeprefix(PREFIX))
        frames.append(df)
    df = valid(pd.concat(frames, ignore_index=True)).dropna(subset=["group"])
    renames = {"id": "listing_id", "name": "title", "number_of_images": "n_images"}
    renames |= {"current_seller": "seller", "date_created": "age_days", "quantity_sold": "sold"}
    df = df.drop_duplicates("id").rename(columns=renames)
    df["description"] = df["description"].fillna("")
    cols = ["listing_id", "source", "group", "title", "description", "price"]
    cols += ["n_images", "seller", "age_days", "sold", "top25", "split"]
    return label(df, "tiki23", tiki23_score(df))[cols]


def build_tiki26(cmap: dict) -> pd.DataFrame:
    df = pd.read_csv(paths.raw("tiki_products_raw.csv"))
    df["group"] = df["category"].map(cmap["tiki26"])
    renames = {"product_id": "listing_id", "name": "title", "thumbnail_url": "image_url"}
    renames |= {"quantity_sold": "sold"}
    df = valid(df.dropna(subset=["group"])).drop_duplicates("product_id").rename(columns=renames)
    df["description"] = df["short_description"].fillna("")
    df["seller"] = resolve_seller(df)
    cols = ["listing_id", "source", "group", "title", "description", "price", "image_url"]
    cols += ["seller", "sold", "top25", "split", "scraped_at"]
    return label(df, "tiki26", df["sold"])[cols]


def build_tikifashion() -> pd.DataFrame:
    df = pd.read_csv(paths.raw("filtered_cleaned_caption.csv"))
    df = df.dropna(subset=["caption_clean", "image_url"])
    df = df.sample(n=min(5000, len(df)), random_state=42)
    df = df.rename(columns={"click_id": "listing_id", "caption_clean": "caption"})
    return df[["listing_id", "image_url", "caption", "category"]].reset_index(drop=True)


def save(df: pd.DataFrame, name: str) -> None:
    df.to_parquet(paths.clean(name), index=False)
    ratio = f" top25={df['top25'].mean():.3f}" if "top25" in df else ""
    print(f"{name}: {len(df)} rows{ratio}")


def main() -> None:
    fetch_raw()
    cmap = json.loads(CATEGORY_MAP.read_text(encoding="utf-8"))
    save(build_tiki23(cmap), "tiki23.parquet")
    save(build_tiki26(cmap), "tiki26.parquet")
    save(build_tikifashion(), "tikifashion.parquet")
    monthly = paths.clean("tikireviews_monthly.parquet")
    if not monthly.exists() or pd.read_parquet(monthly).empty:
        save(build_reviews(), "tikireviews_monthly.parquet")


if __name__ == "__main__":
    main()
