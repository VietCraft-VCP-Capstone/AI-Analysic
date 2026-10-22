import json
from pathlib import Path

import pytest

from app.core.f29 import weights

FIXTURE = Path(__file__).parent / "weights_fixture.json"


def test_load_reads_fixture():
    data = weights.load(FIXTURE)
    assert sum(data["weights"].values()) == 100
    assert data["model_version"] == "health-2.0"


def test_load_missing_raises(tmp_path):
    with pytest.raises(RuntimeError):
        weights.load(tmp_path / "missing.json")


def test_load_bad_sum_raises(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"weights": {"image": 27, "description": 13, "tags": 10,
                                            "review": 5, "price": 35}}))
    with pytest.raises(RuntimeError):
        weights.load(path)


def test_load_missing_fields_raises(tmp_path):
    base = json.loads(FIXTURE.read_text("utf-8"))
    cases = [
        {**base, "weights": {"image": 27, "description": 13, "review": 5, "price": 55}},
        {**base, "targets": {"image": 6, "description": 570}},
        {**base, "review": {}},
        {**base, "price": {"full_at": 1.0, "zero_at": 2.0}},
    ]
    for i, data in enumerate(cases):
        path = tmp_path / f"broken{i}.json"
        path.write_text(json.dumps(data))
        with pytest.raises(RuntimeError):
            weights.load(path)
