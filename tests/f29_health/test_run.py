import sys

import pytest

from scripts.f29_health import run, shopee


def test_failed_gate_exits_2_and_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(run, "REPORT", tmp_path / "report.md")
    out = tmp_path / "weights.json"
    with pytest.raises(SystemExit) as exc:
        run._publish({"gate": {"passed": False}}, out)
    assert exc.value.code == 2
    assert not out.exists() and not (tmp_path / "report.md").exists()


def test_run_stops_without_shopee(tmp_path, monkeypatch):
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setattr(shopee, "SHOPEE_DIR", empty)
    monkeypatch.setattr(run, "REPORT", tmp_path / "report.md")
    out = tmp_path / "weights.json"
    monkeypatch.setattr(sys, "argv", ["run", "--out", str(out)])
    with pytest.raises(SystemExit) as exc:
        run.main()
    assert exc.value.code == 2
    assert not out.exists() and not (tmp_path / "report.md").exists()
