from __future__ import annotations

from pathlib import Path
from decimal import Decimal

from app.schemas.dataset_rebuild import SUPPORTED_EXTENSIONS, SUPPORTED_RAG_EXTENSIONS, SUPPORTED_STRUCTURED_EXTENSIONS
from app.services.structured_file_import import import_structured_file


def test_supported_extension_registry_matches_v2_parity() -> None:
    assert SUPPORTED_RAG_EXTENSIONS == {".md", ".txt", ".pdf", ".docx"}
    assert SUPPORTED_STRUCTURED_EXTENSIONS == {".csv", ".xlsx"}
    assert SUPPORTED_EXTENSIONS == {".md", ".txt", ".pdf", ".docx", ".csv", ".xlsx"}


def test_required_parser_dependencies_are_declared_and_ocr_dependencies_are_absent() -> None:
    requirements = (Path(__file__).resolve().parents[1] / "requirements.txt").read_text(encoding="utf-8")

    assert "openpyxl" in requirements
    assert "pypdf" in requirements
    assert "python-docx" in requirements
    for forbidden in ["pytesseract", "pdf2image", "easyocr", "textract"]:
        assert forbidden not in requirements


def test_csv_type_inference_is_canonical_and_exact(tmp_path: Path) -> None:
    path = tmp_path / "typed.csv"
    path.write_text(
        "all_null,flag,binary,whole,amount,code,mixed,date_value\n"
        ",true,0,1,1.25,001,1,2026-07-15\n"
        ",false,1,-2,2,002,nope,2026-07-16\n",
        encoding="utf-8",
    )

    profile = import_structured_file(path, relative_path="Finance/typed.csv", permission_scope_key="finance")[0]

    assert [column["data_type"] for column in profile.columns] == [
        "text", "boolean", "integer", "integer", "decimal", "text", "text", "text"
    ]
    assert profile.rows == [
        {
            "all_null": None,
            "flag": True,
            "binary": 0,
            "whole": 1,
            "amount": Decimal("1.25"),
            "code": "001",
            "mixed": "1",
            "date_value": "2026-07-15",
        },
        {
            "all_null": None,
            "flag": False,
            "binary": 1,
            "whole": -2,
            "amount": Decimal("2"),
            "code": "002",
            "mixed": "nope",
            "date_value": "2026-07-16",
        },
    ]


def test_xlsx_uses_the_same_type_inference_and_conversion_path(tmp_path: Path) -> None:
    from openpyxl import Workbook

    path = tmp_path / "typed.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["flag", "whole", "amount", "blank", "date_text"])
    sheet.append([True, 1, 1.25, None, "2026-07-15"])
    sheet.append([False, 2, 2, "", "2026-07-16"])
    workbook.save(path)

    profile = import_structured_file(path, relative_path="Finance/typed.xlsx", permission_scope_key="finance")[0]

    assert [column["data_type"] for column in profile.columns] == ["boolean", "integer", "decimal", "text", "text"]
    assert profile.rows[0] == {
        "flag": True,
        "whole": 1,
        "amount": Decimal("1.25"),
        "blank": None,
        "date_text": "2026-07-15",
    }
    assert profile.rows[1]["amount"] == Decimal("2")
