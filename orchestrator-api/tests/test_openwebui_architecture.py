from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BRIDGE_FILES = [
    ROOT / "app" / "routes" / "openwebui.py",
    ROOT / "app" / "schemas" / "openwebui.py",
    ROOT / "app" / "services" / "openwebui_identity.py",
    ROOT.parents[0] / "openwebui_tools" / "company_intelligent.py",
    ROOT.parents[0] / "openwebui_functions" / "company_intelligent_pipe.py",
]


def _bridge_text() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in BRIDGE_FILES)


def test_openwebui_bridge_uses_main_graph_entrypoint_only() -> None:
    route_text = (ROOT / "app" / "routes" / "openwebui.py").read_text(encoding="utf-8")

    assert "run_main_graph" in route_text
    for forbidden in [
        "run_get_user_permission_schema",
        "run_tool_selection_planner",
        "run_sql_rag_agent",
        "run_final_answer_composer",
        "app.tools.sql_rag",
        "graphs.permission_schema.nodes",
    ]:
        assert forbidden not in route_text


def test_openwebui_bridge_contains_no_backend_business_mapping_or_internals() -> None:
    text = _bridge_text()

    for forbidden in [
        "execution_plan",
        "runtime_execution",
        "runtime_final_bundle",
        "final_answer_context",
        "trusted_access_context",
        "allowed_scopes",
        "denied_scopes",
        "permission_schema",
        "sql_rag",
        "rag_retrieval",
        "sql_executor",
        "sql_validator",
        "compose_generic_final_answer",
    ]:
        assert forbidden not in text


def test_openwebui_pipe_does_not_import_backend_core_modules() -> None:
    text = (ROOT.parents[0] / "openwebui_functions" / "company_intelligent_pipe.py").read_text(encoding="utf-8")

    for forbidden in [
        "app.graphs",
        "app.tools.sql_rag",
        "graphs.permission_schema",
        "run_main_graph",
        "run_final_answer_composer",
    ]:
        assert forbidden not in text


def test_main_py_only_registers_openwebui_router() -> None:
    text = (ROOT / "app" / "main.py").read_text(encoding="utf-8")

    assert "include_router(openwebui_router)" in text
    assert "openwebui_ask" not in text
    assert "run_main_graph" not in text
