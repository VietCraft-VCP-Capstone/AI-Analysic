import time

from bson import ObjectId

from app.core.f29 import review_stats
from tests.f29.fake_mongo import make_calculator

PRODUCT = ObjectId("507f1f77bcf86cd799439011")
OTHER = ObjectId("507f1f77bcf86cd799439012")
REAL = ObjectId()
SIM = ObjectId()


def _db(reviews):
    orders = [{"_id": REAL}, {"_id": SIM, "is_simulated": True}]
    return make_calculator(orders=orders, reviews=reviews).live_db


def test_product_counts_counts_only_real_order_reviews():
    db = _db([
        {"product_id": PRODUCT, "order_id": REAL, "rating": 5},
        {"product_id": PRODUCT, "order_id": REAL, "rating": 2},
        {"product_id": PRODUCT, "order_id": SIM, "rating": 5},
        {"product_id": OTHER, "order_id": REAL, "rating": 5},
    ])
    assert review_stats.product_counts(db, PRODUCT) == (1, 2)


def test_review_without_rating_is_skipped():
    db = _db([
        {"product_id": PRODUCT, "order_id": REAL, "rating": 5},
        {"product_id": PRODUCT, "order_id": REAL},
    ])
    assert review_stats.product_counts(db, PRODUCT) == (1, 1)
    assert review_stats.platform_p0(db) == 1.0


def test_platform_p0_cached_for_one_hour(monkeypatch):
    db = _db([{"product_id": PRODUCT, "order_id": REAL, "rating": 5}])
    assert review_stats.platform_p0(db) == 1.0
    db["reviews"].docs.append({"product_id": PRODUCT, "order_id": REAL, "rating": 1})
    assert review_stats.platform_p0(db) == 1.0
    later = time.monotonic() + review_stats.P0_TTL_SECONDS + 1
    monkeypatch.setattr(review_stats.time, "monotonic", lambda: later)
    assert review_stats.platform_p0(db) == 0.5
