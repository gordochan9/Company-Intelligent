from pathlib import Path


PERMISSION_PATHS = [
    Path(__file__).resolve().parents[1] / "app" / "graphs" / "permission_schema",
    Path(__file__).resolve().parents[1] / "app" / "services" / "permissions",
]


def _production_text() -> str:
    files = []
    for root in PERMISSION_PATHS:
        files.extend(root.rglob("*.py"))
    return "\n".join(path.read_text(encoding="utf-8") for path in files)


def test_permission_schema_production_code_does_not_read_user_question() -> None:
    assert "user_question" not in _production_text()


def test_permission_schema_does_not_import_sql_rag_or_final_answer_layers() -> None:
    text = _production_text()

    for forbidden in [
        "sql_generator",
        "sql_validator",
        "sql_executor",
        "build_sql_context",
        "vector_retriever",
        "keyword_retriever",
        "retrieve_chunks",
        "final_answer_composer",
    ]:
        assert forbidden not in text


def test_demo_hardcoding_is_isolated_to_demo_adapter() -> None:
    root = Path(__file__).resolve().parents[1] / "app"
    matches = []
    for path in root.rglob("*.py"):
        if "admin@demo.com" in path.read_text(encoding="utf-8"):
            matches.append(path)

    assert matches == [root / "services" / "permissions" / "demo_adapter.py"]
