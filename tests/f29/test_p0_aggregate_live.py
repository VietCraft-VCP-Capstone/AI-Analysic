import uuid

import pytest
from bson import ObjectId
from pymongo import MongoClient
from pymongo.errors import PyMongoError

from app.core.f29 import review_stats

MONGO_URI = "mongodb://127.0.0.1:27017"


@pytest.fixture
def temp_db():
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=1000)
    try:
        client.admin.command("ping")
    except PyMongoError:
        client.close()
        pytest.skip("Mongo local không kết nối được")
    name = f"f29_test_p0_{uuid.uuid4().hex}"
    try:
        yield client[name]
    finally:
        client.drop_database(name)
        client.close()


def test_aggregate_p0_matches_fallback(temp_db):
    real_a, real_b, sim = ObjectId(), ObjectId(), ObjectId()
    temp_db["orders"].insert_many([
        {"_id": real_a},
        {"_id": real_b},
        {"_id": sim, "is_simulated": True},
    ])
    temp_db["reviews"].insert_many([
        {"order_id": real_a, "rating": 5},
        {"order_id": real_b, "rating": 2},
        {"order_id": sim, "rating": 5},
    ])
    assert review_stats._aggregate_p0(temp_db) == 0.5
