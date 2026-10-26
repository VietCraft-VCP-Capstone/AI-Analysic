import numpy as np
import pandas as pd
import pytest

from scripts.f29_health import shopee


def _shopee(ids, rating=60.0, created="2026-10-01", seen="2026-10-11"):
    n = len(ids)
    return pd.DataFrame({
        "itemId": [f"it{i}" for i in ids],
        "shopId": [f"s{i % 10}" for i in ids],
        "catId": [float(i % 2) for i in ids],
        "images": [["a", "b", "c"]] * n,
        "description": [" mô tả "] * n,
        "priceMin": [i * 1000 for i in ids],
        "ratingCount": [rating] * n,
        "createdAt": pd.to_datetime([created] * n, utc=True),
        "_lastSeenAt": pd.to_datetime([seen] * n, utc=True),
    })


def test_load_columns_and_dedup(tmp_path):
    _shopee(range(0, 20)).to_parquet(tmp_path / "a.parquet")
    _shopee(range(19, 39)).to_parquet(tmp_path / "b.parquet")
    df = shopee.load(tmp_path)
    assert list(df.columns) == [
        "listing_id", "source", "seller", "group", "n_images", "desc_len",
        "price", "price_ref", "sold", "age_days", "top25", "split",
    ]
    assert df["listing_id"].is_unique
    assert len(df) == 38
    assert (df["price"] > 0).all()
    assert df.set_index("listing_id").loc["it5", "price"] == pytest.approx(5000 / 1e5)


def test_sold_is_age_adjusted(tmp_path):
    _shopee(range(1, 11)).to_parquet(tmp_path / "a.parquet")
    df = shopee.load(tmp_path)
    assert (df["age_days"] == 10).all()
    assert (df["sold"] == 2.0).all()


def test_row_without_cat_is_dropped(tmp_path):
    raw = _shopee(range(1, 11))
    raw.loc[raw["itemId"] == "it3", "catId"] = np.nan
    raw.to_parquet(tmp_path / "a.parquet")
    df = shopee.load(tmp_path)
    assert "it3" not in set(df["listing_id"])
    assert len(df) == 9
    assert df["group"].notna().all()


def test_missing_folder_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        shopee.load(tmp_path)
