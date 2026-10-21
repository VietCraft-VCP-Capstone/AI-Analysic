import pandas as pd

from scripts.li import paths
from scripts.li.fit import AXES

RAW = {"tiki23": "vietnamese_tiki_products_*.csv", "tiki26": "tiki_products_raw.csv"}


def _raw_rows(pattern):
    files = sorted(paths.raw("").glob(pattern))
    return sum(len(pd.read_csv(f, usecols=[0])) for f in files) if files else None


def _splits(df):
    out = {}
    for split in ("train", "val", "test"):
        part = df[df["split"] == split]
        out[split] = {"rows": int(len(part)), "top25_rate": round(float(part["top25"].mean()), 3),
                      "sellers": int(part["seller"].dropna().nunique()),
                      "rows_no_seller": int(part["seller"].isna().sum())}
    return out


def _missing(df):
    return {a: round(float(df[cols].isna().all(axis=1).mean()), 3) for a, cols in AXES.items()}


def run(table):
    out = {}
    for src, df in table.groupby("source"):
        clean = paths.clean(f"{src}.parquet")
        out[src] = {
            "raw_rows": _raw_rows(RAW.get(src, "")),
            "clean_rows": int(len(pd.read_parquet(clean, columns=["listing_id"]))) if clean.exists() else None,
            "table_rows": int(len(df)),
            "groups": sorted(df["group"].astype(str).unique()),
            "splits": _splits(df),
            "axis_all_nan_share": _missing(df),
        }
    fashion = paths.DATA_DIR / "features" / "emb_tikifashion.npz"
    out["tikifashion"] = {"clean_rows": int(len(pd.read_parquet(paths.clean("tikifashion.parquet"))))
                          if paths.clean("tikifashion.parquet").exists() else None,
                          "embedded": fashion.exists()}
    monthly = pd.read_parquet(paths.clean("tikireviews_monthly.parquet"))
    out["tikireviews"] = {"groups": sorted(monthly["group"].unique()),
                          "reviews_by_group": monthly.groupby("group")["n_reviews"].sum().astype(int).to_dict()}
    return out
