from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Protocol

from app.schemas.dataset_rebuild import RebuildReport, SUPPORTED_EXTENSIONS, SUPPORTED_RAG_EXTENSIONS, ScanRecord
from app.services.source_file_parsers import SourceParseError, parse_rag_document
from app.services.structured_file_import import StructuredImportError, import_structured_file


SCOPE_BY_TOP_LEVEL = {
    "Employee Guidelines": "employee_guidelines",
    "File Server": "file_server",
    "Finance": "finance",
    "HR": "hr",
}


class RebuildStore(Protocol):
    def replace_dataset(self, records: list[ScanRecord], documents: dict[str, list], structured: dict[str, list]) -> dict[str, int]:
        ...


def run_rebuild(
    dataset_root: str | Path | None = None,
    *,
    dry_run: bool = False,
    store: RebuildStore | None = None,
    active_dataset_id: str = "active",
    source_catalog_version: str = "active",
) -> RebuildReport:
    root = Path(dataset_root or os.getenv("CONTAINER_ACTIVE_DATASET_ROOT", "/app/active_dataset"))
    report = RebuildReport(
        status="dry_run_ok" if dry_run else "failed",
        active_dataset_id=active_dataset_id,
        dataset_root_label="active_dataset",
        source_catalog_version=source_catalog_version,
    )
    if not root.exists() or not root.is_dir():
        report.status = "dry_run_failed" if dry_run else "failed"
        report.validation_errors.append({"code": "active_dataset_root_missing", "message": "Active dataset root is unavailable."})
        report.exit_code = 1
        return report

    records: list[ScanRecord] = []
    documents: dict[str, list] = {}
    structured: dict[str, list] = {}
    for path in sorted(item for item in root.rglob("*") if item.is_file() and not item.is_symlink()):
        report.files_scanned += 1
        try:
            record = _scan_record(root, path)
        except ValueError:
            safe_path = path.relative_to(root).as_posix()
            report.validation_errors.append({"path": safe_path, "code": "unknown_top_level_scope"})
            continue
        if record.extension not in SUPPORTED_EXTENSIONS:
            report.files_unsupported += 1
            report.skipped_files.append({"path": record.relative_path, "code": "unsupported_extension"})
            continue
        report.files_supported += 1
        records.append(record)
        if record.extension in SUPPORTED_RAG_EXTENSIONS:
            try:
                chunks = parse_rag_document(path, safe_path=record.relative_path)
                documents[record.relative_path] = chunks
                report.documents_parsed += 1
                report.chunks_written += len(chunks) if not dry_run else 0
            except SourceParseError as exc:
                report.skipped_files.append({"path": record.relative_path, "code": exc.code})
        else:
            try:
                profiles = import_structured_file(path, relative_path=record.relative_path, permission_scope_key=record.permission_scope_key)
                structured[record.relative_path] = profiles
                report.structured_files_imported += 1
                report.structured_resources_written += len(profiles) if not dry_run else 0
                report.structured_columns_written += sum(len(profile.columns) for profile in profiles) if not dry_run else 0
                report.structured_rows_written += sum(len(profile.rows) for profile in profiles) if not dry_run else 0
                if record.extension == ".xlsx":
                    report.xlsx_workbooks_imported += 1
                    report.xlsx_sheets_imported += len(profiles)
            except StructuredImportError as exc:
                report.skipped_files.append({"path": record.relative_path, "code": exc.code})

    report.sources_registered = len(records) if not dry_run else 0
    report.catalog_entries_written = len(records) if not dry_run else 0
    report.embeddings_written = 0
    report.warnings.append({"code": "embeddings_not_configured", "message": "Embedding writer is not configured for this rebuild."})
    report.join_refresh_required = bool(structured)
    if dry_run:
        report.status = "dry_run_ok" if not report.validation_errors else "dry_run_failed"
        report.exit_code = 0 if report.status == "dry_run_ok" else 1
        return report
    if store is None:
        report.status = "failed"
        report.validation_errors.append({"code": "rebuild_store_not_configured", "message": "Dataset rebuild store is not configured."})
        report.exit_code = 1
        return report
    counts = store.replace_dataset(records, documents, structured)
    report.sources_registered = counts.get("sources_registered", report.sources_registered)
    report.catalog_entries_written = counts.get("catalog_entries_written", report.catalog_entries_written)
    report.status = "completed_with_skips" if report.skipped_files else "ok"
    report.exit_code = 0
    return report


def _scan_record(root: Path, path: Path) -> ScanRecord:
    relative = path.relative_to(root).as_posix()
    top_level = relative.split("/", 1)[0]
    scope = SCOPE_BY_TOP_LEVEL.get(top_level)
    if not scope:
        raise ValueError("unknown_top_level_scope")
    extension = path.suffix.lower()
    return ScanRecord(
        relative_path=relative,
        source_uri="active-dataset://" + relative,
        extension=extension,
        permission_scope_key=scope,
        file_kind="rag_document" if extension in SUPPORTED_RAG_EXTENSIONS else "structured_table",
        content_hash=hashlib.sha256(path.read_bytes()).hexdigest(),
        size_bytes=path.stat().st_size,
    )
