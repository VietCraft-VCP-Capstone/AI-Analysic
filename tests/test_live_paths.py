import random
from datetime import datetime, timedelta, timezone

import pytest
from bson import ObjectId

from app.api.v1 import _live, _live_competitor, _live_data, _live_listing, _live_overview
from app.api.v1.f27_listing_timeseries import listing_timeseries
from app.api.v1.f28_conversion import conversion
from app.api.v1.f33_shop_comparison import shop_comparison
from app.api.v1.f34_tag_gap import tag_gap
from app.api.v1.f37_forecast_revenue import forecast_revenue
from app.api.v1._live_overview import overview_live
from tests.f29.fake_mongo import _FakeMongoClient

SHOP_A, SHOP_B = ObjectId(), ObjectId()
NOW = datetime.now(timezone.utc)


def _san_pham(shop, n, cat="Áo thun", tags=("áo",)):
    return [{"_id": ObjectId(), "shop_id": shop, "title": f"Áo {i}", "categories": [cat],
             "tags": list(tags), "average_rating": 4.5, "rating_count": 3, "status": "PUBLISHED"} for i in range(n)]


def _don(shop, pid, ngay_truoc, gia=100000.0):
    return {"_id": ObjectId(), "shop_id": shop, "created_at": NOW - timedelta(days=ngay_truoc),
            "payment_status": "PAID", "order_status": "DELIVERED",
            "items": [{"product_id": pid, "quantity": 1, "retail_price": gia}],
            "financial_breakdown": {"subtotal": gia}}


@pytest.fixture
def db(monkeypatch):
    fake = _FakeMongoClient()["vietcraft"]
    for mod in (_live, _live_data, _live_listing, _live_competitor, _live_overview):
        monkeypatch.setattr(mod, "db_live", lambda: fake)
    return fake


@pytest.fixture
def san(db):
    a, b = _san_pham(SHOP_A, 6), _san_pham(SHOP_B, 6, tags=("áo", "cotton"))
    db["products"].seed(a + b + [{**_san_pham(SHOP_A, 1)[0], "is_hidden": True}])
    db["product_variants"].seed([{"product_id": p["_id"], "retail_price": 150000, "is_active": True,
                                  "stock_quantity": 5} for p in a + b])
    db["shops"].seed([{"_id": SHOP_A, "shop_name": "A", "average_response_time_seconds": 600},
                      {"_id": SHOP_B, "shop_name": "B", "average_response_time_seconds": 60}])
    p = a[0]["_id"]
    db["product_events"].seed(
        [{"product_id": p, "event_type": "view", "created_at": NOW - timedelta(days=i % 20)} for i in range(40)]
        + [{"product_id": p, "event_type": "add_to_cart", "created_at": NOW - timedelta(days=1)}] * 8
        + [{"product_id": b[0]["_id"], "event_type": "view", "created_at": NOW - timedelta(days=2)}] * 10)
    db["orders"].seed([_don(SHOP_A, p, 1), _don(SHOP_A, p, 3),
                       {**_don(SHOP_A, p, 2), "order_status": "CANCELLED"}, _don(SHOP_B, b[0]["_id"], 2)])
    return a, b


def test_f28_pheu_tu_su_kien_va_don_that(san):
    r = conversion(str(san[0][0]["_id"]), shop_id=str(SHOP_A))
    assert r["data"]["funnel"] == {"views": 40, "carts": 8, "orders": 2}
    assert r["data"]["cart_to_order_pct"] == 25.0
    assert r["meta"]["source"]["mode"] == "live"


def test_f28_it_luot_xem_tra_insufficient_kem_tien_do(san):
    r = conversion(str(san[0][1]["_id"]), shop_id=str(SHOP_A))
    assert r["data"] is None and r["meta"]["unlock"]["current"] == 0


def test_f27_chuoi_ngay_va_trung_vi_danh_muc(san):
    r = listing_timeseries(str(san[0][0]["_id"]), shop_id=str(SHOP_A), timeRange="30d")
    assert r["data"]["totals"]["views"] == 40 and r["data"]["totals"]["orders"] == 2
    assert len(r["data"]["series"]) == 30 and len(r["data"]["category_median"]) == 30


def test_f27_san_pham_shop_khac_bi_chan(san):
    with pytest.raises(Exception):
        listing_timeseries(str(san[1][0]["_id"]), shop_id=str(SHOP_A), timeRange="30d")


def test_f33_so_sanh_voi_shop_that_cung_danh_muc(san):
    r = shop_comparison(shop_id=str(SHOP_A))
    assert [c["shop_id"] for c in r["data"]["competitors"]] == [str(SHOP_B)]
    assert r["data"]["me_raw"]["listing_count"] == 6


def test_f34_thieu_doi_thu_bao_tien_do(san):
    r = tag_gap(shop_id=str(SHOP_A), categoryId=None)
    assert r["data"] is None and r["meta"]["unlock"]["current"] == 6


def test_f37_du_lich_su_thi_chay_mo_hinh(db, san):
    p, nhieu = san[0][0]["_id"], random.Random(7)
    db["orders"].seed([_don(SHOP_A, p, d, 100000 + (d % 7) * 20000 + nhieu.gauss(0, 15000))
                       for d in range(1, 121)])
    f = forecast_revenue(shop_id=str(SHOP_A), targetId=None, window="30")
    assert len(f["data"]["points"]) == 30 and f["meta"]["source"]["mode"] == "live"


def test_f37_it_lich_su_insufficient(san):
    r = forecast_revenue(shop_id=str(SHOP_A), targetId=None, window="30")
    assert r["data"] is None and r["meta"]["unlock"]["target"] == 90


def test_f26_luot_xem_that(san):
    r = overview_live(str(SHOP_A), 30, "30d")
    assert r["data"]["kpi"]["views"]["value"] == 40
    assert r["data"]["kpi"]["conversion_pct"]["value"] == 5.0
