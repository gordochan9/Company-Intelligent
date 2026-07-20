from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMPOSER_ROOT = ROOT / "app" / "graphs" / "final_answer_composer"
WRAPPER = ROOT / "app" / "graphs" / "main" / "nodes" / "final_answer_composer.py"


def _production_text() -> str:
    files = list(COMPOSER_ROOT.rglob("*.py")) + [WRAPPER]
    return "\n".join(path.read_text(encoding="utf-8") for path in files)


def test_final_answer_composer_has_approved_node_flow() -> None:
    graph_text = (COMPOSER_ROOT / "graph.py").read_text(encoding="utf-8")
    nodes = [
        "final_answer_intake",
        "read_user_question",
        "read_final_answer_context_from_adapter",
        "build_final_answer_llm_payload",
        "call_final_answer_llm",
        "log_final_answer_llm_response",
        "parse_final_answer_llm_json",
        "attach_public_citations",
        "emit_final_answer",
    ]

    for node_name in nodes:
        assert f'graph.add_node("{node_name}"' in graph_text
        assert (COMPOSER_ROOT / "nodes" / f"{node_name}.py").exists()

    assert 'graph.add_edge(START, "final_answer_intake")' in graph_text


def test_main_graph_final_answer_wrapper_is_thin() -> None:
    text = WRAPPER.read_text(encoding="utf-8")

    assert "run_final_answer_composer" in text
    for forbidden in [
        "build_final_answer_llm_payload",
        "call_final_answer_llm",
        "parse_final_answer_llm_json",
        "attach_public_citations",
        "emit_audit_event",
        "run_sql_rag_agent",
    ]:
        assert forbidden not in text


def test_final_answer_composer_does_not_call_tool_or_permission_internals() -> None:
    text = _production_text()

    for forbidden in [
        "sql_generator",
        "sql_validator",
        "sql_executor",
        "execute_sql",
        "vector_retriever",
        "keyword_retriever",
        "retrieve_chunks",
        "rag_retrieval",
        "resolve_share_drive_permissions",
        "permission_adapter",
        "run_sql_rag_agent",
        "run_rag_workflow",
        "run_sql_workflow",
    ]:
        assert forbidden not in text
