from __future__ import annotations

from app.graphs.tool_selection_planner.state import ALLOWED_STATUSES
from app.services.tool_selection_planner import (
    build_tool_selection_prompt,
    normalize_tool_cards,
    parse_tool_selection_output,
)


def test_prompt_uses_bounded_conversation_history_and_tool_cards_as_payload() -> None:
    prompt = build_tool_selection_prompt(
        "What are their names?",
        [{"tool": "sql_rag"}],
        [
            {"role": "system", "content": "ignored"},
            {"role": "user", "content": "For order 10250, how many products are there?"},
            {"role": "assistant", "content": "There are 3 products in order 10250."},
            {"role": "user", "content": "What are their names?"},
        ],
    )

    assert set(prompt) == {"system_prompt", "payload"}
    assert set(prompt["payload"]) == {"user_question", "conversation_history", "tool_capability_cards"}
    assert prompt["payload"]["conversation_history"] == [
        {"role": "user", "content": "For order 10250, how many products are there?"},
        {"role": "assistant", "content": "There are 3 products in order 10250."},
        {"role": "user", "content": "What are their names?"},
    ]
    assert "Read conversation_history to resolve follow-up references" in prompt["system_prompt"]
    assert "Do not ask for clarification just because execution details are missing." in prompt["system_prompt"]
    assert "Do not return deny." in prompt["system_prompt"]


def test_tool_cards_are_loaded_from_state_and_normalized_for_prompt() -> None:
    cards = normalize_tool_cards([{"tool": "sql_rag", "enabled": True, "limitations": ["limited"]}])

    assert cards == [
        {
            "tool": "sql_rag",
            "display_name": "Company SQL/RAG Workflow",
            "description": "Answers company questions using approved structured data and document retrieval.",
            "capabilities": [
                "company document lookup",
                "policy questions",
                "structured company data questions",
                "SQL-backed calculations",
                "RAG-backed evidence retrieval",
                "mixed SQL and RAG company answers",
            ],
            "not_for": [
                "sending emails",
                "creating calendar events",
                "changing permissions",
                "editing files",
                "external web browsing",
            ],
            "limitations": ["limited"],
        }
    ]


def test_selected_output_contract_is_route_level_only() -> None:
    result = parse_tool_selection_output(
        {
            "status": "selected",
            "selected_tools": [{"tool": "sql_rag", "reason": "Company workflow."}],
            "reason": "Use company workflow.",
        },
        [{"tool": "sql_rag"}],
    )

    assert result == {
        "status": "selected",
        "selected_tools": [{"tool": "sql_rag", "reason": "Company workflow."}],
        "reason": "Use company workflow.",
        "limitations": [],
        "errors": [],
        "debug": {},
    }
    assert set(result) == {"status", "selected_tools", "reason", "limitations", "errors", "debug"}


def test_allowed_statuses_exclude_permission_and_execution_statuses() -> None:
    assert ALLOWED_STATUSES == {"selected", "clarification", "unsupported", "error"}
    for forbidden in ["deny", "access_failed", "permission_failed", "validation_failed", "noop"]:
        assert forbidden not in ALLOWED_STATUSES


def test_parser_preserves_unsupported_and_does_not_fallback_to_sql_rag() -> None:
    result = parse_tool_selection_output(
        {
            "status": "unsupported",
            "selected_tools": [{"tool": "sql_rag", "reason": "Should not be preserved."}],
            "reason": "No available workflow can send email.",
        },
        [{"tool": "sql_rag"}],
    )

    assert result["status"] == "unsupported"
    assert result["selected_tools"] == []


def test_parser_rejects_unknown_selected_tool_without_guessing() -> None:
    result = parse_tool_selection_output(
        {
            "status": "selected",
            "selected_tools": [{"tool": "mailbox", "reason": "Find the invoice."}],
            "reason": "Use mailbox.",
        },
        [{"tool": "sql_rag"}],
    )

    assert result["status"] == "error"
    assert result["errors"][0]["code"] == "tool_selection_unknown_tool"


def test_parser_rejects_forbidden_tool_internal_fields() -> None:
    result = parse_tool_selection_output(
        {
            "status": "selected",
            "selected_tools": [{"tool": "sql_rag", "reason": "Company workflow."}],
            "reason": "Use company workflow.",
            "required_tables": ["invoice"],
        },
        [{"tool": "sql_rag"}],
    )

    assert result["status"] == "error"
    assert result["errors"][0]["code"] == "tool_selection_forbidden_fields"
