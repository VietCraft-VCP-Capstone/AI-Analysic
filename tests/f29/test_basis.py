import json
from pathlib import Path

from app.core.f29 import basis, weights

FIXTURE = Path(__file__).parent / "weights_fixture.json"


def test_basis_reads_tiki_auc_from_real_structure():
    out = basis.build(weights.load())
    assert out["tiki_test_auc"] == 0.567
    assert out["equal_auc"] == 0.566
    assert out["trained_on"] == "Olist, 1000 dòng, mốc 2017-06-01..2017-06-01"


def test_basis_keeps_rest_of_source_casing():
    data = json.loads(FIXTURE.read_text("utf-8"))
    data["trained_on"]["source"] = "olist (Brazil)"
    assert basis.build(data)["trained_on"].startswith("Olist (Brazil), ")


def test_basis_missing_metrics_gives_none():
    data = json.loads(FIXTURE.read_text("utf-8"))
    del data["metrics"]
    out = basis.build(data)
    assert out["tiki_test_auc"] is None and out["equal_auc"] is None
