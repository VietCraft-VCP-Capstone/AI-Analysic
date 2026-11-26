import numpy as np
import pandas as pd
import pytest

from scripts.f29_price import train


def frame(n, prefix):
    words = ["balo", "ví", "giày", "áo", "nón", "túi"]
    return pd.DataFrame({
        "group": ["bags" if i % 2 else "shoes" for i in range(n)],
        "title": [f"{words[i % len(words)]} {prefix} {i}" for i in range(n)],
        "price": [1000 * (i % 7 + 1) + i for i in range(n)],
    })


def splits():
    return {
        "train": frame(60, "train"),
        "val": frame(20, "val"),
        "tiki23_test": frame(20, "t23"),
        "tiki26_test": frame(20, "t26"),
    }


class Perfect:
    def __init__(self, df):
        self.price = dict(zip(train.text(df), df["price"]))

    def predict(self, texts):
        return np.log([self.price[t] for t in texts])


def test_gate_needs_both_tests():
    good = {"mdape_model": 0.4, "mdape_group": 0.65}
    weak = {"mdape_model": 0.7, "mdape_group": 0.65}
    assert train.gate({"tiki23_test": good, "tiki26_test": weak}) is False
    assert train.gate({"tiki23_test": good, "tiki26_test": good}) is True


def test_evaluate_perfect_model():
    df = frame(30, "x")
    res = train.evaluate(Perfect(df), (-0.1, 0.1), df, train.group_median(df))
    assert res["mdape_model"] == pytest.approx(0, abs=1e-9)


def test_cli_writes_nothing_on_fail(monkeypatch, tmp_path):
    monkeypatch.setattr(train, "OUT", tmp_path)
    monkeypatch.setattr(train.data, "load", splits)
    monkeypatch.setattr(train, "gate", lambda metrics: False)
    with pytest.raises(SystemExit) as exc:
        train.main()
    assert exc.value.code == 2
    assert list(tmp_path.iterdir()) == []
