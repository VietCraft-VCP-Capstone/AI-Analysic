import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import GroupShuffleSplit

from scripts.f29.register.learn import ROOT

DATA = ROOT / "agent-skills/ai-data-train-prod/data-li"
MAP = json.loads((ROOT / "AI-Analysic/app/core/f29/data/category_map.json").read_text("utf-8"))
NO_SELLER = {"oem", "no brand"}
SEED = 42


def _valid(df: pd.DataFrame, title: str, price: str) -> pd.DataFrame:
    df = df.dropna(subset=[title, price])
    return df[df[price] > 0]


def top25(values: pd.Series, group: pd.Series) -> pd.Series:
    return values.groupby(group).rank(pct=True).gt(0.75).astype("int64")


def split(seller: pd.Series, seed: int = SEED) -> np.ndarray:
    rows = pd.Series([f"row:{i}" for i in range(len(seller))], index=seller.index)
    g = seller.where(seller.notna(), rows).to_numpy()
    out = np.full(len(g), "train", dtype=object)
    _, rest = next(GroupShuffleSplit(n_splits=1, test_size=0.3, random_state=seed).split(g, groups=g))
    va, te = next(GroupShuffleSplit(n_splits=1, test_size=0.5, random_state=seed).split(rest, groups=g[rest]))
    out[rest[va]], out[rest[te]] = "val", "test"
    return out


def tiki23(raw: Path = DATA / "raw") -> pd.DataFrame:
    parts = [pd.read_csv(f).assign(group=MAP["tiki23"][f.stem.removeprefix("vietnamese_tiki_products_")])
             for f in sorted(raw.glob("vietnamese_tiki_products_*.csv"))]
    r = _valid(pd.concat(parts, ignore_index=True), "name", "price").drop_duplicates("id")
    df = pd.DataFrame({
        "listing_id": r["id"].astype("int64"), "source": "tiki23", "group": r["group"], "title": r["name"],
        "description": r["description"], "price": r["price"].astype("int64"),
        "n_images": r["number_of_images"].astype("int64"), "seller": r["current_seller"],
        "age_days": r["date_created"].astype("int64"), "sold": r["quantity_sold"].astype("int64"),
    }).reset_index(drop=True)
    df["top25"] = top25(df["sold"] / df["age_days"].clip(lower=30), df["group"])
    df["split"] = split(df["seller"])
    return df


def tiki26(raw: Path = DATA / "raw") -> pd.DataFrame:
    r = pd.read_csv(raw / "tiki_products_raw.csv")
    r = _valid(r[r["category"].isin(MAP["tiki26"])], "name", "price").drop_duplicates("product_id")
    sid = r["seller_id"].map(lambda v: None if pd.isna(v) else str(int(v)))
    brand = r["brand_name"].str.strip()
    brand = brand.where(~brand.str.lower().isin(NO_SELLER))
    df = pd.DataFrame({
        "listing_id": r["product_id"].astype("int64"), "source": "tiki26", "group": r["category"].map(MAP["tiki26"]),
        "title": r["name"], "description": "", "price": r["price"].astype("int64"), "image_url": r["thumbnail_url"],
        "seller": sid.where(sid.notna(), brand), "sold": r["quantity_sold"].fillna(0).astype("int64"),
    }).reset_index(drop=True)
    df["top25"] = top25(df["sold"], df["group"])
    df["split"] = split(df["seller"])
    df["scraped_at"] = r["scraped_at"].to_numpy()
    return df


def compare(new: pd.DataFrame, old: pd.DataFrame) -> dict:
    m = new.merge(old, on="listing_id", suffixes=("", "_old"))
    same = {c: float(((m[c].isna() & m[c + "_old"].isna()) | (m[c].astype(str) == m[c + "_old"].astype(str))).mean())
            for c in new.columns if c != "listing_id"}
    return {"rows": [len(new), len(old)], "same_ids": set(new["listing_id"]) == set(old["listing_id"]), **same}


def main(argv: list[str]) -> int:
    built = {"tiki23": tiki23(), "tiki26": tiki26()}
    if "--check" not in argv:
        for name, df in built.items():
            df.to_parquet(DATA / "clean" / f"{name}.parquet", index=False)
        return 0
    report = {n: compare(df, pd.read_parquet(DATA / "clean" / f"{n}.parquet")) for n, df in built.items()}
    print(json.dumps(report, ensure_ascii=False, indent=1))
    ok = all(r["same_ids"] and all(v == 1.0 for k, v in r.items() if k not in ("rows", "same_ids")) for r in report.values())
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
