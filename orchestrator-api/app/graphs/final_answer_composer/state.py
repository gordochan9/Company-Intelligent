from __future__ import annotations

from typing import Any, TypedDict


STATUS_RUNNING = "running"
STATUS_ERROR = "error"
STATUS_READY = "ready"

ALLOWED_CONTEXT_STATUSES = {
    "success",
    "denied",
    "access_failed",
    "unsupported",
    "clarification",
    "insufficient_evidence",
    "validation_failed",
    "error",
}

FINAL_STATUS_BY_CONTEXT = {
    "success": "answered",
    "denied": "denied",
    "access_failed": "access_failed",
    "unsupported": "unsupported",
    "clarification": "clarification",
    "insufficient_evidence": "insufficient_evidence",
    "validation_failed": "validation_failed",
    "error": "error",
}


class FinalAnswerComposerState(TypedDict, total=False):
    request_id: str
    trace_id: str
    user_question: str
    final_answer_context: dict[str, Any]
    answer_material: dict[str, Any]
    adapter_citations: list[dict[str, Any]]
    final_answer_llm_payload: dict[str, Any]
    raw_final_answer_llm_response: dict[str, Any] | str | None
    final_answer_llm_metadata: dict[str, Any]
    parsed_answer_text: str
    parsed_used_citation_ids: list[str]
    public_citations: list[dict[str, Any]]
    public_limitations: list[dict[str, Any]]
    final_answer: str
    final_status: str
    errors: list[dict[str, str]]
    limitations: list[dict[str, Any]]
    unknown_citation_ids: list[str]
    composer_status: str
    failed_node: str | None
    failure_code: str | None
    trace: list[dict[str, Any]]


def safe_error(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def fail_state(node: str, code: str, message: str) -> FinalAnswerComposerState:
    return {
        "composer_status": STATUS_ERROR,
        "failed_node": node,
        "failure_code": code,
        "errors": [safe_error(code, message)],
        "final_status": STATUS_ERROR,
        "final_answer": "I cannot produce a safe final answer for this request.",
        "public_citations": [],
    }
