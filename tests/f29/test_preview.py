"""Xem điểm nếu sửa (§4.3): chấm lại với giá trị giả định, chỉ đọc."""

from datetime import timedelta

import pytest
from bson import ObjectId
from fastapi.testclient import TestClient

from app.api.v1 import f29_health
from app.core.f29 import scoring
from app.core.f29.preview import apply_overrides, preview_health
from tests.f29.fake_mongo import make_calculator
from tests.f29.samples import NOW, PRODUCT_ID, base_product, with_id

SHOP_ID = "64b000000000000000000001"
OTHER_SHOP = "64b000000000000000000002"


def _calc(product=None, variants=None, **seed):
    product = product or with_id(base_product(shop_id=ObjectId(SHOP_ID)))
    if variants is None:
        variants = [{"product_id": product["_id"], "is_active": True, "stock_quantity": 5},
                    {"product_id": product["_id"], "is_active": True, "stock_quantity": 0}]
    return make_calculator(products=[product], product_variants=variants, **seed)


class TestApplyOverrides:
    AXES = {"conversion": None, "rating": None, "content": 60.0, "inventory": 50.0, "freshness": 40.0}
    INPUTS = {"n_images": 2, "description_length": 150, "n_tags": 3, "in_stock_ratio_pct": 50.0}

    def test_no_overrides_keeps_axes(self):
        out = apply_overrides(self.AXES, self.INPUTS, {})
        assert out["axes"] == self.AXES
        assert out["ignored"] == []

    def test_content_override_uses_engine_formula_and_resets_freshness(self):
        out = apply_overrides(self.AXES, self.INPUTS, {"n_images": 5})
        comps = scoring.content_component_scores(5, 150, 3)
        assert out["axes"]["content"] == round(scoring.content_axis_score(comps), 1) == 100.0
        assert out["axes"]["freshness"] == 100.0
        assert out["axes"]["inventory"] == 50.0

    def test_same_value_is_not_an_edit(self):
        out = apply_overrides(self.AXES, self.INPUTS, {"n_images": 2})
        assert out["axes"]["freshness"] == 40.0

    def test_stock_override_clamped(self):
        out = apply_overrides(self.AXES, self.INPUTS, {"in_stock_ratio_pct": 100})
        assert out["axes"]["inventory"] == 100.0
        assert out["axes"]["content"] == 60.0

    def test_stock_override_ignored_when_inventory_na(self):
        axes = {**self.AXES, "inventory": None}
        out = apply_overrides(axes, {**self.INPUTS, "in_stock_ratio_pct": None}, {"in_stock_ratio_pct": 90})
        assert out["axes"]["inventory"] is None
        assert out["ignored"] == ["in_stock_ratio_pct"]

    def test_unknown_keys_dropped(self):
        out = apply_overrides(self.AXES, self.INPUTS, {"price": 1})
        assert out["axes"] == self.AXES


class TestPreviewHealth:
    def test_no_overrides_matches_current(self):
        calc = _calc()
        result = preview_health(calc, PRODUCT_ID, {})
        assert result["delta_vs_current"] == 0.0
        assert result["score"] == result["current_score"] == calc.calculate(PRODUCT_ID)["score"]
        assert result["current_inputs"] == {"n_images": 5, "description_length": result["current_inputs"]["description_length"],
                                            "n_tags": 3, "in_stock_ratio_pct": 50.0}

    def test_restock_raises_score_by_engine_total(self):
        calc = _calc()
        current = calc.calculate(PRODUCT_ID)
        result = preview_health(calc, PRODUCT_ID, {"in_stock_ratio_pct": 100})
        expected = scoring.total_score({**current["axes"], "inventory": 100.0})
        assert result["score"] == expected
        assert result["delta_vs_current"] == round(expected - current["score"], 1) > 0
        assert result["status"] == scoring.status_from_score(expected)

    def test_removing_images_lowers_score(self):
        calc = _calc()
        result = preview_health(calc, PRODUCT_ID, {"n_images": 0})
        assert result["delta_vs_current"] < 0
        assert result["inputs"]["n_images"] == 0

    def test_stale_listing_gets_fresh_on_content_edit(self):
        product = with_id(base_product(shop_id=ObjectId(SHOP_ID), images=["a.jpg"],
                                       updated_at=NOW - timedelta(days=300)))
        calc = _calc(product=product)
        current = calc.calculate(PRODUCT_ID)
        assert current["axes"]["freshness"] < 100
        result = preview_health(calc, PRODUCT_ID, {"n_images": 5})
        assert result["axes"]["freshness"] == 100.0
        assert result["axes"]["content"] == 100.0

    def test_seed_or_missing_listing_returns_none(self):
        seed = with_id(base_product(seed_ref="seed_1"))
        assert preview_health(make_calculator(products=[seed]), PRODUCT_ID, {}) is None
        assert preview_health(make_calculator(), PRODUCT_ID, {}) is None

    def test_never_writes(self):
        calc = _calc(listing_health_scores=[{"product_id": ObjectId(PRODUCT_ID), "score": 1.0}])
        before = [dict(d) for d in calc.live_db["listing_health_scores"].docs]

        def _no_write(*_a, **_kw):
            raise AssertionError("preview không được ghi Mongo")

        for coll in calc.live_db.values():
            coll.update_one = _no_write
        preview_health(calc, PRODUCT_ID, {"n_images": 1, "in_stock_ratio_pct": 100})
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
        r = self._post(client, {"in_stock_ratio_pct": 100})
        assert r.status_code == 200
        body = r.json()
        assert body["meta"]["status"] == "ok"
        assert body["data"]["delta_vs_current"] > 0

    def test_other_shop_forbidden(self, client):
        assert self._post(client, {}, shop=OTHER_SHOP).status_code == 403

    def test_unknown_listing_404(self, client):
        assert self._post(client, {}, pid="64b0000000000000000000ff").status_code == 404

    @pytest.mark.parametrize("body", [{"n_images": -1}, {"in_stock_ratio_pct": 101}, {"n_tags": "x"}])
    def test_invalid_body_rejected(self, client, body):
        assert self._post(client, body).status_code in (400, 422)
