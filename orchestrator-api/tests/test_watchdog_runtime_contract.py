from __future__ import annotations

from pathlib import Path

import pytest

from app.schemas.watchdog_sync import supported_extensions
from app.services.watchdog_runtime import normalize_watchdog_event


def test_path_normalization_accepts_valid_active_dataset_file(tmp_path: Path) -> None:
    path = tmp_path / "Finance" / "note.txt"
    path.parent.mkdir()
    path.write_text("hello", encoding="utf-8")

    item = normalize_watchdog_event(tmp_path, "created", path)

    assert item.event.relative_path == "Finance/note.txt"
    assert item.event.permission_scope_key == "finance"
    assert item.event.file_kind == "rag_document"


def test_path_normalization_rejects_path_outside_root(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("x", encoding="utf-8")

    with pytest.raises(ValueError, match="path_outside_active_dataset"):
        normalize_watchdog_event(tmp_path, "created", outside)


def test_path_normalization_rejects_unknown_top_level_folder(tmp_path: Path) -> None:
    path = tmp_path / "Unknown" / "note.txt"
    path.parent.mkdir()
    path.write_text("hello", encoding="utf-8")

    with pytest.raises(ValueError, match="unknown_top_level_scope"):
        normalize_watchdog_event(tmp_path, "created", path)


def test_supported_extension_registry_matches_dataset_rebuild() -> None:
    assert supported_extensions() == {".md", ".txt", ".pdf", ".docx", ".csv", ".xlsx"}


def test_temp_file_event_is_skipped_safely(tmp_path: Path) -> None:
    path = tmp_path / "Finance" / "~$draft.docx"
    path.parent.mkdir()
    path.write_text("temp", encoding="utf-8")

    item = normalize_watchdog_event(tmp_path, "created", path)

    assert item.event.reason == "temporary_file_skip"
    assert item.event.file_kind == "unsupported"
