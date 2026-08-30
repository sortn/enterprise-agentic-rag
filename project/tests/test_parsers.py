from pathlib import Path

from ingestion.parsers import MultiFormatParser


class ParserSettings:
    max_upload_mb = 1


def test_markdown_heading_hierarchy(tmp_path: Path):
    path = tmp_path / "policy.md"
    path.write_text("# 总则\n内容A\n## 报销\n内容B", encoding="utf-8")
    parsed = MultiFormatParser(ParserSettings()).parse(path)
    assert [unit.heading for unit in parsed.units] == ["总则", "总则 > 报销"]
    assert parsed.source == "policy.md"
    assert len(parsed.doc_id) == 24


def test_rejects_unsupported_extension(tmp_path: Path):
    path = tmp_path / "unsafe.exe"
    path.write_text("test", encoding="utf-8")
    try:
        MultiFormatParser(ParserSettings()).parse(path)
    except ValueError as exc:
        assert "不支持" in str(exc)
    else:
        raise AssertionError("unsupported file should fail")
