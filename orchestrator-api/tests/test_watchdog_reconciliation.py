from __future__ import annotations

import hashlib
from pathlib import Path

from app.schemas.watchdog_reconciliation import ReconciliationRecord
from app.services.watchdog_reconciliation import run_watchdog_reconciliation


class Store:
    def __init__(self, records: list[ReconciliationRecord]) -> None:
        self.records = records

    def list_active_records(self) -> list[ReconciliationRecord]:
        return self.records


def _file(root: Path, relative: str, text: str = "hello") -> str:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_reconciliation_returns_current_when_filesystem_and_runtime_match(tmp_path: Path) -> None:
    digest = _file(tmp_path, "Finance/a.txt")
    store = Store([ReconciliationRecord("Finance/a.txt", digest, "finance", "rag_document", chunk_count=1)])

    report = run_watchdog_reconciliation(tmp_path, store=store)

    assert report.status == "current"


def test_reconciliation_detects_missing_db_source_and_hash_mismatch(tmp_path: Path) -> None:
    _file(tmp_path, "Finance/a.txt")
    store = Store([ReconciliationRecord("Finance/a.txt", "wrong", "finance", "rag_document", chunk_count=1)])

    report = run_watchdog_reconciliation(tmp_path, store=store)

    assert report.status == "full_rebuild_required"
    assert report.mismatches[0]["code"] == "content_hash_mismatch"


def test_reconciliation_detects_db_active_source_missing_from_filesystem(tmp_path: Path) -> None:
    store = Store([ReconciliationRecord("Finance/missing.txt", "digest", "finance", "rag_document", chunk_count=1)])

    report = run_watchdog_reconciliation(tmp_path, store=store)

    assert report.status == "full_rebuild_required"
    assert report.mismatches[0]["code"] == "db_active_source_missing_from_filesystem"


def test_reconciliation_detects_structured_runtime_mismatches(tmp_path: Path) -> None:
    digest = _file(tmp_path, "Finance/orders.csv", "id,amount\n1,10\n")
    store = Store(
        [
            ReconciliationRecord(
                "Finance/orders.csv",
                digest,
                "finance",
                "structured_table",
                runtime_relation_exists=False,
                structured_columns=["id", "amount"],
                runtime_columns=["id"],
                row_count=1,
                runtime_row_count=2,
            )
        ]
    )

    report = run_watchdog_reconciliation(tmp_path, store=store)
    codes = {mismatch["code"] for mismatch in report.mismatches}

    assert {"structured_runtime_relation_missing", "structured_columns_mismatch", "structured_row_count_mismatch"} <= codes
