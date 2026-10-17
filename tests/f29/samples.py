from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from bson import ObjectId

from tests.f29.fake_mongo import make_calculator

NOW = datetime.now(timezone.utc)
PRODUCT_ID = "507f1f77bcf86cd799439011"


def base_product(**overrides) -> Dict[str, Any]:
    p = {
        "_id_str": PRODUCT_ID,
        "title": "Áo thun cotton local brand unisex form rộng",
        "description": "Áo thun chất liệu cotton 100% thoáng mát, form unisex form rộng, "
                        "in hoạ tiết độc quyền, phù hợp mặc hàng ngày lẫn đi chơi, dễ phối đồ, "
                        "giặt máy không lo phai màu hay co rút, đường may chắc chắn tỉ mỉ.",
        "images": ["i1.jpg", "i2.jpg", "i3.jpg", "i4.jpg", "i5.jpg"],
        "tags": ["áo thun", "unisex", "local brand"],
        "categories": ["Thời trang"],
        "category_ids": ["cat_ao_thun"],
        "product_type": "READY_TO_SHIP",
        "moderation_status": "APPROVED",
        "weight_g": 250,
        "dimensions_cm": {"length": 30, "width": 20, "height": 5},
        "updated_at": NOW - timedelta(days=5),
    }
    p.update(overrides)
    return p


def with_id(doc: Dict[str, Any], oid_str: str = PRODUCT_ID) -> Dict[str, Any]:
    d = dict(doc)
    d.pop("_id_str", None)
    d["_id"] = ObjectId(oid_str)
    return d


def conv_world(n_peers: int, views_each: int, orders_each: int, *, target_views: int,
               target_orders: int, category: str = "cat_a", extra_orders=None):
    products, events, orders = [], [], []

    def add(oid, n_views, n_orders):
        products.append({"_id": oid, "category_ids": [category]})
        events.extend({"product_id": oid, "event_type": "view", "created_at": NOW - timedelta(days=1)}
                      for _ in range(n_views))
        orders.extend({"_id": ObjectId(), "items": [{"product_id": oid}], "order_status": "DELIVERED",
                       "created_at": NOW - timedelta(days=2)} for _ in range(n_orders))

    add(ObjectId(PRODUCT_ID), target_views, target_orders)
    for i in range(n_peers):
        add(ObjectId(f"{i + 1:024x}"), views_each, orders_each)
    orders.extend(extra_orders or [])
    return make_calculator(products=products, product_events=events, orders=orders)
