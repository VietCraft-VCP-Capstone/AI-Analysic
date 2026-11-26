import json

import pytest

from scripts.f29_health import report_price


def test_price_lines_empty_without_file(tmp_path):
    assert report_price.price_lines(tmp_path / "none.json") == []


@pytest.mark.parametrize("content", ["{not json", "[]", '{"metrics": {}}'])
def test_price_lines_skip_broken_file(tmp_path, content):
    path = tmp_path / "price_model.json"
    path.write_text(content, encoding="utf-8")
    assert report_price.price_lines(path) == []


def test_price_lines_show_metrics_and_limits(tmp_path):
    path = tmp_path / "price_model.json"
    metrics = {"tiki26_test": {"n": 782, "mdape_model": 0.49, "mdape_group": 0.6, "in_range": 0.38}}
    path.write_text(json.dumps({"metrics": metrics}), encoding="utf-8")
    text = "\n".join(report_price.price_lines(path))
    assert text.startswith("## 7. Mô hình gợi ý giá")
    assert "| tiki26_test | 782 | 0,490 | 0,600 | 38,0% |" in text
    assert "chỉ chứa 38% giá thật ở Tiki 2026" in text
