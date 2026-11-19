from pathlib import Path

import pytest

from app.core.f29 import image_check, price_ref, price_suggest, review_stats, weights
from app.core.f29.scoring import normalize_image
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


def fake_analyze(urls, title, group, fetch=None, budget=None):
    uniq = {normalize_image(u) for u in urls} - {""}
    return {"state": "scored" if uniq else "seller_missing", "useful": len(uniq), "images": [],
            "method": "heuristic"}


@pytest.fixture(autouse=True)
def no_image_io(monkeypatch):
    monkeypatch.setattr(image_check, "analyze", fake_analyze)
