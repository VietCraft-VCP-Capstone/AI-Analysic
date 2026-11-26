import pytest

from app.core.f29.ml.features import snapshot
from tests.f29_ml.samples import T, day, sale, tables


def _snap(sales, rated=()):
    return snapshot(*tables(sales, rated), T).set_index("product_id")


def test_only_listings_sold_in_last_180_days_are_scored():
    df = _snap([sale("o1", "active", at=-10), sale("o2", "dead", at=-200)])
    assert list(df.index) == ["active"]


def test_label_uses_only_the_next_90_days():
    df = _snap([sale("o1", "a", at=-10), sale("o2", "a", at=5),
                sale("o3", "b", at=-10), sale("o4", "b", at=95)])
    assert df.loc["a", "label"] == 1
    assert df.loc["b", "label"] == 0


def test_future_sales_do_not_leak_into_features():
    df = _snap([sale("o1", "a", at=-10), sale("o2", "a", at=1), sale("o3", "a", at=2)])
    assert df.loc["a", "sales_90d"] == 1
    assert df.loc["a", "days_since_last"] == 10


def test_reviews_after_cutoff_are_ignored():
    rated = [["o1", "a", "s1", 5, day(-5)], ["o1", "a", "s1", 1, day(2)]]
    df = _snap([sale("o1", "a", at=-10)], rated)
    assert df.loc["a", "review_count"] == 1
    assert df.loc["a", "low_star_share"] == 0


def test_undelivered_orders_do_not_count_for_ship_days():
    df = _snap([sale("o1", "a", at=-10, delivered=4), sale("o2", "b", at=-3, delivered=8)])
    assert df.loc["a", "seller_ship_days"] == pytest.approx(4)


def test_label_window_is_closed_at_t_and_open_at_t_plus_90():
    df = _snap([sale("o1", "a", at=-10), sale("o2", "a", at=0),
                sale("o3", "b", at=-10), sale("o4", "b", at=90)])
    assert df.loc["a", "label"] == 1
    assert df.loc["b", "label"] == 0


def test_reviews_of_orders_placed_after_cutoff_are_ignored():
    rated = [["o2", "a", "s1", 1, day(-1)]]
    df = _snap([sale("o1", "a", at=-10), sale("o2", "a", at=3)], rated)
    assert df.loc["a", "review_count"] == 0
