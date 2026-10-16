import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.core.f29.scoring import (  # noqa: E402
    bayes_shrunk_rating,
    content_score,
    freshness_score,
    inventory_score,
    rating_axis_score,
    status_from_score,
    total_score,
)

VC_DATA = ROOT.parent / "vc-data"
OUT_CSV = ROOT / "docs" / "health_score_example.csv"
REF_NOW = datetime(2026, 8, 30, tzinfo=timezone.utc)
N_NO_REVIEW_EXTRA = 3


def _split(value) -> list:
    return [x for x in str(value or "").split(";") if x.strip()]


def main():
    listings = pd.read_parquet(VC_DATA / "master/listings.parquet")
    variants = pd.read_parquet(VC_DATA / "master/listing_variants.parquet")
    reviews = pd.read_csv(VC_DATA / "samples/reviews.csv")

    variants["stock_qty"] = pd.to_numeric(variants["stock_qty"], errors="coerce").fillna(0)
    variants_of = variants.groupby("listing_id")["stock_qty"].apply(list).to_dict()
    review_agg = reviews.groupby("listing_id")["star"].agg(["sum", "count"])
    platform_mean = float(reviews["star"].mean())

    rows = []
    for _, l in listings.iterrows():
        lid = l["listing_id"]
        product = {
            "title": l["title"], "description": "" if pd.isna(l["description"]) else str(l["description"]),
            "images": _split(l["images"]), "tags": _split(l["tags"]),
            "product_type": "READY_TO_SHIP",
            "content_changed_at": datetime.strptime(str(l["created_at"])[:19], "%Y-%m-%d %H:%M:%S"),
        }
        stocks = variants_of.get(lid, [])
        n_rv, sum_rv = 0, 0
        rating = None
        if lid in review_agg.index:
            n_rv, sum_rv = int(review_agg.loc[lid, "count"]), int(review_agg.loc[lid, "sum"])
            rating = round(rating_axis_score(bayes_shrunk_rating(sum_rv, n_rv, platform_mean)), 1)

        content, _ = content_score(product)
        inventory = inventory_score(product, [{"stock_quantity": q} for q in stocks])
        axes = {
            "conversion": None,
            "rating": rating,
            "content": round(content, 1),
            "inventory": None if inventory is None else round(inventory, 1),
            "freshness": round(freshness_score(product, now=REF_NOW), 1),
        }
        score = total_score(axes)
        rows.append({
            "listing_id": lid, "title": l["title"],
            "n_images": len(product["images"]), "desc_len": len(product["description"].strip()),
            "n_tags": len(product["tags"]), "n_reviews": n_rv, "sum_stars": sum_rv,
            "variants_in_stock": f"{sum(1 for q in stocks if q > 0)}/{len(stocks)}",
            "age_days": (REF_NOW - product["content_changed_at"].replace(tzinfo=timezone.utc)).days,
            **axes, "score": score,
            "status": None if score is None else status_from_score(score),
        })

    df = pd.DataFrame(rows)
    print(f"{len(df):,} listing có điểm. Phân bố status:\n{df['status'].value_counts(dropna=False)}")

    has_review = df[df["n_reviews"] > 0].sort_values("score", ascending=False)
    no_review = df[df["n_reviews"] == 0].sort_values("score").reset_index(drop=True)
    extra = no_review.iloc[sorted({0, len(no_review) // 2, len(no_review) - 1})[:N_NO_REVIEW_EXTRA]]
    final = pd.concat([has_review, extra]).reset_index(drop=True)

    final.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")
    print(f"\nC (trung bình toàn sàn) = {platform_mean:.4f}")
    print(f"Đã ghi {len(final)} dòng vào {OUT_CSV}")
    print(final.drop(columns=["title"]).to_string(index=False))


if __name__ == "__main__":
    main()
