from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from app.graphs.tool_selection_planner.state import (
    ALLOWED_STATUSES,
    STATUS_CLARIFICATION,
    STATUS_ERROR,
    STATUS_SELECTED,
    STATUS_UNSUPPORTED,
    error_selection,
    safe_error,
)


STATIC_TOOL_SELECTION_PROMPT = """You are the tool selection planner for the Project 3.0 main graph.

Your only job is to select which available tool workflow should handle the user request.

You must use only the provided tool capability cards.

Read the user question.
Read conversation_history to resolve follow-up references in the user question.
Read all available tool capability cards.
Select the available tool workflow or workflows that should handle the request.

Decision priority:
1. If one or more available tools can reasonably handle the request, select the tool.
2. Use clarification only when the request is so incomplete that no tool workflow can be selected.
3. Use unsupported only when the request is clear but none of the available tools can handle it.
4. Do not ask for clarification just because execution details are missing.
5. Do not ask for clarification about SQL, RAG, tables, sources, joins, retrieval, calculations, or evidence. Those decisions belong inside the selected tool workflow.
6. Do not choose unsupported if an available tool card can reasonably handle the request.
7. Do not invent tools.
8. Do not answer the user question.

You must not:
- check permission
- decide identity
- decide access
- decide SQL vs RAG
- decide SQL-only / RAG-only / mixed
- create execution steps
- list tables
- list sources
- list source IDs
- infer joins
- write SQL
- create retrieval queries
- retrieve document chunks
- perform calculations
- compose the final answer

Return only this JSON object:

{
  "status": "selected" | "clarification" | "unsupported" | "error",
  "selected_tools": [
    {
      "tool": "string",
      "reason": "string"
    }
  ],
  "reason": "string",
  "limitations": [],
  "errors": [],
  "debug": {}
}

Status rules:
- Use "selected" when an available tool should handle the request.
- Use "clarification" only when the request is too incomplete to choose any tool.
- Use "unsupported" only when the request is clear but outside all available tool cards.
- Use "error" only for a technical tool-selection failure.

Do not return deny.
Do not return access_failed.
Do not return permission_failed.
Do not return validation_failed.
Do not return execution steps.
Do not return SQL/RAG internal fields.
"""

FORBIDDEN_OUTPUT_FIELD_PARTS = {
    ("steps",),
    ("step", "type"),
    ("required", "tables"),
    ("required", "sources"),
    ("source", "ids"),
    ("table", "names"),
    ("sql", "context"),
    ("rag", "context"),
    ("raw", "sql"),
    ("join", "plan"),
    ("approved", "joins"),
    ("sample", "rows"),
    ("column", "profiles"),
    ("retrieval", "query"),
    ("sql", "mode"),
    ("rag", "mode"),
    ("mixed", "mode"),
}
FORBIDDEN_OUTPUT_FIELDS = {"_".join(parts) for parts in FORBIDDEN_OUTPUT_FIELD_PARTS}

_ToolSelectionModel = Callable[[str, dict[str, Any]], dict[str, Any] | str]
_tool_selection_model: _ToolSelectionModel | None = None
MAX_CONVERSATION_MESSAGES = 12
MAX_CONVERSATION_CONTENT_CHARS = 2000


class ToolSelectionModelUnavailable(RuntimeError):
    pass


def set_tool_selection_model(model: _ToolSelectionModel | None) -> None:
    global _tool_selection_model
    _tool_selection_model = model


def normalize_tool_cards(cards: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    normalized = []
    for card in cards or []:
        tool = card.get("tool")
        if not isinstance(tool, str) or not tool.strip():
            continue
        normalized.append(
            {
                "tool": tool,
                "display_name": card.get("display_name") or _display_name_for(tool),
                "description": card.get("description") or _description_for(tool),
                "capabilities": list(card.get("capabilities") or _capabilities_for(tool)),
                "not_for": list(card.get("not_for") or _not_for(tool)),
                "limitations": list(card.get("limitations") or []),
            }
        )
    return normalized


def build_tool_selection_prompt(
    user_question: str,
    tool_capability_cards: list[dict[str, Any]],
    messages: list[Any] | None = None,
) -> dict[str, Any]:
    return {
        "system_prompt": STATIC_TOOL_SELECTION_PROMPT,
        "payload": {
            "user_question": user_question,
            "conversation_history": conversation_history_from_messages(messages),
            "tool_capability_cards": tool_capability_cards,
        },
    }


def conversation_history_from_messages(messages: list[Any] | None) -> list[dict[str, str]]:
    history: list[dict[str, str]] = []
    for message in list(messages or [])[-MAX_CONVERSATION_MESSAGES:]:
        if not isinstance(message, dict):
            continue
        role = message.get("role")
        if role not in {"user", "assistant"}:
            continue
        content = _message_text(message.get("content"))
        if content:
            history.append({"role": role, "content": content[:MAX_CONVERSATION_CONTENT_CHARS]})
    return history


def _message_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for item in content:
        if isinstance(item, dict) and isinstance(item.get("text"), str):
            parts.append(item["text"])
    return "\n".join(parts).strip()


def select_tool_workflow(prompt: dict[str, Any]) -> dict[str, Any] | str:
    if _tool_selection_model is None:
        raise ToolSelectionModelUnavailable("No tool selection LLM model is configured.")
    try:
        return _tool_selection_model(prompt["system_prompt"], prompt["payload"])
    except Exception as exc:
        raise ToolSelectionModelUnavailable("Tool selection LLM model call failed.") from exc


def parse_tool_selection_output(raw_output: dict[str, Any] | str | None, available_tool_cards: list[dict[str, Any]]) -> dict[str, Any]:
    try:
        output = json.loads(raw_output) if isinstance(raw_output, str) else raw_output
    except json.JSONDecodeError:
        return error_selection("tool_selection_output_unreadable", "Unable to parse tool selection output.")

    if not isinstance(output, dict):
        return error_selection("tool_selection_output_unreadable", "Unable to parse tool selection output.")

    if FORBIDDEN_OUTPUT_FIELDS.intersection(output):
        return error_selection("tool_selection_forbidden_fields", "Tool selection output contained tool-internal fields.")

    status = output.get("status")
    if status not in ALLOWED_STATUSES:
        return error_selection("tool_selection_invalid_status", "Tool selection output used an invalid status.")

    selected_tools = _normalize_selected_tools(output.get("selected_tools"))
    if selected_tools is None:
        return error_selection("tool_selection_invalid_selected_tools", "Tool selection output used an invalid selected_tools value.")

    if status == STATUS_SELECTED:
        if not selected_tools:
            return error_selection("tool_selection_missing_selected_tool", "Tool selection output did not include a selected tool.")
        available_tools = {card["tool"] for card in available_tool_cards}
        if any(item["tool"] not in available_tools for item in selected_tools):
            return error_selection("tool_selection_unknown_tool", "Tool selection output selected an unavailable tool.")
    else:
        selected_tools = []

    return {
        "status": status,
        "selected_tools": selected_tools,
        "reason": str(output.get("reason") or _default_reason(status)),
        "limitations": _as_list(output.get("limitations")),
        "errors": _as_list(output.get("errors")),
        "debug": dict(output.get("debug") or {}),
    }


def _normalize_selected_tools(value: Any) -> list[dict[str, str]] | None:
    if not isinstance(value, list):
        return None
    selected = []
    for item in value:
        if not isinstance(item, dict):
            return None
        tool = item.get("tool")
        reason = item.get("reason")
        if not isinstance(tool, str) or not isinstance(reason, str):
            return None
        selected.append({"tool": tool, "reason": reason})
    return selected


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _default_reason(status: str) -> str:
    if status == STATUS_CLARIFICATION:
        return "The request is too incomplete to select a workflow."
    if status == STATUS_UNSUPPORTED:
        return "No available workflow can handle the request."
    if status == STATUS_ERROR:
        return "Tool selection failed."
    return "An available workflow should handle the request."


def _display_name_for(tool: str) -> str:
    if tool == "sql_rag":
        return "Company SQL/RAG Workflow"
    return tool


def _description_for(tool: str) -> str:
    if tool == "sql_rag":
        return "Answers company questions using approved structured data and document retrieval."
    return "Available backend workflow."


def _capabilities_for(tool: str) -> list[str]:
    if tool == "sql_rag":
        return [
            "company document lookup",
            "policy questions",
            "structured company data questions",
            "SQL-backed calculations",
            "RAG-backed evidence retrieval",
            "mixed SQL and RAG company answers",
        ]
    return []


def _not_for(tool: str) -> list[str]:
    if tool == "sql_rag":
        return [
            "sending emails",
            "creating calendar events",
            "changing permissions",
            "editing files",
            "external web browsing",
        ]
    return []


def model_unavailable_selection() -> dict[str, Any]:
    return {
        "status": STATUS_ERROR,
        "selected_tools": [],
        "reason": "Tool selection model is unavailable.",
        "limitations": [],
        "errors": [safe_error("tool_selection_model_unavailable", "Tool selection model is unavailable.")],
        "debug": {},
    }
