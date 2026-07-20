from __future__ import annotations

import hashlib
import json
import os
import re
from typing import Any
from uuid import uuid4

from app.schemas.audit_trace import (
    AuditEmitResult,
    AuditEvent,
    AuditEventCategory,
    AuditEventSeverity,
    AuditEventStatus,
    AuditFailure,
    AuditTimelineRow,
    TraceEntry,
)


REDACTED = "[REDACTED]"
HASHED_PREFIX = "sha256:"

SECRET_KEY_RE = re.compile(
    r"(secret|token|password|api[_-]?key|authorization|cookie|database[_-]?url|raw[_-]?acl|raw[_-]?headers)",
    re.IGNORECASE,
)
PATH_OR_DSN_RE = re.compile(
    r"(?:[A-Za-z]:\\Users\\[^\s,;]+|/Users/[^\s,;]+|/mnt/c/Users/[^\s,;]+|file://[^\s,;]+|postgres(?:ql)?://[^\s,;]+)",
    re.IGNORECASE,
)
KEY_REQUIRES_HASH_RE = re.compile(r"(^|_)(user|source|chunk|catalog_entry|document|resource)_?id$", re.IGNORECASE)
SQL_KEY_RE = re.compile(r"(^|_)(sql|raw_sql|candidate_sql|validated_sql|rejected_sql)$", re.IGNORECASE)


def new_request_id() -> str:
    return str(uuid4())


def new_trace_id() -> str:
    return str(uuid4())


def hash_identifier(value: Any) -> str:
    return HASHED_PREFIX + hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def _sanitize_string(value: str) -> str:
    if PATH_OR_DSN_RE.search(value):
        return REDACTED
    if re.search(r"sk-[A-Za-z0-9_-]{8,}", value):
        return REDACTED
    return value


def sanitize_metadata(metadata: dict[str, Any] | None, *, allow_raw_sql: bool = False) -> dict[str, Any]:
    if not metadata:
        return {}

    def sanitize_value(key: str, value: Any) -> Any:
        if SECRET_KEY_RE.search(key):
            return REDACTED
        if SQL_KEY_RE.search(key) and not allow_raw_sql:
            return REDACTED
        if KEY_REQUIRES_HASH_RE.search(key):
            return hash_identifier(value)
        if isinstance(value, dict):
            return {str(child_key): sanitize_value(str(child_key), child_value) for child_key, child_value in value.items()}
        if isinstance(value, list):
            return [sanitize_value(key, item) for item in value]
        if isinstance(value, str):
            return _sanitize_string(value)
        return value

    return {str(key): sanitize_value(str(key), value) for key, value in metadata.items()}


def emit_audit_event(
    *,
    request_id: str | None,
    trace_id: str | None,
    event_category: AuditEventCategory,
    event_type: str,
    status: AuditEventStatus,
    workflow_name: str | None = None,
    node_name: str | None = None,
    event_sequence: int = 0,
    severity: AuditEventSeverity = AuditEventSeverity.INFO,
    failure: AuditFailure | None = None,
    duration_ms: int | None = None,
    metadata: dict[str, Any] | None = None,
    restricted_metadata: dict[str, Any] | None = None,
    include_trace_entry: bool = True,
) -> AuditEmitResult:
    errors: list[str] = []
    safe_request_id = request_id or new_request_id()
    safe_trace_id = trace_id or new_trace_id()
    safe_metadata = sanitize_metadata(metadata)
    safe_restricted_metadata = sanitize_metadata(restricted_metadata, allow_raw_sql=True)

    try:
        event = AuditEvent(
            request_id=safe_request_id,
            trace_id=safe_trace_id,
            event_sequence=event_sequence,
            event_category=event_category,
            event_type=event_type,
            status=status,
            severity=severity,
            workflow_name=workflow_name,
            node_name=node_name,
            failure=failure,
            duration_ms=duration_ms,
            metadata=safe_metadata,
            restricted_metadata=safe_restricted_metadata,
        )
        trace_entry = None
        if include_trace_entry and workflow_name and node_name:
            trace_entry = TraceEntry(
                request_id=safe_request_id,
                trace_id=safe_trace_id,
                event_sequence=event_sequence,
                workflow_name=workflow_name,
                node_name=node_name,
                status=status,
                failure=failure,
                duration_ms=duration_ms,
                metadata=safe_metadata,
            )
        _persist_audit_event(event)
        return AuditEmitResult(status=AuditEventStatus.SUCCEEDED, event=event, trace_entry=trace_entry)
    except Exception as exc:  # pragma: no cover - pydantic protects normal call paths
        errors.append(type(exc).__name__)
        return AuditEmitResult(status=AuditEventStatus.FAILED, errors=errors)


def append_trace_entry(state_patch: dict[str, Any], trace_entry: TraceEntry | None) -> dict[str, Any]:
    if trace_entry is None:
        return state_patch
    existing = list(state_patch.get("trace", []))
    existing.append(trace_entry.model_dump(mode="json"))
    return {**state_patch, "trace": existing}


def build_request_timeline(events: list[AuditEvent]) -> list[AuditTimelineRow]:
    rows = []
    for event in sorted(events, key=lambda item: (item.created_at, item.event_sequence)):
        rows.append(
            AuditTimelineRow(
                event_sequence=event.event_sequence,
                workflow_name=event.workflow_name,
                node_name=event.node_name,
                event_type=event.event_type,
                status=event.status,
                failure_code=event.failure.failure_code if event.failure else None,
                failure_reason=event.failure.failure_reason if event.failure else None,
                duration_ms=event.duration_ms,
                created_at=event.created_at,
            )
        )
    return rows


def _persist_audit_event(event: AuditEvent) -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        return
    from psycopg import connect
    from psycopg.types.json import Jsonb

    metadata = {
        "schema_version": event.schema_version,
        "trace_id": event.trace_id,
        "event_sequence": event.event_sequence,
        "event_category": event.event_category.value,
        "severity": event.severity.value,
        "workflow_name": event.workflow_name,
        "node_name": event.node_name,
        "failure": event.failure.model_dump(mode="json") if event.failure else None,
        "duration_ms": event.duration_ms,
        "metadata": event.metadata,
        "restricted_metadata": event.restricted_metadata,
    }
    with connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO audit_events (request_id, event_type, actor_user_key, status, metadata)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    event.request_id,
                    event.event_type,
                    event.actor.user_hash if event.actor else None,
                    event.status.value,
                    Jsonb(json.loads(json.dumps(metadata))),
                ),
            )
