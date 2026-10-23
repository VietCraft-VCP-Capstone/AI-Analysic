from pathlib import Path

import pytest

from app.core.f29 import price_ref, price_suggest, review_stats, weights
from tests.f29.fake_price import FakePriceModel

FIXTURE = Path(__file__).parent / "weights_fixture.json"


@pytest.fixture(autouse=True)
def health_weights(monkeypatch):
    monkeypatch.setattr(weights, "WEIGHTS_PATH", FIXTURE)
    weights.clear_cache()
    yield
    weights.clear_cache()


@pytest.fixture(autouse=True)
def fresh_p0():
    review_stats.clear_p0_cache()
    yield
    review_stats.clear_p0_cache()


@pytest.fixture(autouse=True)
def fresh_price_index():
    price_ref.clear_index_cache()
    yield
    price_ref.clear_index_cache()


@pytest.fixture(autouse=True)
def no_price_model(monkeypatch, tmp_path):
    monkeypatch.setattr(price_suggest, "MODEL_PATH", tmp_path / "price_model.joblib")


@pytest.fixture
def fake_price_model(monkeypatch):
    monkeypatch.setattr(price_suggest, "_load", lambda path: (FakePriceModel(), -0.2, 0.2))
