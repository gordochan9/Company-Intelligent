from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Protocol

from app.schemas.dataset_rebuild import SUPPORTED_EXTENSIONS
from app.schemas.watchdog_reconciliation import ReconciliationRecord, WatchdogReconciliationReport
from app.schemas.watchdog_sync import WATCHDOG_SCOPE_BY_TOP_LEVEL


class WatchdogReconciliationStore(Protocol):
    def list_active_records(self) -> list[ReconciliationRecord]:
        ...


def run_watchdog_reconciliation(dataset_root: str | Path, *, store: WatchdogReconciliationStore) -> WatchdogReconciliationReport:
    root = Path(dataset_root)
    if not root.exists() or not root.is_dir():
        return WatchdogReconciliationReport(status="failed", mismatches=[_mismatch("active_dataset_root_missing", "active_dataset")])
    filesystem = _scan_filesystem(root)
    records = {record.relative_path: record for record in store.list_active_records()}
    mismatches = []
    for relative_path, file_hash in filesystem.items():
        record = records.get(relative_path)
        if record is None:
            mismatches.append(_mismatch("filesystem_source_missing_in_db", relative_path))
            continue
        if record.content_hash != file_hash:
            mismatches.append(_mismatch("content_hash_mismatch", relative_path))
        expected_scope = WATCHDOG_SCOPE_BY_TOP_LEVEL.get(relative_path.split("/", 1)[0])
        if expected_scope and record.permission_scope_key != expected_scope:
            mismatches.append(_mismatch("permission_scope_mismatch", relative_path))
        if record.file_kind == "rag_document" and record.chunk_count <= 0:
            mismatches.append(_mismatch("rag_document_missing_chunks", relative_path))
        if record.file_kind == "structured_table":
            if not record.runtime_relation_exists:
                mismatches.append(_mismatch("structured_runtime_relation_missing", relative_path))
            if sorted(record.structured_columns) != sorted(record.runtime_columns):
                mismatches.append(_mismatch("structured_columns_mismatch", relative_path))
            if record.row_count is not None and record.runtime_row_count is not None and record.row_count != record.runtime_row_count:
                mismatches.append(_mismatch("structured_row_count_mismatch", relative_path))
    for relative_path in set(records) - set(filesystem):
        mismatches.append(_mismatch("db_active_source_missing_from_filesystem", relative_path))
    return WatchdogReconciliationReport(
        status="full_rebuild_required" if mismatches else "current",
        mismatches=mismatches,
        filesystem_files=len(filesystem),
        catalog_records=len(records),
    )


def _scan_filesystem(root: Path) -> dict[str, str]:
    files = {}
    for path in sorted(item for item in root.rglob("*") if item.is_file() and item.suffix.lower() in SUPPORTED_EXTENSIONS):
        relative = path.relative_to(root).as_posix()
        if relative.split("/", 1)[0] not in WATCHDOG_SCOPE_BY_TOP_LEVEL:
            continue
        files[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return files


def _mismatch(code: str, relative_path: str) -> dict[str, str]:
    return {"code": code, "path": relative_path}
