from __future__ import annotations

from pathlib import Path

from app.services.source_catalog_dataset_rebuild import run_rebuild


class Store:
    def __init__(self) -> None:
        self.calls = 0

    def replace_dataset(self, records, documents, structured):
        self.calls += 1
        return {"sources_registered": len(records), "catalog_entries_written": len(records)}


def _dataset(root: Path) -> Path:
    finance = root / "Finance"
    finance.mkdir()
    (finance / "policy.txt").write_text("Finance policy evidence.", encoding="utf-8")
    (finance / "invoices.csv").write_text("amount,status\n100,overdue\n", encoding="utf-8")
    return root


def test_rebuild_scans_supported_files_and_writes_via_store(tmp_path: Path) -> None:
    store = Store()

    report = run_rebuild(_dataset(tmp_path), store=store)

    assert store.calls == 1
    assert report.status == "ok"
    assert report.files_scanned == 2
    assert report.files_supported == 2
    assert report.sources_registered == 2
    assert report.documents_parsed == 1
    assert report.structured_resources_written == 1
    assert report.structured_rows_written == 1
    assert report.join_refresh_required is True


def test_dry_run_scans_without_store_writes(tmp_path: Path) -> None:
    store = Store()

    report = run_rebuild(_dataset(tmp_path), dry_run=True, store=store)

    assert store.calls == 0
    assert report.status == "dry_run_ok"
    assert report.sources_registered == 0
    assert report.catalog_entries_written == 0


def test_missing_store_fails_closed_in_write_mode(tmp_path: Path) -> None:
    report = run_rebuild(_dataset(tmp_path))

    assert report.status == "failed"
    assert report.exit_code == 1
    assert report.validation_errors[-1]["code"] == "rebuild_store_not_configured"
