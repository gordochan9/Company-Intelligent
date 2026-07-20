from __future__ import annotations

from pathlib import Path

from app.services.source_catalog_dataset_rebuild import run_rebuild


def test_unknown_top_level_scope_fails_closed(tmp_path: Path) -> None:
    unknown = tmp_path / "Unknown"
    unknown.mkdir()
    (unknown / "file.txt").write_text("content", encoding="utf-8")

    report = run_rebuild(tmp_path, dry_run=True)

    assert report.status == "dry_run_failed"
    assert report.validation_errors == [{"path": "Unknown/file.txt", "code": "unknown_top_level_scope"}]


def test_report_uses_safe_relative_paths_only(tmp_path: Path) -> None:
    finance = tmp_path / "Finance"
    finance.mkdir()
    (finance / "ignore.exe").write_text("binary", encoding="utf-8")

    report = run_rebuild(tmp_path, dry_run=True).as_dict()

    assert str(tmp_path) not in repr(report)
    assert report["skipped_files"] == [{"path": "Finance/ignore.exe", "code": "unsupported_extension"}]


def test_rebuild_report_does_not_include_raw_file_content(tmp_path: Path) -> None:
    finance = tmp_path / "Finance"
    finance.mkdir()
    (finance / "policy.txt").write_text("sensitive raw content", encoding="utf-8")

    report = run_rebuild(tmp_path, dry_run=True).as_dict()

    assert "sensitive raw content" not in repr(report)
