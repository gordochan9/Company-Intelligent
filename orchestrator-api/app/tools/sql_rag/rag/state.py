from __future__ import annotations

from typing import Any, TypedDict


STATUS_RUNNING = "running"
STATUS_SUCCESS = "success"
STATUS_INSUFFICIENT = "insufficient_evidence"
STATUS_ERROR = "error"
ALLOWED_RAG_STATUSES = {STATUS_SUCCESS, STATUS_INSUFFICIENT, STATUS_ERROR}


class RagState(TypedDict, total=False):
    request_id: str
    trace_id: str
    step_id: str
    rag_question: str
    step_goal: str
    obligations: list[dict[str, str]]
    trusted_user_context: dict[str, Any]
    user_permission_schema: dict[str, Any]
    dependency_context: dict[str, Any]
    conversation_context: dict[str, Any] | None
    filtered_rag_schema: dict[str, Any] | None
    llm_readable_rag_schema: dict[str, Any] | None
    rag_search_plan: dict[str, Any] | None
    raw_rag_search_plan: dict[str, Any] | str | None
    selected_documents: list[dict[str, Any]]
    retrieved_chunks: list[dict[str, Any]]
    validated_evidence: list[dict[str, Any]]
    validated_citations: list[dict[str, Any]]
    rag_status: str
    limitations: list[dict[str, Any]]
    errors: list[dict[str, str]]
    audit_metadata: dict[str, Any]
    debug: dict[str, Any]
    failed_node: str | None
    failure_code: str | None
    trace: list[dict[str, Any]]
    rag_result: dict[str, Any]


def safe_error(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def fail_state(node: str, code: str, message: str, *, status: str = STATUS_ERROR) -> RagState:
    return {
        "rag_status": status,
        "failed_node": node,
        "failure_code": code,
        "errors": [safe_error(code, message)],
    }


def empty_validated_output() -> dict[str, Any]:
    return {
        "document_findings": [],
        "validated_evidence": [],
        "validated_citations": [],
        "retrieval_metadata": {},
    }
