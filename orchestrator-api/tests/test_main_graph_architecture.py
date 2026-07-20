from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAIN_ROOT = ROOT / "app" / "graphs" / "main"


def _main_text() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in MAIN_ROOT.rglob("*.py"))


def test_main_graph_has_approved_node_flow() -> None:
    graph_text = (MAIN_ROOT / "graph.py").read_text(encoding="utf-8")

    for node_name in [
        "request_intake",
        "get_user_permission_schema",
        "tool_selection_planner",
        "tool_dispatch",
        "final_answer_composer",
    ]:
        assert f'graph.add_node("{node_name}"' in graph_text

    assert 'graph.add_edge(START, "request_intake")' in graph_text
    assert 'graph.add_edge("request_intake", "get_user_permission_schema")' in graph_text
    assert 'graph.add_edge("tool_dispatch", "final_answer_composer")' in graph_text


def test_main_graph_calls_only_approved_workflow_entrypoints() -> None:
    text = _main_text()

    assert "run_get_user_permission_schema" in text
    assert "run_tool_selection_planner" in text
    assert "run_sql_rag_agent" in text
    assert "run_final_answer_composer" in text
    for forbidden in [
        "tools.sql_rag.nodes",
        "run_rag_workflow",
        "run_sql_workflow",
        "multi_step_runtime_executor",
        "perform_rag_sql",
        "normalizer_transformer",
        "final_result_bundle",
    ]:
        assert forbidden not in text


def test_main_graph_contains_no_sql_rag_or_permission_internals() -> None:
    text = _main_text()

    for forbidden in [
        "build_sql_context",
        "enrich_sql_context",
        "sql_context_from_catalog_entries",
        "approved_sql_joins",
        "join_discovery",
        "infer_join",
        "sql_generator",
        "sql_validator",
        "sql_executor",
        "vector_retriever",
        "keyword_retriever",
        "rag_retrieval",
        "retrieve_chunks",
        "resolve_share_drive_permissions",
        "build_allowed_resource_map",
    ]:
        assert forbidden not in text


def test_main_graph_has_no_keyword_question_router() -> None:
    text = _main_text()

    assert "MAX_SELECTED_TOOLS" not in text
    assert not re.search(r"if .* in user_question", text)
    assert not re.search(r"if .* in question", text)
