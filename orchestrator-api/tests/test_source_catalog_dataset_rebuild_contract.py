from __future__ import annotations

from pathlib import Path

from app.scripts.rebuild_dataset import main
from app.services.source_file_parsers import parse_rag_document
from app.services.structured_file_import import import_structured_file, safe_column_name


def test_text_parser_returns_safe_chunk_contract(tmp_path: Path) -> None:
    path = tmp_path / "doc.txt"
    path.write_text("hello world", encoding="utf-8")

    chunks = parse_rag_document(path, safe_path="Finance/doc.txt")

    assert chunks[0].chunk_index == 0
    assert chunks[0].chunk_text == "hello world"
    assert chunks[0].citation == {"safe_location_path": "Finance/doc.txt"}


def test_csv_import_profile_contract(tmp_path: Path) -> None:
    path = tmp_path / "invoices.csv"
    path.write_text("Invoice Amount,Status\n100,overdue\n", encoding="utf-8")

    profile = import_structured_file(path, relative_path="Finance/invoices.csv", permission_scope_key="finance")[0]

    assert profile.resource_key == "structured:finance:invoices"
    assert profile.runtime_relation_name == "structured_finance_invoices"
    assert profile.columns[0]["column_name"] == "invoice_amount"
    assert profile.columns[0]["data_type"] == "integer"
    assert profile.rows == [{"invoice_amount": 100, "status": "overdue"}]
    assert profile.metadata["row_count"] == 1


def test_safe_column_name_is_deterministic() -> None:
    assert safe_column_name("Invoice Amount ($)") == "invoice_amount"


def test_rebuild_script_returns_nonzero_for_missing_root(tmp_path: Path, capsys) -> None:
    exit_code = main(["--dataset-root", str(tmp_path / "missing")])

    assert exit_code == 1
    assert "active_dataset_root_missing" in capsys.readouterr().out
