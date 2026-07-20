from __future__ import annotations

from pathlib import Path

import pytest

from app.services.watchdog_runtime import normalize_watchdog_event


def test_host_absolute_path_is_not_emitted_in_event_payload(tmp_path: Path) -> None:
    path = tmp_path / "Finance" / "safe.txt"
    path.parent.mkdir()
    path.write_text("secret token DATABASE_URL", encoding="utf-8")

    item = normalize_watchdog_event(tmp_path, "created", path)

    assert str(tmp_path) not in repr(item.event)
    assert item.event.relative_path == "Finance/safe.txt"


def test_permission_scope_comes_from_top_level_folder_not_file_content(tmp_path: Path) -> None:
    path = tmp_path / "HR" / "note.txt"
    path.parent.mkdir()
    path.write_text("finance", encoding="utf-8")

    item = normalize_watchdog_event(tmp_path, "created", path)

    assert item.event.permission_scope_key == "hr"


def test_unknown_top_level_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "Secrets" / "note.txt"
    path.parent.mkdir()
    path.write_text("x", encoding="utf-8")

    with pytest.raises(ValueError, match="unknown_top_level_scope"):
        normalize_watchdog_event(tmp_path, "created", path)
