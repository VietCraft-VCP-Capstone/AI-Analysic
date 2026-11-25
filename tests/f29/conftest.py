from pathlib import Path

import pytest

from app.core.f29.score import image_check
from app.core.f29 import constants
from app.core.f29.score import peers
from app.core.f29.score import price
from app.core.f29.score import text_rules
from app.core.f29.checks import run
from app.core.f29.score.scoring import normalize_image
from tests.f29.fake_mongo import _FakeDB

FIXTURE = Path(__file__).parent / "weights_fixture.json"


@pytest.fixture(autouse=True)
def health_weights(monkeypatch):
    monkeypatch.setattr(constants, "WEIGHTS_PATH", FIXTURE)
    constants.clear_cache()
    yield
    constants.clear_cache()


@pytest.fixture(autouse=True)
def fixed_price_params(monkeypatch):
    monkeypatch.setattr(text_rules, "price_params", lambda: text_rules.DEFAULT_PARAMS)


@pytest.fixture(autouse=True)
def fresh_p0():
    peers.clear_p0_cache()
    yield
    peers.clear_p0_cache()


@pytest.fixture(autouse=True)
def fresh_price_index():
    price.clear_index_cache()
    yield
    price.clear_index_cache()


def fake_analyze(urls, fetch=None, budget=None):
    uniq = {normalize_image(u) for u in urls} - {""}
    return {"state": "scored" if uniq else "seller_missing", "useful": len(uniq), "images": [],
            "method": "heuristic"}


@pytest.fixture(autouse=True)
def no_image_io(monkeypatch):
    monkeypatch.setattr(image_check, "analyze", fake_analyze)


@pytest.fixture(autouse=True)
def fake_store(monkeypatch):
    db = _FakeDB()
    monkeypatch.setattr(constants, "store_db", lambda: db)
    monkeypatch.setattr(run, "rgba", lambda url: None)
    monkeypatch.setattr(run, "embed", lambda img: None)
    monkeypatch.setattr(run, "txt", lambda title: None)
    return db
