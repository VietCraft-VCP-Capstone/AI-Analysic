from dataclasses import replace

import pandas as pd

from app.core.listing_intel import features as F
from app.core.listing_intel.context import save_context
from app.core.listing_intel.types import ListingInput
from scripts.li import embed_cache, paths
from scripts.li.fit_context import fit_context

ID_COLS = ["listing_id", "source", "group", "seller", "split", "top25", "sold"]
TIKI23_AT = "2023-09-15"
COL_GROUPS = {"meta": F.META_COLS, "text": F.TEXT_COLS, "image": F.IMAGE_COLS,
              "market": F.MARKET_COLS, "trend": F.TREND_COLS}


def load_rows() -> pd.DataFrame:
    a = pd.read_parquet(paths.clean("tiki23.parquet")).assign(scraped_at=TIKI23_AT, image_url=None)
    b = pd.read_parquet(paths.clean("tiki26.parquet")).assign(n_images=float("nan"))
    df = pd.concat([a.drop(columns="age_days"), b], ignore_index=True)
    df[["title", "description"]] = df[["title", "description"]].fillna("").astype(str)
    df["seller"] = df["seller"].astype("object").where(df["seller"].notna(), None)
    df["at"] = pd.to_datetime(df["scraped_at"], format="ISO8601").dt.date
    return df


def _input(r) -> ListingInput:
    urls = [r.image_url] if isinstance(r.image_url, str) else []
    return ListingInput(title=r.title, description=r.description, group=r.group,
                        price=float(r.price), image_urls=urls, seller_id=r.seller)


def _until(series: dict, at) -> dict:
    return {k: s[s.index <= pd.Timestamp(at)] for k, s in series.items()}


def assemble_rows(df, txt, img, quals, ctx, fold_ctx, folds, pos) -> pd.DataFrame:
    series_at = {at: _until(ctx.trend_series, at) for at in df["at"].unique()}
    ctxs, rows = {}, []
    for i, r in enumerate(df.itertuples(index=False)):
        key = (int(folds[i]), r.at)
        if key not in ctxs:
            base = fold_ctx[key[0]] if key[0] >= 0 else ctx
            ctxs[key] = replace(base, at=r.at, trend_series=series_at[r.at])
        feats = None if quals[i] is None else {**quals[i], "vec": img[i]}
        rows.append(F.assemble(_input(r), feats, ctxs[key], title_vec=txt[i], exclude=pos.get(i)))
    return pd.DataFrame(rows, columns=F.FEATURE_COLS)


def report(table: pd.DataFrame) -> None:
    print(f"table.parquet: shape {table.shape}")
    nan = pd.DataFrame({g: table[cols].isna().mean(axis=1) for g, cols in COL_GROUPS.items()})
    print("NaN rate by column group and source:")
    print(nan.groupby(table["source"]).mean().round(3).to_string())


def main() -> None:
    df = load_rows()
    txt, img = embed_cache.embeddings(df)
    embed_cache.tikifashion()
    ctx, fold_ctx, folds, pos = fit_context(df, txt, img)
    out = embed_cache.features_dir()
    save_context(ctx, out / "context")
    quals = embed_cache.qualities(df["image_url"].tolist())
    feats = assemble_rows(df, txt, img, quals, ctx, fold_ctx, folds, pos)
    feats["n_images"] = df["n_images"].to_numpy(float)
    table = pd.concat([df[ID_COLS].reset_index(drop=True), feats], axis=1)
    table.to_parquet(out / "table.parquet", index=False)
    report(table)


if __name__ == "__main__":
    main()
