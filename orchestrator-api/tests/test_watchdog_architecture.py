from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _combined(path: Path) -> str:
    return "\n".join(file.read_text(encoding="utf-8") for file in path.rglob("*.py"))


def test_runtime_boundaries_do_not_import_watchdog_modules() -> None:
    for relative in [
        "app/graphs/main",
        "app/graphs/permission_schema",
        "app/graphs/tool_selection_planner",
        "app/tools/sql_rag",
        "app/graphs/final_answer_composer",
        "app/routes",
    ]:
        text = _combined(ROOT / relative)
        assert "watchdog_runtime" not in text
        assert "watchdog_sync" not in text
        assert "watchdog_reconciliation" not in text


def test_watchdog_services_do_not_import_forbidden_runtime_or_join_boundaries() -> None:
    text = _combined(ROOT / "app/services")
    watchdog_text = "\n".join(
        (ROOT / "app/services" / name).read_text(encoding="utf-8")
        for name in ["watchdog_runtime.py", "watchdog_sync.py", "watchdog_reconciliation.py"]
    )

    for forbidden in [
        "join_discovery_approved_joins",
        "rebuild_approved_joins",
        "run_sql_workflow",
        "run_rag_workflow",
        "perform_rag_sql",
        "final_answer_composer",
        "company_intelligent",
        "approved_join_relationships",
    ]:
        assert forbidden not in watchdog_text
    assert "watchdog" in text
