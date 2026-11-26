from scripts.f29_health import report


def test_write_keeps_case_study_section(tmp_path, monkeypatch):
    path = tmp_path / "report.md"
    path.write_text("# cũ\n\n## Case study VietCraft\n\nBảng cũ\n\n## Khác\nx\n", encoding="utf-8")
    monkeypatch.setattr(report, "_text", lambda payload: "# Mới\n")
    report.write(path, {})
    text = path.read_text(encoding="utf-8")
    assert text.startswith("# Mới")
    assert "## Case study VietCraft\n\nBảng cũ" in text
    assert "## Khác" not in text and "# cũ" not in text
