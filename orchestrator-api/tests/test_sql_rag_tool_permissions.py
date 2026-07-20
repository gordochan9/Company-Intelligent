from __future__ import annotations

import pytest

from app.tools.sql_rag.agent import run_sql_rag_agent
from app.tools.sql_rag.nodes.runtime_obligation_planner import set_runtime_obligation_planner_model


@pytest.fixture(autouse=True)
def reset_runtime_plan_model():
    set_runtime_obligation_planner_model(None)
    yield
    set_runtime_obligation_planner_model(None)


def _state() -> dict:
    return {
        "request_id": "req-sql-rag",
        "trace_id": "trace-sql-rag",
        "user_question": "What invoices are overdue?",
        "access_status": "ok",
        "trusted_user_context": {"email": "admin@demo.com"},
        "user_permission_schema": {"allowed_resources": {"allowed_structured_resources": ["structured:finance"]}},
        "tool_selection": {
            "status": "selected",
            "selected_tools": [{"tool": "sql_rag", "reason": "Company data request."}],
            "reason": "Company data request.",
            "limitations": [],
            "errors": [],
            "debug": {},
        },
        "trace": [],
    }


def test_access_not_ok_fails_closed_before_runtime_planning(monkeypatch: pytest.MonkeyPatch) -> None:
    called = False

    def model(_payload: dict) -> dict:
        nonlocal called
        called = True
        return {"status": "planned", "steps": []}

    set_runtime_obligation_planner_model(model)
    state = _state()
    state["access_status"] = "denied"

    result = run_sql_rag_agent(state)

    assert called is False
    assert result["tool_results"][0]["status"] == "access_failed"
    assert result["final_answer_context"]["status"] == "access_failed"


def test_missing_permission_context_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    state = _state()
    state.pop("user_permission_schema")

    result = run_sql_rag_agent(state)

    assert result["tool_results"][0]["status"] == "access_failed"
    assert result["tool_results"][0]["validated_output"]["validated_outputs"] == []


def test_missing_runtime_plan_model_fails_without_fallback() -> None:
    result = run_sql_rag_agent(_state())

    assert result["tool_results"][0]["status"] == "error"
    assert result["tool_results"][0]["errors"][0]["code"] == "runtime_plan_model_unavailable"
