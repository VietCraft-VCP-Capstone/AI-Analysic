import sys
from pathlib import Path

import pytest

from app.core.f29 import weights
from scripts.f29_health import case_study
from tests.f29.fake_mongo import make_calculator
from tests.f29.samples import base_product, with_id

FIXTURE = Path(__file__).parents[1] / "f29" / "weights_fixture.json"


@pytest.fixture(autouse=True)
def fixture_weights(monkeypatch):
    monkeypatch.setattr(weights, "WEIGHTS_PATH", FIXTURE)


def _calc(*products):
    variants = [{"product_id": p["_id"], "is_active": True, "retail_price": "150000", "base_cost": "80000"}
                for p in products]
    return make_calculator(products=list(products), product_variants=variants)


@pytest.mark.parametrize("code,target,breakdown,expected", [
    ("image", 6, [], {"n_images": 6}),
    ("description", 570, [], {"description_length": 570}),
    ("tags", 3, [], {"n_tags": 3}),
    ("price", 274000, [{"key": "price", "reference": {"price": 274000}}], {"price": 274000}),
    ("review", 0, [], {}),
])
def test_fix_top_todo(code, target, breakdown, expected):
    result = {"todos": [{"code": code, "target": target}], "breakdown": breakdown}
    assert case_study.fix_top_todo(result) == expected


def test_fix_skips_todo_without_preview_lever():
    result = {"todos": [{"code": "material", "target": 1}, {"code": "tags", "target": 3}], "breakdown": []}
    assert case_study.fix_top_todo(result) == {"n_tags": 3}


@pytest.mark.parametrize("code,target,body,expected", [
    ("image", 6, {"n_images": 6}, "Thêm ảnh lên 6"),
    ("description", 570, {"description_length": 570}, "Viết mô tả đủ 570 ký tự"),
    ("tags", 3, {"n_tags": 3}, "Chọn đủ 3 tag"),
    ("price", 274000, {"price": 274000}, "Đặt giá bằng mức tham chiếu 274.000đ"),
])
def test_action_says_what_to_do(code, target, body, expected):
    todo = {"code": code, "target": target, "message": "chẩn đoán"}
    assert case_study._action(todo, body) == expected

def test_markdown_names_database():
    assert "db `vietcraft-test` (chỉ đọc)" in case_study.markdown([], "vietcraft-test")


def test_empty_run_exits_without_touching_report(monkeypatch, tmp_path, capsys):
    path = tmp_path / "report.md"
    path.write_text("## Case study VietCraft\n\nBảng cũ\n", encoding="utf-8")
    calc = _calc(with_id(base_product()))
    calc.live_db.name = "vietcraft-test"
    monkeypatch.setattr(weights, "WEIGHTS_PATH", tmp_path / "none.json")
    monkeypatch.setattr(case_study, "HealthScoreCalculator", lambda: calc)
    monkeypatch.setattr(case_study, "REPORT", path)
    monkeypatch.setattr(sys, "argv", ["case_study"])
    with pytest.raises(SystemExit) as exc:
        case_study.main()
    assert exc.value.code == 2
    assert path.read_text(encoding="utf-8") == "## Case study VietCraft\n\nBảng cũ\n"
    assert "vietcraft-test" in capsys.readouterr().out
