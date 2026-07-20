from __future__ import annotations

from pathlib import Path

from test_watchdog_sync_documents import Store

from app.services.watchdog_runtime import normalize_watchdog_event
from app.services.watchdog_sync import apply_watchdog_event_batch


def test_watchdog_batch_uses_shared_audit_schema_without_raw_content(tmp_path: Path) -> None:
    path = tmp_path / "Finance" / "note.txt"
    path.parent.mkdir()
    path.write_text("raw file content that must not be in audit", encoding="utf-8")

    report = apply_watchdog_event_batch(tmp_path, [normalize_watchdog_event(tmp_path, "created", path)], store=Store())

    assert report.audit_status == "ok"
    assert report.audit_event_ids
    assert "raw file content" not in repr(report.as_dict())


def test_full_rebuild_required_report_contains_safe_failure_code(tmp_path: Path) -> None:
    path = tmp_path / "Finance" / "note.txt"
    path.parent.mkdir()
    path.write_text("x", encoding="utf-8")

    report = apply_watchdog_event_batch(
        tmp_path,
        [normalize_watchdog_event(tmp_path, "moved", tmp_path / "HR" / "note.txt", source_path=path)],
        store=Store(),
    )

    assert report.status == "full_rebuild_required"
    assert report.validation_errors[0]["code"] == "cross_scope_rename"
