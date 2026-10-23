import pytest
from bson import ObjectId
from fastapi.testclient import TestClient

from app.api.v1 import f29_health
from app.core.f29 import weights
from app.core.f29.preview import preview_health
from tests.f29.fake_mongo import make_calculator
from tests.f29.samples import PRODUCT_ID, base_product, with_id

SHOP_ID = "64b000000000000000000001"
OTHER_SHOP = "64b000000000000000000002"


def _calc(product=None, variants=None, **seed):
    product = product or with_id(base_product(shop_id=ObjectId(SHOP_ID)))
    if variants is None:
        variants = [{"product_id": product["_id"], "is_active": True, "stock_quantity": 5,
                     "retail_price": "150000", "base_cost": "80000"}]
    return make_calculator(products=[product], product_variants=variants, **seed)


def _ref_price(calc):
    return next(r for r in calc.calculate(PRODUCT_ID)["breakdown"] if r["key"] == "price")["peer_median"]


class TestPreviewHealth:
    def test_no_overrides_matches_current(self):
        calc = _calc()
        result = preview_health(calc, PRODUCT_ID, {})
        assert result["delta_vs_current"] == 0.0
        assert result["score"] == result["current_score"] == calc.calculate(PRODUCT_ID)["score"]
        assert result["inputs"] == result["current_inputs"]

    def test_preview_price_lever(self):
        calc = _calc()
        result = preview_health(calc, PRODUCT_ID, {"price": 3 * _ref_price(calc)})
        assert result["axes"]["price"] == 0.0
        assert result["delta_vs_current"] < 0

    def test_removing_images_lowers_score(self):
        calc = _calc()
        result = preview_health(calc, PRODUCT_ID, {"n_images": 0})
        assert result["delta_vs_current"] < 0
        assert result["inputs"]["n_images"] == 0
        assert "image" in result["axes_missing"]

    def test_preview_equals_recalculated_score(self):
        calc = _calc()
        result = preview_health(calc, PRODUCT_ID, {"n_images": 6, "description_length": 570, "n_tags": 3})
        product = with_id(base_product(shop_id=ObjectId(SHOP_ID),
                                       images=[f"i{i}.jpg" for i in range(6)], description="x" * 570))
        assert result["score"] == _calc(product=product).calculate(PRODUCT_ID)["score"]

    def test_seed_or_missing_listing_returns_none(self):
        seed = with_id(base_product(seed_ref="seed_1"))
        assert preview_health(make_calculator(products=[seed]), PRODUCT_ID, {}) is None
        assert preview_health(make_calculator(), PRODUCT_ID, {}) is None

    def test_no_weights_returns_error(self, monkeypatch, tmp_path):
        monkeypatch.setattr(weights, "WEIGHTS_PATH", tmp_path / "none.json")
        weights.clear_cache()
        assert preview_health(_calc(), PRODUCT_ID, {}) == {"error": "no_weights"}

    def test_never_writes(self):
        calc = _calc(listing_health_scores=[{"product_id": ObjectId(PRODUCT_ID), "score": 1.0}])
        before = [dict(d) for d in calc.live_db["listing_health_scores"].docs]

        def _no_write(*_a, **_kw):
            raise AssertionError("preview không được ghi Mongo")

        for coll in calc.live_db.values():
            coll.update_one = _no_write
        preview_health(calc, PRODUCT_ID, {"n_images": 1, "price": 1000})
        assert calc.live_db["listing_health_scores"].docs == before


class TestPreviewEndpoint:
    @pytest.fixture
    def client(self, monkeypatch):
        from app.main import app
        calc = _calc()
        monkeypatch.setenv("DEV_TRUST_SHOP_HEADER", "1")
        monkeypatch.setenv("DEV_SHOP_ID", "")
        monkeypatch.setattr(f29_health, "db_live", lambda: calc.live_db)
        monkeypatch.setattr(f29_health, "HealthScoreCalculator", lambda: calc)
        return TestClient(app, raise_server_exceptions=False)

    def _post(self, client, body, shop=SHOP_ID, pid=PRODUCT_ID):
        return client.post(f"/api/analytics/listings/{pid}/health/preview", json=body,
                           headers={"X-Debug-Shop-Id": shop})

    def test_ok_envelope(self, client):
        r = self._post(client, {"n_images": 6})
        assert r.status_code == 200
        body = r.json()
        assert body["meta"]["status"] == "ok"
        assert body["meta"]["model_version"] == "health-2.1"
        assert body["data"]["delta_vs_current"] > 0

    def test_other_shop_forbidden(self, client):
        assert self._post(client, {}, shop=OTHER_SHOP).status_code == 403

    def test_unknown_listing_404(self, client):
        assert self._post(client, {}, pid="64b0000000000000000000ff").status_code == 404

    @pytest.mark.parametrize("body", [{"n_images": -1}, {"price": -5}, {"n_tags": "x"}])
    def test_invalid_body_rejected(self, client, body):
        assert self._post(client, body).status_code in (400, 422)
