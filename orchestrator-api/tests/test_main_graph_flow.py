from __future__ import annotations

import pytest

from app.graphs.final_answer_composer.nodes.call_final_answer_llm import set_final_answer_model
from app.graphs.main.graph import run_main_graph
from app.services.tool_selection_planner import set_tool_selection_model


@pytest.fixture(autouse=True)
def reset_models():
    set_tool_selection_model(None)
    set_final_answer_model(None)
    yield
    set_tool_selection_model(None)
    set_final_answer_model(None)


def _state() -> dict:
    return {
        "request_id": "req-main",
        "trace_id": "trace-main",
        "user_question": "What invoices are overdue?",
        "openwebui_user_identity": {"email": "admin@demo.com", "auth_source": "openwebui"},
        "messages": [],
        "trace": [],
    }


def test_main_graph_routes_permission_planner_sql_rag_and_final_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    tool_called = False
    set_tool_selection_model(
        lambda _prompt, _payload: {
            "status": "selected",
            "selected_tools": [{"tool": "sql_rag", "reason": "Company data request."}],
            "reason": "Company data request.",
            "limitations": [],
            "errors": [],
            "debug": {},
        }
    )
    set_final_answer_model(lambda _payload: {"answer_text": "Overdue amount is 100.", "used_citation_ids": []})

    def sql_rag_agent(state: dict) -> dict:
        nonlocal tool_called
        tool_called = True
        assert state["access_status"] == "ok"
        return {
            "tool_results": [{"tool": "sql_rag", "status": "success", "validated_output": {}, "limitations": [], "errors": [], "audit_metadata": {}}],
            "final_answer_context": {
                "status": "success",
                "tool": "sql_rag",
                "answer_material": {"structured_results": [{"amount": 100}]},
                "citations": [],
                "limitations": [],
                "errors": [],
            },
            "trace": state.get("trace", []),
        }

    monkeypatch.setattr("app.graphs.main.nodes.tool_dispatch.run_sql_rag_agent", sql_rag_agent)

    result = run_main_graph(_state())

    assert tool_called is True
    assert result["final_status"] == "answered"
    assert result["final_answer"] == "Overdue amount is 100."


def test_access_failure_skips_planner_and_tool_dispatch(monkeypatch: pytest.MonkeyPatch) -> None:
    tool_called = False
    planner_called = False
    set_final_answer_model(lambda _payload: {"answer_text": "Access failed.", "used_citation_ids": []})

    def planner(_state: dict) -> dict:
        nonlocal planner_called
        planner_called = True
        return {}

    def tool(_state: dict) -> dict:
        nonlocal tool_called
        tool_called = True
        return {}

    monkeypatch.setattr("app.graphs.main.nodes.tool_selection_planner.run_tool_selection_planner", planner)
    monkeypatch.setattr("app.graphs.main.nodes.tool_dispatch.run_sql_rag_agent", tool)
    state = _state()
    state["openwebui_user_identity"] = {}

    result = run_main_graph(state)

    assert planner_called is False
    assert tool_called is False
    assert result["final_status"] == "access_failed"


def test_planner_unsupported_skips_tool_dispatch(monkeypatch: pytest.MonkeyPatch) -> None:
    tool_called = False
    set_tool_selection_model(
        lambda _prompt, _payload: {
            "status": "unsupported",
            "selected_tools": [],
            "reason": "No approved tool can handle this.",
            "limitations": [],
            "errors": [],
            "debug": {},
        }
    )
    set_final_answer_model(lambda _payload: {"answer_text": "Unsupported.", "used_citation_ids": []})

    def tool(_state: dict) -> dict:
        nonlocal tool_called
        tool_called = True
        return {}

    monkeypatch.setattr("app.graphs.main.nodes.tool_dispatch.run_sql_rag_agent", tool)

    result = run_main_graph(_state())

    assert tool_called is False
    assert result["final_status"] == "unsupported"
