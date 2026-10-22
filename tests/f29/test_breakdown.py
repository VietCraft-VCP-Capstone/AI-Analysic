import pytest

from app.core.f29 import weights
from app.core.f29.breakdown import build
from app.core.f29.todos import build_todos

TARGETS = {"image": 6, "description": 570, "tags": 3, "review": None, "price": None}
EXTRA = {"tags": {"pending": 0}, "review": {"n_good": 0}, "price": {"reference": {}}}


def _rows(subs, values, missing=()):
    w = weights.load()["weights"]
    return build(subs, values, TARGETS, {}, set(missing), w, EXTRA)


def test_breakdown_points_sum_to_score():
    subs = {"image": 50.0, "description": 100.0, "tags": 0.0, "review": 0.0, "price": 100.0}
    values = {"image": 3, "description": 570, "tags": 0, "review": 0, "price": 150000.0}
    rows, score = _rows(subs, values, missing={"tags", "review"})
    assert [r["points"] for r in rows] == [13.5, 13.0, 0.0, 0.0, 45.0]
    assert score == 71.5


def test_todo_impact_exact_and_sorted():
    subs = {"image": 50.0, "description": 100.0, "tags": 0.0, "review": 0.0, "price": 100.0}
    values = {"image": 3, "description": 570, "tags": 0, "review": 0, "price": 150000.0}
    rows, _ = _rows(subs, values, missing={"tags", "review"})
    todos = build_todos(rows)
    assert [t["field"] for t in todos] == ["image", "tags", "review"]
    assert [t["impact"] for t in todos] == [13.5, 10.0, 5.0]
    assert todos[0]["message"].startswith("Thêm 3 ảnh")


def test_price_todo_message_shows_gap_and_source():
    subs = {"image": 100.0, "description": 100.0, "tags": 100.0, "review": 100.0, "price": 50.0}
    values = {"image": 6, "description": 570, "tags": 3, "review": 5, "price": 150000.0}
    reference = {"price": 100000.0, "source": "category", "n": 8}
    w = weights.load()["weights"]
    rows, _ = build(subs, values, TARGETS, {}, set(), w, {"price": {"reference": reference}})
    todo = build_todos(rows)[0]
    assert todo["message"] == "Giá cao hơn 50% so với mức giữa trong cùng danh mục (100.000đ)"


@pytest.mark.parametrize("sub", [0.0, 12.34, 37.37, 37.25, 62.5, 88.8])
def test_impact_equals_real_score_gain(sub):
    w = {"image": 28, "description": 12, "tags": 10, "review": 5, "price": 45}
    base = {"image": sub, "description": 100.0, "tags": 100.0, "review": 100.0, "price": 100.0}
    values = {"image": 4, "description": 570, "tags": 3, "review": 5, "price": 150000.0}
    rows, before = build(base, values, TARGETS, {}, set(), w, {})
    todo = next(t for t in build_todos(rows) if t["field"] == "image")
    _, after = build({**base, "image": 100.0}, values, TARGETS, {}, set(), w, {})
    assert round(after - before, 1) == todo["impact"]


def test_zero_impact_todo_is_dropped():
    w = {"image": 28, "description": 12, "tags": 10, "review": 5, "price": 45}
    subs = {"image": 99.9, "description": 100.0, "tags": 100.0, "review": 100.0, "price": 100.0}
    values = {"image": 6, "description": 570, "tags": 3, "review": 5, "price": 150000.0}
    rows, _ = build(subs, values, TARGETS, {}, set(), w, {})
    assert build_todos(rows) == []
