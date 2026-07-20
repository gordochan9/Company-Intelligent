from __future__ import annotations

from pathlib import Path

from app.services.watchdog_runtime import normalize_watchdog_event
from app.services.watchdog_sync import WatchdogEventQueue


def _item(root: Path, event_type: str, relative: str):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x", encoding="utf-8")
    return normalize_watchdog_event(root, event_type, path)


def test_debounce_dedup_coalesces_created_modified_to_created(tmp_path: Path) -> None:
    queue = WatchdogEventQueue()
    queue.enqueue(_item(tmp_path, "created", "Finance/a.txt"))
    queue.enqueue(_item(tmp_path, "modified", "Finance/a.txt"))

    events = queue.drain()

    assert len(events) == 1
    assert events[0].event.event_type == "created"


def test_debounce_dedup_coalesces_modified_deleted_to_deleted(tmp_path: Path) -> None:
    queue = WatchdogEventQueue()
    queue.enqueue(_item(tmp_path, "modified", "Finance/a.txt"))
    queue.enqueue(_item(tmp_path, "deleted", "Finance/a.txt"))

    events = queue.drain()

    assert len(events) == 1
    assert events[0].event.event_type == "deleted"


def test_ambiguous_event_sequence_requires_full_rebuild(tmp_path: Path) -> None:
    queue = WatchdogEventQueue()
    queue.enqueue(_item(tmp_path, "deleted", "Finance/a.txt"))
    queue.enqueue(_item(tmp_path, "created", "Finance/a.txt"))

    events = queue.drain()

    assert events[0].event.reason == "ambiguous_event_sequence"
