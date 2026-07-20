from __future__ import annotations

from typing import Any, TypedDict


STATUS_SELECTED = "selected"
STATUS_CLARIFICATION = "clarification"
STATUS_UNSUPPORTED = "unsupported"
STATUS_ERROR = "error"
ALLOWED_STATUSES = {STATUS_SELECTED, STATUS_CLARIFICATION, STATUS_UNSUPPORTED, STATUS_ERROR}


class ToolSelectionPlannerState(TypedDict, total=False):
    request_id: str
    trace_id: str
    user_question: str
    messages: list[Any]
    conversation_context: dict[str, Any] | None
    tool_capability_cards: list[dict[str, Any]]
    available_tool_cards: list[dict[str, Any]]
    tool_selection_prompt: dict[str, Any]
    raw_llm_tool_selection: dict[str, Any] | str | None
    tool_selection: dict[str, Any] | None
    limitations: list[dict[str, Any]]
    errors: list[dict[str, str]]
    trace: list[dict[str, Any]]
    debug: dict[str, Any]


def safe_error(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def error_selection(code: str, message: str) -> dict[str, Any]:
    return {
        "status": STATUS_ERROR,
        "selected_tools": [],
        "reason": message,
        "limitations": [],
        "errors": [safe_error(code, message)],
        "debug": {},
    }
