import pytest

from scripts.f29_health import run


def test_failed_gate_exits_2_and_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(run, "REPORT", tmp_path / "report.md")
    out = tmp_path / "weights.json"
    with pytest.raises(SystemExit) as exc:
        run._publish({"gate": {"passed": False}}, out)
    assert exc.value.code == 2
    assert not out.exists() and not (tmp_path / "report.md").exists()
