from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SQL_ROOT = ROOT / "app" / "tools" / "sql_rag" / "sql"


def _sql_text() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in SQL_ROOT.rglob("*.py"))


def test_sql_subgraph_has_approved_node_flow() -> None:
    graph_text = (SQL_ROOT / "graph.py").read_text(encoding="utf-8")

    for node in [
        "sql_intake",
        "build_permission_filtered_sql_schema",
        "load_approved_join_relationships",
        "read_filtered_sql_schema",
        "build_sql_query_intent",
        "select_relevant_structured_resources",
        "generate_candidate_sql",
        "validate_sql_before_execution",
        "execute_sql",
        "validate_sql_result",
        "emit_sql_result",
        "emit_sql_failure",
    ]:
        assert f'graph.add_node("{node}"' in graph_text


def test_sql_subgraph_does_not_import_forbidden_workflow_internals() -> None:
    text = _sql_text()

    for forbidden in [
        "get_user_permission_schema",
        "resolve_trusted_identity",
        "resolve_user_groups",
        "resolve_share_drive_permissions",
        "permission_cache",
        "rag_retrieval",
        "vector_retriever",
        "keyword_retriever",
        "final_answer_composer",
        "graphs.main",
        "tool_selection_planner",
    ]:
        assert forbidden not in text


def test_sql_subgraph_does_not_import_join_discovery_or_rag_child() -> None:
    text = _sql_text()

    assert "join_discovery" not in text
    assert "tools.sql_rag.rag" not in text


def test_support_files_do_not_hide_node_level_workflow() -> None:
    graph_text = (SQL_ROOT / "graph.py").read_text(encoding="utf-8")
    agent_text = (SQL_ROOT / "agent.py").read_text(encoding="utf-8")
    state_text = (SQL_ROOT / "state.py").read_text(encoding="utf-8")

    assert "graph.add_node" in graph_text
    assert "invoke_sql_subgraph(step_state)" in agent_text
    assert "def sql_intake" not in state_text


def test_main_and_planner_do_not_call_sql_child_internals_before_dispatch_phase() -> None:
    main_root = ROOT / "app" / "graphs" / "main"
    main_text = "\n".join(path.read_text(encoding="utf-8") for path in main_root.rglob("*.py")) if main_root.exists() else ""
    planner_text = "\n".join(
        path.read_text(encoding="utf-8") for path in (ROOT / "app" / "graphs" / "tool_selection_planner").rglob("*.py")
    )

    assert "tools.sql_rag.sql.nodes" not in main_text
    assert "tools.sql_rag.sql.nodes" not in planner_text
    assert "run_sql_workflow" not in main_text
    assert "run_sql_workflow" not in planner_text


def test_runtime_configures_distinct_sql_selector_model_hook() -> None:
    main_text = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
    llm_text = (SQL_ROOT / "services" / "llm.py").read_text(encoding="utf-8")

    assert "set_sql_selector_model(deepseek_payload_call)" in main_text
    assert "def call_selector_model" in llm_text
    assert "def parse_resource_selection" in llm_text
