from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RAG_ROOT = ROOT / "app" / "tools" / "sql_rag" / "rag"


def _rag_text() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in RAG_ROOT.rglob("*.py"))


def test_rag_subgraph_has_approved_node_flow() -> None:
    graph_text = (RAG_ROOT / "graph.py").read_text(encoding="utf-8")

    for node in [
        "rag_intake",
        "build_permission_filtered_rag_schema",
        "read_filtered_rag_schema",
        "build_rag_search_plan",
        "select_relevant_documents",
        "retrieve_relevant_chunks",
        "validate_rag_evidence",
        "emit_rag_result",
        "emit_rag_failure",
    ]:
        assert f'graph.add_node("{node}"' in graph_text


def test_rag_subgraph_does_not_import_forbidden_workflow_internals() -> None:
    text = _rag_text()

    for forbidden in [
        "get_user_permission_schema",
        "resolve_trusted_identity",
        "resolve_user_groups",
        "resolve_share_drive_permissions",
        "permission_cache",
        "sql_generator",
        "sql_validator",
        "sql_executor",
        "build_sql_context",
        "final_answer_composer",
        "graphs.main",
        "tool_selection_planner",
    ]:
        assert forbidden not in text


def test_rag_subgraph_production_contract_does_not_use_forbidden_public_statuses() -> None:
    text = _rag_text()

    for forbidden in ["access_failed", "validation_failed", "denied", "permission_failed"]:
        assert forbidden not in text


def test_support_files_do_not_hide_node_level_workflow() -> None:
    graph_text = (RAG_ROOT / "graph.py").read_text(encoding="utf-8")
    agent_text = (RAG_ROOT / "agent.py").read_text(encoding="utf-8")
    state_text = (RAG_ROOT / "state.py").read_text(encoding="utf-8")

    assert "graph.add_node" in graph_text
    assert "invoke_rag_subgraph(step_state)" in agent_text
    assert "def rag_intake" not in state_text


def test_main_and_planner_do_not_call_rag_child_internals_before_dispatch_phase() -> None:
    main_root = ROOT / "app" / "graphs" / "main"
    main_text = "\n".join(path.read_text(encoding="utf-8") for path in main_root.rglob("*.py")) if main_root.exists() else ""
    planner_text = "\n".join(
        path.read_text(encoding="utf-8") for path in (ROOT / "app" / "graphs" / "tool_selection_planner").rglob("*.py")
    )

    assert "tools.sql_rag.rag.nodes" not in main_text
    assert "tools.sql_rag.rag.nodes" not in planner_text
    assert "run_rag_workflow" not in main_text
    assert "run_rag_workflow" not in planner_text
