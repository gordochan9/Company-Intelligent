from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(frozen=True)
class ReconciliationRecord:
    relative_path: str
    content_hash: str
    permission_scope_key: str
    file_kind: Literal["rag_document", "structured_table"]
    chunk_count: int = 0
    runtime_relation_exists: bool = True
    structured_columns: list[str] = field(default_factory=list)
    runtime_columns: list[str] = field(default_factory=list)
    row_count: int | None = None
    runtime_row_count: int | None = None


@dataclass
class WatchdogReconciliationReport:
    status: Literal["current", "full_rebuild_required", "failed"]
    mismatches: list[dict[str, str]] = field(default_factory=list)
    filesystem_files: int = 0
    catalog_records: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "mismatches": self.mismatches,
            "filesystem_files": self.filesystem_files,
            "catalog_records": self.catalog_records,
        }
