from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLANNER_PATHS = [
    ROOT / "app" / "graphs" / "tool_selection_planner",
    ROOT / "app" / "services" / "tool_selection_planner.py",
]


def _production_files() -> list[Path]:
    files: list[Path] = []
    for path in PLANNER_PATHS:
        if path.is_dir():
            files.extend(path.rglob("*.py"))
        else:
            files.append(path)
    return files


def _production_text() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in _production_files())


def test_tool_selection_planner_has_approved_node_flow() -> None:
    graph_text = (ROOT / "app" / "graphs" / "tool_selection_planner" / "graph.py").read_text(encoding="utf-8")

    for node_name in [
        "tool_selection_intake",
        "load_tool_capability_cards",
        "build_tool_selection_prompt",
        "llm_select_tool_workflow",
        "parse_tool_selection_output",
        "emit_tool_selection",
    ]:
        assert f'graph.add_node("{node_name}"' in graph_text

    assert 'graph.add_edge("tool_selection_intake", "load_tool_capability_cards")' in graph_text
    assert 'graph.add_edge("load_tool_capability_cards", "build_tool_selection_prompt")' in graph_text
    assert 'graph.add_edge("build_tool_selection_prompt", "llm_select_tool_workflow")' in graph_text
    assert 'graph.add_edge("llm_select_tool_workflow", "parse_tool_selection_output")' in graph_text
    assert 'graph.add_edge("parse_tool_selection_output", "emit_tool_selection")' in graph_text


def test_planner_does_not_import_permission_sql_rag_or_final_answer_internals() -> None:
    text = _production_text()

    for forbidden in [
        "services.permissions",
        "resolve_share_drive_permissions",
        "build_allowed_resource_map",
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


def test_planner_contains_no_keyword_or_deterministic_question_router() -> None:
    text = _production_text()

    assert "MAX_SELECTED_TOOLS" not in text
    assert "fallback to sql_rag" not in text.lower()
    assert not re.search(r"if .* in user_question", text)
    assert not re.search(r"if .* in question", text)
    assert "keyword classifier" not in text.lower()


def test_forbidden_fields_are_parser_blocklist_only_not_emitted_contract() -> None:
    service_text = (ROOT / "app" / "services" / "tool_selection_planner.py").read_text(encoding="utf-8")
    state_text = (ROOT / "app" / "graphs" / "tool_selection_planner" / "state.py").read_text(encoding="utf-8")

    assert "FORBIDDEN_OUTPUT_FIELD_PARTS" in service_text
    assert '("required", "tables")' in service_text
    assert "required_tables" not in state_text
    assert "sql_context" not in state_text


def test_main_graph_tool_selection_wrapper_is_thin_when_present() -> None:
    wrapper = ROOT / "app" / "graphs" / "main" / "nodes" / "tool_selection_planner.py"
    if not wrapper.exists():
        assert True
        return

    text = wrapper.read_text(encoding="utf-8")
    assert "run_tool_selection_planner" in text
    for forbidden in [
        "build_sql_context",
        "required_tables",
        "source_ids",
        "table_names",
        "raw_sql",
        "join_plan",
        "sample_rows",
        "column_profiles",
    ]:
        assert forbidden not in text
