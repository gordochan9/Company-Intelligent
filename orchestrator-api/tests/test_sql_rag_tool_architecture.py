from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SQL_RAG_ROOT = ROOT / "app" / "tools" / "sql_rag"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def test_sql_rag_tool_has_approved_node_flow() -> None:
    graph_text = _text(SQL_RAG_ROOT / "graph.py")

    for node_name in [
        "sql_rag_agent",
        "runtime_obligation_planner",
        "multi_step_runtime_executor",
        "perform_rag_sql",
        "normalizer_transformer",
        "final_result_bundle",
        "adapter",
    ]:
        assert f'graph.add_node("{node_name}"' in graph_text

    assert 'graph.add_edge(START, "sql_rag_agent")' in graph_text
    assert 'graph.add_conditional_edges("sql_rag_agent", _after_agent)' in graph_text
    assert 'graph.add_conditional_edges("runtime_obligation_planner", _after_planner)' in graph_text
    assert 'graph.add_edge("perform_rag_sql", "normalizer_transformer")' in graph_text
    assert 'graph.add_edge("normalizer_transformer", "multi_step_runtime_executor")' in graph_text
    assert 'graph.add_edge("final_result_bundle", "adapter")' in graph_text


def test_planner_owns_model_call_and_executor_is_deterministic() -> None:
    planner = _text(SQL_RAG_ROOT / "nodes" / "runtime_obligation_planner.py")
    executor = _text(SQL_RAG_ROOT / "nodes" / "multi_step_runtime_executor.py")

    assert "set_runtime_obligation_planner_model" in planner
    assert "_runtime_obligation_planner_model(" in planner
    for forbidden in ["set_runtime_plan_model", "system_prompt", "_model(", "user_question"]:
        assert forbidden not in executor


def test_runtime_planning_contains_no_phrase_or_sql_value_heuristics() -> None:
    planner = _text(SQL_RAG_ROOT / "nodes" / "runtime_obligation_planner.py").casefold()
    contracts = _text(SQL_RAG_ROOT / "contracts.py").casefold()

    for forbidden in [
        "answer the second part",
        "what are their names",
        "continue from previous result",
        "_is_vague_goal",
        "_reject_forbidden_values",
    ]:
        assert forbidden not in planner
        assert forbidden not in contracts


def test_runtime_step_audit_uses_approved_event_names() -> None:
    normalizer = _text(SQL_RAG_ROOT / "nodes" / "normalizer_transformer.py")
    executor = _text(SQL_RAG_ROOT / "nodes" / "multi_step_runtime_executor.py")

    assert "normalizer_completed" in normalizer
    assert "runtime_step_completed" in normalizer
    assert "runtime_step_failed" in normalizer
    assert "runtime_step_coverage_evaluated" not in normalizer
    assert "runtime_step_completed" in executor
    assert "runtime_step_failed" in executor
    assert "runtime_step_coverage_evaluated" not in executor
    for forbidden in ["_missing_outputs", "incomplete_step_output", "STATUS_BLOCKED", '"runtime_plan_status"']:
        assert forbidden not in normalizer


def test_sql_and_rag_coverage_ownership_is_split_at_runtime_boundary() -> None:
    normalizer = _text(SQL_RAG_ROOT / "nodes" / "normalizer_transformer.py")
    executor = _text(SQL_RAG_ROOT / "nodes" / "multi_step_runtime_executor.py")

    assert 'step.get("step_type") == "rag"' in normalizer
    assert "_sql_output_gate_reason" in executor
    assert "covered_obligation_ids" in executor
    assert "validated_evidence" not in executor


def test_support_files_do_not_hide_node_level_workflow_behavior() -> None:
    graph = _text(SQL_RAG_ROOT / "graph.py")
    state = _text(SQL_RAG_ROOT / "state.py")
    contracts = _text(SQL_RAG_ROOT / "contracts.py")

    assert "def validate_runtime_plan" in contracts
    assert "def multi_step_runtime_executor" not in contracts
    assert "emit_audit_event" not in contracts
    assert "def runtime_obligation_planner" not in state
    assert "call_" not in state
    assert "def validate_runtime_plan" not in graph


def test_perform_rag_sql_uses_only_child_public_entrypoints() -> None:
    text = _text(SQL_RAG_ROOT / "nodes" / "perform_rag_sql.py")

    assert "run_rag_workflow" in text
    assert "run_sql_workflow" in text
    for forbidden in [
        "tools.sql_rag.rag.nodes",
        "tools.sql_rag.sql.nodes",
        "generate_candidate_sql",
        "validate_sql_before_execution",
        "execute_sql",
        "retrieve_relevant_chunks",
        "validate_rag_evidence",
    ]:
        assert forbidden not in text


def test_sql_rag_agent_and_adapter_do_not_compose_final_answer() -> None:
    text = "\n".join(
        _text(SQL_RAG_ROOT / path)
        for path in [
            Path("agent.py"),
            Path("nodes") / "sql_rag_agent.py",
            Path("nodes") / "adapter.py",
            Path("nodes") / "final_result_bundle.py",
        ]
    )

    assert "final_answer_context" in text
    assert "compose_final" not in text
    assert "final_answer_composer" not in text
    assert '"answer"' not in text


def test_main_graph_not_created_or_connected_during_sql_rag_phase() -> None:
    main_root = ROOT / "app" / "graphs" / "main"
    if not main_root.exists():
        assert True
        return

    main_text = "\n".join(path.read_text(encoding="utf-8") for path in main_root.rglob("*.py"))
    for forbidden in [
        "multi_step_runtime_executor",
        "perform_rag_sql",
        "normalizer_transformer",
        "final_result_bundle",
        "tools.sql_rag.nodes",
        "run_rag_workflow",
        "run_sql_workflow",
    ]:
        assert forbidden not in main_text
