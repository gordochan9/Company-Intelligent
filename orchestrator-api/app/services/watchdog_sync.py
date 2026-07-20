from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Protocol

from app.schemas.audit_trace import AuditEventCategory, AuditEventStatus
from app.schemas.watchdog_runtime import WatchdogQueueItem
from app.schemas.watchdog_sync import WatchdogEvent, WatchdogSyncReport
from app.services.audit_trace import emit_audit_event
from app.services.source_file_parsers import SourceParseError, parse_rag_document
from app.services.structured_file_import import StructuredImportError, import_structured_file


class WatchdogSyncStore(Protocol):
    def refresh_document(self, relative_path: str, permission_scope_key: str, chunks: list[Any]) -> None:
        ...

    def delete_document(self, relative_path: str) -> None:
        ...

    def refresh_structured(self, relative_path: str, permission_scope_key: str, profiles: list[Any]) -> dict[str, Any]:
        ...

    def delete_structured(self, relative_path: str) -> None:
        ...

    def rename_path(self, source_relative_path: str, relative_path: str) -> None:
        ...


class WatchdogEventQueue:
    def __init__(self) -> None:
        self._items: dict[str, WatchdogQueueItem] = {}
        self._ambiguous = False

    def enqueue(self, item: WatchdogQueueItem) -> None:
        key = item.event.relative_path
        existing = self._items.get(key)
        if existing is None:
            self._items[key] = item
            return
        merged = _merge_events(existing, item)
        if merged is None:
            self._ambiguous = True
            self._items[key] = item
        else:
            self._items[key] = merged

    def drain(self) -> list[WatchdogQueueItem]:
        if self._ambiguous:
            return [
                WatchdogQueueItem(
                    event=WatchdogEvent(
                        event_type="modified",
                        relative_path="",
                        permission_scope_key="",
                        extension="",
                        file_kind="unsupported",
                        reason="ambiguous_event_sequence",
                    )
                )
            ]
        items = list(self._items.values())
        self._items.clear()
        return items


def apply_watchdog_event_batch(dataset_root: str | Path, items: list[WatchdogQueueItem], *, store: WatchdogSyncStore | None = None) -> WatchdogSyncReport:
    if store is None:
        return WatchdogSyncReport(status="failed", validation_errors=[_error("watchdog_store_not_configured", "Watchdog sync store is not configured.")])
    root = Path(dataset_root)
    report = WatchdogSyncReport(status="ok")
    for item in items:
        event_report = apply_watchdog_event(root, item, store=store)
        _merge_report(report, event_report)
        if event_report.full_rebuild_required:
            report.status = "full_rebuild_required"
            report.full_rebuild_required = True
    audit = emit_audit_event(
        request_id=None,
        trace_id=None,
        event_category=AuditEventCategory.WATCHDOG,
        event_type="watchdog_event_batch_applied",
        status=AuditEventStatus.SUCCEEDED if report.status in {"ok", "skipped"} else AuditEventStatus.VALIDATION_FAILED,
        workflow_name="watchdog_incremental_sync",
        node_name="apply_watchdog_event_batch",
        metadata={
            "processed_events": report.processed_events,
            "skipped_events": report.skipped_events,
            "full_rebuild_required": report.full_rebuild_required,
            "join_refresh_recommended": report.join_refresh_recommended,
        },
    )
    if audit.event:
        report.audit_status = "ok"
        report.audit_event_ids.append(audit.event.trace_id)
    return report


def apply_watchdog_event(dataset_root: Path, item: WatchdogQueueItem, *, store: WatchdogSyncStore) -> WatchdogSyncReport:
    event = item.event
    if event.reason == "ambiguous_event_sequence":
        return WatchdogSyncReport(status="full_rebuild_required", full_rebuild_required=True, validation_errors=[_error("ambiguous_event_sequence", "Watchdog event sequence is ambiguous.")])
    if event.reason == "cross_scope_rename":
        return WatchdogSyncReport(status="full_rebuild_required", full_rebuild_required=True, validation_errors=[_error("cross_scope_rename", "Cross-scope rename requires full rebuild.")])
    if event.reason == "temporary_file_skip" or event.file_kind == "unsupported":
        return WatchdogSyncReport(status="skipped", skipped_events=1, warnings=[_error("unsupported_skip", "Watchdog event was skipped safely.")])
    if event.event_type == "moved" and event.source_relative_path:
        store.rename_path(event.source_relative_path, event.relative_path)
        return WatchdogSyncReport(status="ok", processed_events=1)
    if event.event_type == "deleted":
        return _delete_event(event, store)
    path = item.path or dataset_root / event.relative_path
    if event.file_kind == "rag_document":
        return _refresh_document(path, event, store)
    if event.file_kind == "structured_table":
        return _refresh_structured(path, event, store)
    return WatchdogSyncReport(status="skipped", skipped_events=1)


def _refresh_document(path: Path, event: WatchdogEvent, store: WatchdogSyncStore) -> WatchdogSyncReport:
    try:
        chunks = parse_rag_document(path, safe_path=event.relative_path)
        store.refresh_document(event.relative_path, event.permission_scope_key, chunks)
        return WatchdogSyncReport(status="ok", processed_events=1, documents_refreshed=1)
    except SourceParseError as exc:
        return WatchdogSyncReport(status="validation_failed", processed_events=1, validation_errors=[_error(exc.code, "Document parser failed safely.")])


def _refresh_structured(path: Path, event: WatchdogEvent, store: WatchdogSyncStore) -> WatchdogSyncReport:
    try:
        if event.extension == ".csv":
            _validate_csv_header_for_watchdog(path)
        profiles = import_structured_file(path, relative_path=event.relative_path, permission_scope_key=event.permission_scope_key)
        result = store.refresh_structured(event.relative_path, event.permission_scope_key, profiles)
    except StructuredImportError as exc:
        return WatchdogSyncReport(status="validation_failed", processed_events=1, validation_errors=[_error(exc.code, "Structured import failed safely.")])
    if result.get("runtime_relation_validated") is False:
        return WatchdogSyncReport(status="full_rebuild_required", processed_events=1, full_rebuild_required=True, validation_errors=[_error("runtime_relation_validation_failed", "Structured runtime relation was not validated.")])
    return WatchdogSyncReport(
        status="ok",
        processed_events=1,
        structured_resources_refreshed=len(profiles),
        join_refresh_recommended=bool(result.get("columns_changed")),
    )


def _validate_csv_header_for_watchdog(path: Path) -> None:
    try:
        with path.open(newline="", encoding="utf-8-sig") as handle:
            headers = next(csv.reader(handle), [])
    except Exception as exc:
        raise StructuredImportError("csv_import_failed") from exc
    if not headers or any(not str(header).strip() for header in headers):
        raise StructuredImportError("invalid_structured_headers")
    if len(set(headers)) != len(headers):
        raise StructuredImportError("duplicate_structured_headers")


def _delete_event(event: WatchdogEvent, store: WatchdogSyncStore) -> WatchdogSyncReport:
    if event.file_kind == "rag_document":
        store.delete_document(event.relative_path)
        return WatchdogSyncReport(status="ok", processed_events=1, documents_deleted=1)
    if event.file_kind == "structured_table":
        store.delete_structured(event.relative_path)
        return WatchdogSyncReport(status="ok", processed_events=1, structured_resources_deleted=1, join_refresh_recommended=True)
    return WatchdogSyncReport(status="skipped", skipped_events=1)


def _merge_events(existing: WatchdogQueueItem, incoming: WatchdogQueueItem) -> WatchdogQueueItem | None:
    old = existing.event.event_type
    new = incoming.event.event_type
    if old == "created" and new == "modified":
        return existing
    if new == "deleted":
        return incoming
    if old == new:
        return incoming
    return None


def _merge_report(target: WatchdogSyncReport, source: WatchdogSyncReport) -> None:
    target.processed_events += source.processed_events
    target.skipped_events += source.skipped_events
    target.documents_refreshed += source.documents_refreshed
    target.documents_deleted += source.documents_deleted
    target.structured_resources_refreshed += source.structured_resources_refreshed
    target.structured_resources_deleted += source.structured_resources_deleted
    target.join_refresh_recommended = target.join_refresh_recommended or source.join_refresh_recommended
    target.validation_errors.extend(source.validation_errors)
    target.warnings.extend(source.warnings)
    if source.status not in {"ok", "skipped"} and target.status == "ok":
        target.status = source.status


def _error(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}
