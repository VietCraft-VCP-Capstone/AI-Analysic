from app.core.f29 import price_suggest
from tests.f29.fake_price import FakePriceModel


def test_suggest_none_without_model(monkeypatch, tmp_path):
    monkeypatch.setattr(price_suggest, "MODEL_PATH", tmp_path / "missing.joblib")
    assert price_suggest.suggest("Áo thun cotton", "fashion") is None


def test_suggest_none_for_broken_model(monkeypatch, tmp_path):
    (tmp_path / "broken.joblib").write_bytes(b"not a model")
    (tmp_path / "broken.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(price_suggest, "MODEL_PATH", tmp_path / "broken.joblib")
    assert price_suggest.suggest("Áo thun cotton", "fashion") is None


def test_suggest_none_when_predict_fails(monkeypatch):
    model = FakePriceModel(error=RuntimeError("boom"))
    monkeypatch.setattr(price_suggest, "_load", lambda path: (model, -0.2, 0.2))
    assert price_suggest.suggest("Áo thun cotton", "fashion") is None


def test_suggest_orders_low_mid_high(fake_price_model):
    out = price_suggest.suggest("Áo thun cotton", "fashion")
    assert out["low"] < out["mid"] < out["high"]
    assert out["mid"] == 100000


def test_suggest_floors_at_1000(monkeypatch):
    monkeypatch.setattr(price_suggest, "_load", lambda path: (FakePriceModel(price=100), -0.2, 0.2))
    assert price_suggest.suggest("Móc khóa", None) == {"low": 1000.0, "mid": 1000.0, "high": 1000.0}


def test_text_without_group_has_no_leading_space(monkeypatch):
    model = FakePriceModel()
    monkeypatch.setattr(price_suggest, "_load", lambda path: (model, -0.2, 0.2))
    price_suggest.suggest("  Móc khóa ", None)
    assert model.seen == [["Móc khóa"]]
