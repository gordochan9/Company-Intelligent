from __future__ import annotations

from pathlib import Path

from app.services.watchdog_runtime import normalize_watchdog_event
from app.services.watchdog_sync import apply_watchdog_event_batch


class Store:
    def __init__(self) -> None:
        self.documents: dict[str, list] = {}
        self.structured: dict[str, list] = {}
        self.deleted_documents: list[str] = []
        self.deleted_structured: list[str] = []
        self.renames: list[tuple[str, str]] = []

    def refresh_document(self, relative_path, permission_scope_key, chunks):
        self.documents[relative_path] = chunks

    def delete_document(self, relative_path):
        self.deleted_documents.append(relative_path)

    def refresh_structured(self, relative_path, permission_scope_key, profiles):
        self.structured[relative_path] = profiles
        return {"runtime_relation_validated": True, "columns_changed": False}

    def delete_structured(self, relative_path):
        self.deleted_structured.append(relative_path)

    def rename_path(self, source_relative_path, relative_path):
        self.renames.append((source_relative_path, relative_path))


def test_created_txt_refreshes_document_chunks(tmp_path: Path) -> None:
    path = tmp_path / "Finance" / "note.txt"
    path.parent.mkdir()
    path.write_text("Finance policy text.", encoding="utf-8")
    store = Store()

    report = apply_watchdog_event_batch(tmp_path, [normalize_watchdog_event(tmp_path, "created", path)], store=store)

    assert report.status == "ok"
    assert report.documents_refreshed == 1
    assert store.documents["Finance/note.txt"][0].chunk_text == "Finance policy text."


def test_modified_txt_replaces_prior_chunks_without_duplicates(tmp_path: Path) -> None:
    path = tmp_path / "Finance" / "note.txt"
    path.parent.mkdir()
    path.write_text("Version one.", encoding="utf-8")
    store = Store()
    apply_watchdog_event_batch(tmp_path, [normalize_watchdog_event(tmp_path, "created", path)], store=store)
    path.write_text("Version two.", encoding="utf-8")

    report = apply_watchdog_event_batch(tmp_path, [normalize_watchdog_event(tmp_path, "modified", path)], store=store)

    assert report.documents_refreshed == 1
    assert len(store.documents["Finance/note.txt"]) == 1
    assert store.documents["Finance/note.txt"][0].chunk_text == "Version two."


def test_corrupt_pdf_reports_safe_parser_failure(tmp_path: Path) -> None:
    path = tmp_path / "Finance" / "bad.pdf"
    path.parent.mkdir()
    path.write_bytes(b"not a pdf")

    report = apply_watchdog_event_batch(tmp_path, [normalize_watchdog_event(tmp_path, "created", path)], store=Store())

    assert report.status == "validation_failed"
    assert report.validation_errors[0]["code"] == "pdf_parse_failed"


def test_deleted_document_removes_chunks_and_embeddings_boundary(tmp_path: Path) -> None:
    path = tmp_path / "Finance" / "note.txt"
    path.parent.mkdir()
    path.write_text("gone", encoding="utf-8")
    store = Store()

    report = apply_watchdog_event_batch(tmp_path, [normalize_watchdog_event(tmp_path, "deleted", path)], store=store)

    assert report.documents_deleted == 1
    assert store.deleted_documents == ["Finance/note.txt"]


def test_cross_scope_document_rename_requires_full_rebuild(tmp_path: Path) -> None:
    source = tmp_path / "Finance" / "a.txt"
    target = tmp_path / "HR" / "a.txt"
    source.parent.mkdir()
    target.parent.mkdir()
    target.write_text("moved", encoding="utf-8")

    report = apply_watchdog_event_batch(
        tmp_path,
        [normalize_watchdog_event(tmp_path, "moved", target, source_path=source)],
        store=Store(),
    )

    assert report.status == "full_rebuild_required"
    assert report.validation_errors[0]["code"] == "cross_scope_rename"
