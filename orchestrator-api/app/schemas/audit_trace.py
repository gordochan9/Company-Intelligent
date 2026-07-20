from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class AuditEventCategory(StrEnum):
    REQUEST = "request"
    IDENTITY = "identity"
    PERMISSION = "permission"
    PLANNER = "planner"
    DISPATCH = "dispatch"
    TOOL = "tool"
    RAG = "rag"
    SQL = "sql"
    ADAPTER = "adapter"
    FINAL_ANSWER = "final_answer"
    OPENWEBUI = "openwebui"
    DATASET_REBUILD = "dataset_rebuild"
    JOIN_DISCOVERY = "join_discovery"
    WATCHDOG = "watchdog"
    SECURITY = "security"
    SYSTEM = "system"


class AuditEventStatus(StrEnum):
    STARTED = "started"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    DENIED = "denied"
    VALIDATION_FAILED = "validation_failed"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    ACCESS_FAILED = "access_failed"
    SKIPPED = "skipped"


class AuditEventSeverity(StrEnum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AuditActor(BaseModel):
    actor_type: str = "system"
    user_hash: str | None = None
    auth_source: str | None = None


class AuditFailure(BaseModel):
    failed_workflow: str
    failed_node: str
    failure_code: str
    failure_reason: str


class AuditEvent(BaseModel):
    schema_version: str = "1.0"
    request_id: str
    trace_id: str
    event_sequence: int = 0
    event_category: AuditEventCategory
    event_type: str
    status: AuditEventStatus
    severity: AuditEventSeverity = AuditEventSeverity.INFO
    workflow_name: str | None = None
    node_name: str | None = None
    actor: AuditActor | None = None
    failure: AuditFailure | None = None
    duration_ms: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    restricted_metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class TraceEntry(BaseModel):
    schema_version: str = "1.0"
    request_id: str
    trace_id: str
    event_sequence: int = 0
    workflow_name: str
    node_name: str
    status: AuditEventStatus
    failure: AuditFailure | None = None
    duration_ms: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AuditEmitResult(BaseModel):
    status: AuditEventStatus
    event: AuditEvent | None = None
    trace_entry: TraceEntry | None = None
    errors: list[str] = Field(default_factory=list)


class AuditTimelineRow(BaseModel):
    event_sequence: int
    workflow_name: str | None = None
    node_name: str | None = None
    event_type: str
    status: AuditEventStatus
    failure_code: str | None = None
    failure_reason: str | None = None
    duration_ms: int | None = None
    created_at: datetime
