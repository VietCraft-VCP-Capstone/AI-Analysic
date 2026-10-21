import pandas as pd

from app.core.f29.ml.live_data import PRODUCT_COLS, RATED_COLS, SALES_COLS

T = pd.Timestamp("2026-06-01")


def day(n):
    return T + pd.Timedelta(days=n)


def sale(order, product, seller="s1", at=-10, price=100.0, delivered=3):
    return [order, product, seller, price, 10.0, day(at), day(at + delivered), pd.NaT]


def tables(sales, rated=(), products=None):
    ids = sorted({row[1] for row in sales})
    products = products or [[p, "cat", 3, 300, 40, 500, 10, 10, 10] for p in ids]
    return (pd.DataFrame(sales, columns=SALES_COLS),
            pd.DataFrame(products, columns=PRODUCT_COLS),
            pd.DataFrame(list(rated), columns=RATED_COLS))
