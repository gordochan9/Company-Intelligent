from __future__ import annotations

import os
from pathlib import Path

from app.schemas.watchdog_runtime import WatchdogQueueItem, WatchdogRuntimeReport
from app.schemas.watchdog_sync import WATCHDOG_EVENT_TYPES, WATCHDOG_SCOPE_BY_TOP_LEVEL, WatchdogEvent, file_kind_for_extension
from app.services.watchdog_sync import WatchdogEventQueue, apply_watchdog_event_batch


TEMP_PREFIXES = ("~$", ".")
TEMP_SUFFIXES = (".tmp", ".swp", ".part")


def normalize_watchdog_event(
    dataset_root: str | Path,
    event_type: str,
    path: str | Path,
    *,
    source_path: str | Path | None = None,
) -> WatchdogQueueItem:
    if event_type not in WATCHDOG_EVENT_TYPES:
        raise ValueError("unsupported_watchdog_event")
    root = Path(dataset_root).resolve()
    target = Path(path).resolve()
    source = Path(source_path).resolve() if source_path else None
    relative = _safe_relative(root, target)
    if _is_temporary(relative):
        event = WatchdogEvent(
            event_type=event_type,  # type: ignore[arg-type]
            relative_path=relative,
            permission_scope_key="",
            extension=Path(relative).suffix.lower(),
            file_kind="unsupported",
            reason="temporary_file_skip",
        )
        return WatchdogQueueItem(event=event, path=target, source_path=source)
    top_level = relative.split("/", 1)[0]
    scope = WATCHDOG_SCOPE_BY_TOP_LEVEL.get(top_level)
    if not scope:
        raise ValueError("unknown_top_level_scope")
    source_relative = _safe_relative(root, source) if source else None
    if source_relative and source_relative.split("/", 1)[0] != top_level:
        event = WatchdogEvent(
            event_type="moved",
            relative_path=relative,
            permission_scope_key=scope,
            extension=Path(relative).suffix.lower(),
            file_kind=file_kind_for_extension(Path(relative).suffix.lower()),
            source_relative_path=source_relative,
            reason="cross_scope_rename",
        )
        return WatchdogQueueItem(event=event, path=target, source_path=source)
    extension = Path(relative).suffix.lower()
    event = WatchdogEvent(
        event_type=event_type,  # type: ignore[arg-type]
        relative_path=relative,
        permission_scope_key=scope,
        extension=extension,
        file_kind=file_kind_for_extension(extension),
        source_relative_path=source_relative,
    )
    return WatchdogQueueItem(event=event, path=target, source_path=source)


def enqueue_watchdog_event(queue: WatchdogEventQueue, item: WatchdogQueueItem) -> None:
    queue.enqueue(item)


def run_watchdog_once(dataset_root: str | Path | None = None, *, store=None, dry_run: bool = False) -> WatchdogRuntimeReport:
    root = Path(dataset_root or os.getenv("CONTAINER_ACTIVE_DATASET_ROOT", "/app/active_dataset"))
    if not root.exists() or not root.is_dir():
        return WatchdogRuntimeReport(status="failed", validation_errors=[{"code": "active_dataset_root_missing", "message": "Active dataset root is unavailable."}])
    if dry_run:
        return WatchdogRuntimeReport(status="dry_run_ok")
    queue = WatchdogEventQueue()
    report = apply_watchdog_event_batch(root, queue.drain(), store=store)
    return WatchdogRuntimeReport(status=report.status, processed_events=report.processed_events, sync_report=report.as_dict())


def _safe_relative(root: Path, path: Path | None) -> str:
    if path is None:
        raise ValueError("missing_watchdog_path")
    try:
        relative = path.resolve().relative_to(root).as_posix()
    except ValueError as exc:
        raise ValueError("path_outside_active_dataset") from exc
    if ".." in Path(relative).parts:
        raise ValueError("path_traversal_rejected")
    return relative


def _is_temporary(relative_path: str) -> bool:
    name = Path(relative_path).name
    return name.startswith(TEMP_PREFIXES) or name.lower().endswith(TEMP_SUFFIXES)
