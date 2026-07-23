from __future__ import annotations

import pytest

from app.graphs.tool_selection_planner.graph import invoke_tool_selection_planner_subgraph
from app.services.tool_selection_planner import set_tool_selection_model


SQL_RAG_CARD = [{"tool": "sql_rag", "enabled": True}]


@pytest.fixture(autouse=True)
def reset_tool_selection_model():
    set_tool_selection_model(None)
    yield
    set_tool_selection_model(None)


def _state(question: str) -> dict:
    return {
        "request_id": "req-tool-selection",
        "trace_id": "trace-tool-selection",
        "user_question": question,
        "tool_capability_cards": SQL_RAG_CARD,
        "messages": [],
        "conversation_context": {},
    }


def _select_sql_rag_model(_prompt: str, _payload: dict) -> dict:
    return {
        "status": "selected",
        "selected_tools": [{"tool": "sql_rag", "reason": "The SQL/RAG workflow can handle this company request."}],
        "reason": "The available SQL/RAG workflow can answer this company request.",
        "limitations": [],
        "errors": [],
        "debug": {},
    }


@pytest.mark.parametrize(
    "question",
    [
        "Who had the highest sales last month?",
        "How many invoices are overdue?",
        "What does the HR policy say about sick leave?",
        "Compare sales performance and related policy implication.",
    ],
)
def test_company_questions_select_sql_rag_without_over_clarification(question: str) -> None:
    set_tool_selection_model(_select_sql_rag_model)

    result = invoke_tool_selection_planner_subgraph(_state(question))

    assert result["tool_selection"]["status"] == "selected"
    assert result["tool_selection"]["selected_tools"] == [
        {"tool": "sql_rag", "reason": "The SQL/RAG workflow can handle this company request."}
    ]


def test_tool_selection_model_receives_conversation_history_for_followup() -> None:
    captured: dict = {}

    def model(_prompt: str, payload: dict) -> dict:
        captured.update(payload)
        return _select_sql_rag_model(_prompt, payload)

    set_tool_selection_model(model)
    state = _state("What are their names?")
    state["messages"] = [
        {"role": "user", "content": "For order 10250, how many products are there?"},
        {"role": "assistant", "content": "There are 3 products in order 10250."},
        {"role": "user", "content": "What are their names?"},
    ]

    invoke_tool_selection_planner_subgraph(state)

    assert captured["conversation_history"] == state["messages"]


def test_ambiguous_question_can_return_clarification() -> None:
    set_tool_selection_model(
        lambda _prompt, _payload: {
            "status": "clarification",
            "selected_tools": [],
            "reason": "The request is too incomplete to select a workflow.",
            "limitations": [],
            "errors": [],
            "debug": {},
        }
    )

    result = invoke_tool_selection_planner_subgraph(_state("Check this for me."))

    assert result["tool_selection"]["status"] == "clarification"
    assert result["tool_selection"]["selected_tools"] == []


def test_email_calendar_action_request_returns_unsupported() -> None:
    set_tool_selection_model(
        lambda _prompt, _payload: {
            "status": "unsupported",
            "selected_tools": [],
            "reason": "No available workflow sends email or books meetings.",
            "limitations": [],
            "errors": [],
            "debug": {},
        }
    )

    result = invoke_tool_selection_planner_subgraph(_state("Book a meeting tomorrow."))

    assert result["tool_selection"]["status"] == "unsupported"
    assert result["tool_selection"]["selected_tools"] == []


def test_unreadable_llm_output_returns_error() -> None:
    set_tool_selection_model(lambda _prompt, _payload: "not json")

    result = invoke_tool_selection_planner_subgraph(_state("Who had the highest sales last month?"))

    assert result["tool_selection"]["status"] == "error"
    assert result["tool_selection"]["errors"] == [
        {"code": "tool_selection_output_unreadable", "message": "Unable to parse tool selection output."}
    ]


def test_missing_llm_model_returns_error_without_fallback_selection() -> None:
    result = invoke_tool_selection_planner_subgraph(_state("Who had the highest sales last month?"))

    assert result["tool_selection"]["status"] == "error"
    assert result["tool_selection"]["selected_tools"] == []
    assert result["tool_selection"]["errors"][0]["code"] == "tool_selection_model_unavailable"
