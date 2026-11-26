import pandas as pd

from app.core.f29.material import has_material
from scripts.f29_health import run


def test_has_material_from_field():
    assert has_material({"materials": ["Len"]}) is True


def test_has_material_from_title():
    assert has_material({"materials": [], "title": "Khăn len đan tay"}) is True


def test_has_material_negation():
    assert has_material({"description": "không phải cotton"}) is False
    assert has_material({"description": "áo 100% cotton"}) is True
    assert has_material({"materials": ["len"]}) is True


def test_no_material():
    assert has_material({"title": "Mũ bucket thêu logo", "materials": None}) is False

def test_material_rate_splits_top25():
    df = pd.DataFrame({"title": ["Khăn len", "Mũ bucket", "Áo cotton"],
                       "description": [None, "thêu logo", None], "top25": [1, 1, 0]})
    assert run._material_rate(df) == {"share": 66.7, "top25_with": 50.0, "top25_without": 100.0}
