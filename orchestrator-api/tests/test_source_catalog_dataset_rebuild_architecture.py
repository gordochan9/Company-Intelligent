from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_graphs_and_tools_do_not_import_rebuild_services() -> None:
    combined = "\n".join(
        path.read_text(encoding="utf-8")
        for base in [ROOT / "app" / "graphs", ROOT / "app" / "tools"]
        for path in base.rglob("*.py")
    )

    for forbidden in ["source_catalog_dataset_rebuild", "source_file_parsers", "structured_file_import", "rebuild_dataset"]:
        assert forbidden not in combined


def test_rebuild_services_do_not_import_runtime_business_layers() -> None:
    combined = "\n".join(
        path.read_text(encoding="utf-8")
        for path in [
            ROOT / "app" / "services" / "source_catalog_dataset_rebuild.py",
            ROOT / "app" / "services" / "source_file_parsers.py",
            ROOT / "app" / "services" / "structured_file_import.py",
        ]
    )

    for forbidden in ["final_answer_composer", "openwebui", "run_sql_rag_agent", "run_main_graph", "approved_join_relationships"]:
        assert forbidden not in combined


def test_rebuild_code_contains_no_ocr_dependency_references() -> None:
    combined = "\n".join(
        path.read_text(encoding="utf-8")
        for path in [
            ROOT / "requirements.txt",
            ROOT / "app" / "services" / "source_file_parsers.py",
            ROOT / "app" / "services" / "structured_file_import.py",
        ]
    )

    for forbidden in ["pytesseract", "pdf2image", "easyocr", "textract"]:
        assert forbidden not in combined
