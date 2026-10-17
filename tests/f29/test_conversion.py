from bson import ObjectId

from tests.f29.fake_mongo import make_calculator
from tests.f29.samples import NOW, PRODUCT_ID, base_product, conv_world, with_id


class TestConversionScore:
    def test_no_events_not_counted(self):
        calc = make_calculator()
        score, detail = calc._get_conversion(PRODUCT_ID)
        assert score is None
        assert detail["reason"] == "not_enough_views"
        assert detail["views_30d"] == 0 and detail["min_views"] == 100

    def test_below_view_threshold_not_counted(self):
        calc = conv_world(5, 200, 4, target_views=99, target_orders=5)
        score, detail = calc._get_conversion(PRODUCT_ID)
        assert score is None and detail["views_30d"] == 99

    def test_add_to_cart_events_are_not_views(self):
        oid = ObjectId(PRODUCT_ID)
        events = [{"product_id": oid, "event_type": "add_to_cart", "created_at": NOW} for _ in range(150)]
        calc = make_calculator(products=[{"_id": oid}], product_events=events)
        assert calc._get_conversion(PRODUCT_ID)[1]["views_30d"] == 0

    def test_not_enough_peers_not_counted(self):
        calc = conv_world(3, 200, 4, target_views=200, target_orders=4)
        score, detail = calc._get_conversion(PRODUCT_ID)
        assert score is None and detail["reason"] == "not_enough_peers"

    def test_equal_to_baseline_is_50(self):
        calc = conv_world(5, 200, 4, target_views=200, target_orders=4)
        score, detail = calc._get_conversion(PRODUCT_ID)
        assert score == 50.0
        assert detail["baseline_scope"] == "category"
        assert detail["conversion_rate"] == 0.02

    def test_double_baseline_capped_at_100(self):
        calc = conv_world(5, 200, 2, target_views=200, target_orders=12)
        assert calc._get_conversion(PRODUCT_ID)[0] == 100.0

    def test_cancelled_and_simulated_orders_ignored(self):
        oid = ObjectId(PRODUCT_ID)
        noise = [
            {"items": [{"product_id": oid}], "order_status": "CANCELLED", "created_at": NOW},
            {"items": [{"product_id": oid}], "order_status": "DELIVERED", "is_simulated": True, "created_at": NOW},
            {"items": [{"product_id": oid}], "order_status": "DELIVERED", "seed_ref": "x", "created_at": NOW},
        ]
        calc = conv_world(5, 200, 4, target_views=200, target_orders=4, extra_orders=noise)
        _, detail = calc._get_conversion(PRODUCT_ID)
        assert detail["orders_30d"] == 4

    def test_zero_orders_in_baseline_not_counted(self):
        calc = conv_world(5, 200, 0, target_views=200, target_orders=0)
        score, detail = calc._get_conversion(PRODUCT_ID)
        assert score is None and detail["reason"] == "no_orders_in_baseline"

    def test_falls_back_to_platform_baseline(self):
        calc = conv_world(5, 200, 4, target_views=200, target_orders=4)
        calc.live_db["products"].docs[0]["category_ids"] = ["cat_khac"]
        score, detail = calc._get_conversion(PRODUCT_ID)
        assert score == 50.0 and detail["baseline_scope"] == "platform"

    def test_calculate_includes_conversion_when_ready(self):
        calc = conv_world(5, 200, 4, target_views=200, target_orders=8)
        product = with_id(base_product(category_ids=["cat_a"]))
        calc.live_db["products"].docs[0] = product
        calc._conv_cache = None
        result = calc.calculate(PRODUCT_ID)
        assert "conversion" not in result["axes_missing"]
        assert result["axes"]["conversion"] is not None
        assert result["conversion_detail"]["views_30d"] == 200
