from __future__ import annotations

from typing import Any, TypedDict


class MainGraphState(TypedDict, total=False):
    request_id: str
    trace_id: str
    session_id: str | None
    user_question: str
    openwebui_user_identity: dict[str, Any]
    messages: list[dict[str, Any]]
    trace: list[dict[str, Any]]
    access_status: str
    trusted_user_context: dict[str, Any] | None
    user_permission_schema: dict[str, Any] | None
    tool_capability_cards: list[dict[str, Any]]
    permission_limitations: list[dict[str, Any]]
    permission_errors: list[dict[str, str]]
    tool_selection: dict[str, Any]
    tool_results: list[dict[str, Any]]
    final_answer_context: dict[str, Any] | None
    final_answer: str
    final_status: str
    public_citations: list[dict[str, Any]]
    public_limitations: list[dict[str, Any]]
    errors: list[dict[str, str]]


def safe_terminal_context(status: str, *, reason: str, limitations: list | None = None, errors: list | None = None) -> dict[str, Any]:
    return {
        "status": status,
        "tool": None,
        "answer_material": {"document_evidence": [], "structured_results": [], "mixed_findings": []},
        "citations": [],
        "limitations": list(limitations or []),
        "errors": list(errors or [{"code": status, "message": reason}]),
        "permission_safe_metadata": {},
    }
