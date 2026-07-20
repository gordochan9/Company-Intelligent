from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


SUPPORTED_RAG_EXTENSIONS = {".md", ".txt", ".pdf", ".docx"}
SUPPORTED_STRUCTURED_EXTENSIONS = {".csv", ".xlsx"}
SUPPORTED_EXTENSIONS = SUPPORTED_RAG_EXTENSIONS | SUPPORTED_STRUCTURED_EXTENSIONS


@dataclass(frozen=True)
class ScanRecord:
    relative_path: str
    source_uri: str
    extension: str
    permission_scope_key: str
    file_kind: str
    content_hash: str
    size_bytes: int


@dataclass(frozen=True)
class ParsedChunk:
    chunk_index: int
    chunk_text: str
    citation: dict[str, Any]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class StructuredImportProfile:
    resource_key: str
    runtime_relation_name: str
    display_name: str
    columns: list[dict[str, Any]]
    rows: list[dict[str, Any]]
    metadata: dict[str, Any]


@dataclass
class RebuildReport:
    status: str
    active_dataset_id: str
    dataset_root_label: str
    source_catalog_version: str
    files_scanned: int = 0
    files_supported: int = 0
    files_unsupported: int = 0
    sources_registered: int = 0
    catalog_entries_written: int = 0
    documents_parsed: int = 0
    chunks_written: int = 0
    embeddings_written: int = 0
    structured_files_imported: int = 0
    structured_resources_written: int = 0
    structured_columns_written: int = 0
    structured_rows_written: int = 0
    xlsx_workbooks_imported: int = 0
    xlsx_sheets_imported: int = 0
    skipped_files: list[dict[str, str]] = field(default_factory=list)
    validation_errors: list[dict[str, str]] = field(default_factory=list)
    warnings: list[dict[str, str]] = field(default_factory=list)
    exit_code: int = 0
    audit_event_ids: list[str] = field(default_factory=list)
    join_refresh_required: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "active_dataset_id": self.active_dataset_id,
            "dataset_root_label": self.dataset_root_label,
            "source_catalog_version": self.source_catalog_version,
            "files_scanned": self.files_scanned,
            "files_supported": self.files_supported,
            "files_unsupported": self.files_unsupported,
            "sources_registered": self.sources_registered,
            "catalog_entries_written": self.catalog_entries_written,
            "documents_parsed": self.documents_parsed,
            "chunks_written": self.chunks_written,
            "embeddings_written": self.embeddings_written,
            "structured_files_imported": self.structured_files_imported,
            "structured_resources_written": self.structured_resources_written,
            "structured_columns_written": self.structured_columns_written,
            "structured_rows_written": self.structured_rows_written,
            "xlsx_workbooks_imported": self.xlsx_workbooks_imported,
            "xlsx_sheets_imported": self.xlsx_sheets_imported,
            "skipped_files": self.skipped_files,
            "validation_errors": self.validation_errors,
            "warnings": self.warnings,
            "exit_code": self.exit_code,
            "audit_event_ids": self.audit_event_ids,
            "join_refresh_required": self.join_refresh_required,
        }
