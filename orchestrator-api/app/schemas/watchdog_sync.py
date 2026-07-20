from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from app.schemas.dataset_rebuild import SUPPORTED_EXTENSIONS, SUPPORTED_RAG_EXTENSIONS, SUPPORTED_STRUCTURED_EXTENSIONS


WATCHDOG_SCOPE_BY_TOP_LEVEL = {
    "Employee Guidelines": "employee_guidelines",
    "File Server": "file_server",
    "Finance": "finance",
    "HR": "hr",
}
WATCHDOG_EVENT_TYPES = {"created", "modified", "deleted", "moved"}
WATCHDOG_REPORT_STATUSES = {"ok", "skipped", "validation_failed", "full_rebuild_required", "failed"}


@dataclass(frozen=True)
class WatchdogEvent:
    event_type: Literal["created", "modified", "deleted", "moved"]
    relative_path: str
    permission_scope_key: str
    extension: str
    file_kind: Literal["rag_document", "structured_table", "unsupported"]
    source_relative_path: str | None = None
    reason: str | None = None


@dataclass
class WatchdogSyncReport:
    status: Literal["ok", "skipped", "validation_failed", "full_rebuild_required", "failed"]
    processed_events: int = 0
    skipped_events: int = 0
    documents_refreshed: int = 0
    documents_deleted: int = 0
    structured_resources_refreshed: int = 0
    structured_resources_deleted: int = 0
    full_rebuild_required: bool = False
    join_refresh_recommended: bool = False
    validation_errors: list[dict[str, str]] = field(default_factory=list)
    warnings: list[dict[str, str]] = field(default_factory=list)
    audit_status: str = "not_configured"
    audit_event_ids: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "processed_events": self.processed_events,
            "skipped_events": self.skipped_events,
            "documents_refreshed": self.documents_refreshed,
            "documents_deleted": self.documents_deleted,
            "structured_resources_refreshed": self.structured_resources_refreshed,
            "structured_resources_deleted": self.structured_resources_deleted,
            "full_rebuild_required": self.full_rebuild_required,
            "join_refresh_recommended": self.join_refresh_recommended,
            "validation_errors": self.validation_errors,
            "warnings": self.warnings,
            "audit_status": self.audit_status,
            "audit_event_ids": self.audit_event_ids,
        }


def file_kind_for_extension(extension: str) -> Literal["rag_document", "structured_table", "unsupported"]:
    suffix = extension.lower()
    if suffix in SUPPORTED_RAG_EXTENSIONS:
        return "rag_document"
    if suffix in SUPPORTED_STRUCTURED_EXTENSIONS:
        return "structured_table"
    return "unsupported"


def supported_extensions() -> set[str]:
    return set(SUPPORTED_EXTENSIONS)
