from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _combined(path: Path) -> str:
    if path.is_file():
        return path.read_text(encoding="utf-8")
    return "\n".join(file.read_text(encoding="utf-8") for file in path.rglob("*.py"))


def test_runtime_graphs_and_sql_rag_do_not_import_join_discovery_service() -> None:
    for relative in [
        "app/graphs/main",
        "app/graphs/permission_schema",
        "app/graphs/tool_selection_planner",
        "app/tools/sql_rag/rag",
        "app/tools/sql_rag/sql",
    ]:
        text = _combined(ROOT / relative)
        assert "join_discovery_approved_joins" not in text
        assert "rebuild_approved_joins" not in text


def test_join_discovery_does_not_import_forbidden_runtime_boundaries() -> None:
    text = (ROOT / "app/services/join_discovery_approved_joins.py").read_text(encoding="utf-8")

    for forbidden in [
        "generate_candidate_sql",
        "validate_sql_before_execution",
        "execute_sql",
        "rag.services",
        "final_answer_composer",
        "openwebui",
        "tool_selection_planner",
    ]:
        assert forbidden not in text


def test_sql_subgraph_loader_does_not_call_llm_or_write_approved_joins() -> None:
    text = (ROOT / "app/tools/sql_rag/sql/nodes/load_approved_join_relationships.py").read_text(encoding="utf-8")

    assert "set_join_discovery_model" not in text
    assert "call" not in text.lower()
    assert "replace_approved_joins" not in text


def test_normal_startup_cannot_run_dataset_rebuild() -> None:
    project_root = ROOT.parent
    startup = (project_root / "scripts/project30_demo.ps1").read_text(encoding="utf-8")
    env_example = (project_root / ".env.example").read_text(encoding="utf-8")

    assert "PROJECT3_AUTO_REBUILD_ON_START" not in startup
    assert "Rebuild Dataset.bat" not in startup
    assert "Run-OptionalBat" not in startup
    assert "PROJECT3_AUTO_REBUILD_ON_START" not in env_example
