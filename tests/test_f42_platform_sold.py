"""
F42 lấy thêm dữ liệu trên sàn: giá bán THẬT trong đơn đã giao (không lấy đơn giả lập / huỷ / hoàn tiền).
Không cần MongoDB.
"""

from bson import Decimal128, ObjectId

import pandas as pd

from app.services.f42 import pricing_engine
from app.services.f42.comparable_pricing import ComparableEstimate, Comparable, ComparableIndex
from app.services.f42.pricing_engine import fetch_sold_items, pricing_from_comparables

P1, P2, P3 = ObjectId(), ObjectId(), ObjectId()


class _Orders:
    def __init__(self, rows):
        self.rows, self.pipeline = rows, None

    def aggregate(self, pipeline):
        self.pipeline = pipeline
        return iter(self.rows)


def test_fetch_sold_items_filters_real_delivered_and_takes_median():
    orders = _Orders([
        {"pid": P1, "title": "Cốc sứ vẽ tay", "price": Decimal128("100000"), "qty": 2},
        {"pid": P1, "title": "Cốc sứ vẽ tay", "price": Decimal128("120000"), "qty": 1},
        {"pid": P1, "title": "Cốc sứ vẽ tay", "price": Decimal128("140000"), "qty": 1},
        {"pid": P2, "title": "Lỗi giá", "price": None, "qty": 1},
    ])
    out = fetch_sold_items({"orders": orders})
    assert out == {P1: {"title": "Cốc sứ vẽ tay", "price": 120000.0, "qty": 4}}
    match = orders.pipeline[0]["$match"]
    assert match["is_simulated"] == {"$ne": True}          # bỏ đơn giả lập
    assert match["order_status"] == "DELIVERED"            # chỉ đơn đã giao
    assert match["refund_status"] == {"$ne": "REFUNDED"}   # bỏ đơn đã hoàn tiền
    assert "$gte" in match["created_at"]


def test_fetch_sold_items_db_error_returns_empty():
    class Broken:
        def aggregate(self, _):
            raise RuntimeError("down")
    assert fetch_sold_items({"orders": Broken()}) == {}
    assert fetch_sold_items(None) == {}


def _index():
    words = ["vẽ tay", "hoa sen", "hoa mai", "men rạn", "quai tròn", "Bát Tràng"]
    rows = [("home", f"Cốc sứ {words[i % 6]} {words[(i + 2) % 6]}", 40_000 + i * 500, 1) for i in range(30)]
    rows += [("fashion", f"Áo thun {w}", 90_000, 1) for w in ("cotton", "basic", "oversize", "cotton basic")]
    return ComparableIndex(pd.DataFrame(rows, columns=["group", "title", "price", "sold"]))


def test_refresh_live_weights_sold_and_adds_changed_or_retired_prices(monkeypatch):
    idx = _index()
    monkeypatch.setattr(pricing_engine, "fetch_live_listings", lambda db: [
        {"_id": P1, "title": "Cốc sứ vẽ tay hoa sen", "price": 120_000, "category_ids": []},
        {"_id": P2, "title": "Cốc sứ vẽ tay hoa mai", "price": 150_000, "category_ids": []},
    ])
    monkeypatch.setattr(pricing_engine, "fetch_sold_items", lambda db: {
        P1: {"title": "Cốc sứ vẽ tay hoa sen", "price": 121_000, "qty": 3},  # bán đúng giá đang niêm yết
        P2: {"title": "Cốc sứ vẽ tay hoa mai", "price": 110_000, "qty": 2},  # đã bán giá cũ, nay đổi giá
        P3: {"title": "Cốc sứ vẽ tay hoa đào", "price": 99_000, "qty": 5},   # đã ngừng bán
    })
    idx.refresh_live(object())
    rows, _ = idx._live
    got = sorted((r["title"], r["price"], r["sold"], r.get("source", "vietcraft")) for r in rows)
    assert got == sorted([
        ("Cốc sứ vẽ tay hoa sen", 120_000, 3, "vietcraft"),
        ("Cốc sứ vẽ tay hoa mai", 150_000, 0, "vietcraft"),
        ("Cốc sứ vẽ tay hoa mai", 110_000, 2, "vietcraft_sold"),
        ("Cốc sứ vẽ tay hoa đào", 99_000, 5, "vietcraft_sold"),
    ])
    sources = {c.source for c in idx.search("Cốc sứ vẽ tay hoa")}
    assert {"vietcraft", "vietcraft_sold"} <= sources


def test_explanation_mentions_sold_on_platform():
    comps = [Comparable("Cốc sứ vẽ tay A", 100_000, 0.8, "vietcraft_sold", sold=2),
             Comparable("Cốc sứ vẽ tay B", 110_000, 0.7, "vietcraft", sold=1),
             Comparable("Cốc sứ vẽ tay C", 120_000, 0.6, "tiki")]
    est = ComparableEstimate(comparables=comps, p25=100_000, p50=110_000, p75=120_000, p90=120_000,
                             n_used=3, mean_similarity=0.7, confidence="medium")
    res = pricing_from_comparables(est)
    assert "2 sản phẩm đã bán thành công trên sàn" in res.explanation
    assert res.comparables[0].source == "Sàn VietCraft (giá đã bán)"
