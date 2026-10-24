import numpy as np
import pandas as pd
import pytest

from scripts.li.ingest import resolve_seller, tiki23_score
from scripts.li.labels import split_by_seller, top25
from scripts.li.reviews import monthly_from_frame


def test_top25_marks_quarter_per_group():
    df = pd.DataFrame(
        {
            "group": ["a"] * 4 + ["b"] * 4,
            "score": [1, 2, 3, 4, 40, 30, 20, 10],
        }
    )
    df["top25"] = top25(df, "score", ["group"])
    assert df.groupby("group")["top25"].sum().tolist() == [1, 1]
    assert df.loc[df["top25"] == 1, "score"].tolist() == [4, 40]


def _sellers():
    return pd.DataFrame({"seller": [f"s{i % 60}" for i in range(300)]})


def test_split_keeps_each_seller_in_one_split():
    df = _sellers()
    df["split"] = split_by_seller(df, "seller")
    assert df.groupby("seller")["split"].nunique().max() == 1
    assert set(df["split"]) == {"train", "val", "test"}


def test_split_is_deterministic():
    df = _sellers()
    first = split_by_seller(df, "seller")
    second = split_by_seller(df, "seller")
    assert first.equals(second)


def test_split_handles_missing_seller():
    df = pd.DataFrame({"seller": [None] * 100})
    out = split_by_seller(df, "seller")
    assert set(out) == {"train", "val", "test"}


def test_split_handles_partly_missing_float_seller():
    sellers = [np.nan if i % 7 == 0 else float(i % 40) for i in range(300)]
    df = pd.DataFrame({"seller": sellers})
    df["split"] = split_by_seller(df, "seller")
    known = df.dropna(subset=["seller"])
    assert known.groupby("seller")["split"].nunique().max() == 1
    assert set(df["split"]) == {"train", "val", "test"}


def test_tiki23_score_floors_age_at_30_days():
    df = pd.DataFrame(
        {"source": "tiki23", "group": "bags", "sold": [30, 90, 10, 0], "age_days": [3, 30, 100, 50]}
    )
    df["top25"] = top25(df.assign(score=tiki23_score(df)), "score", ["source", "group"])
    assert df["top25"].tolist() == [0, 1, 0, 0]


def test_resolve_seller_falls_back_to_brand_but_not_placeholders():
    df = pd.DataFrame(
        {
            "seller_id": [7.0, np.nan, np.nan, np.nan, np.nan],
            "brand_name": ["Acme", "Acme", "OEM", " No Brand ", "Không thương hiệu"],
        }
    )
    seller = resolve_seller(df)
    assert seller.iloc[0] == "7.0"
    assert seller.iloc[1] == "Acme"
    assert seller.iloc[2:].isna().all()


def _reviews(name, year, counts):
    dates = [f"{year}-{m:02d}-15 10:00:00" for m, c in enumerate(counts, 1) for _ in range(c)]
    return pd.DataFrame({"name": name, "review_created_date": dates})


def test_monthly_removes_year_volume_trend_and_filters():
    df = pd.concat(
        [
            _reviews("Túi xách", 2021, [20] + [10] * 11),
            _reviews("Túi xách", 2022, [100] * 11 + [200]),
            _reviews("Túi xách", 2023, [500] * 3),
            _reviews("Giày da", 2021, [1] * 12),
        ]
    )
    out = monthly_from_frame(df, min_reviews=100)
    assert out.columns.tolist() == ["group", "month", "index", "n_reviews"]
    assert set(out["group"]) == {"bags"}
    by_month = out.set_index("month")
    assert by_month["index"].mean() == pytest.approx(1.0)
    assert by_month.loc[1, "index"] == pytest.approx(by_month.loc[12, "index"])
    assert by_month.loc[1, "n_reviews"] == 120
