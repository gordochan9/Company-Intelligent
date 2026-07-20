from __future__ import annotations

from typing import Any, TypedDict


STATUS_NOT_STARTED = "not_started"
STATUS_PLANNED = "planned"
STATUS_PLANNING_FAILED = "planning_failed"
STATUS_INVALID_PLAN = "invalid_plan"
STATUS_RUNNING = "running"
STATUS_COMPLETE = "complete"
STATUS_BLOCKED = "blocked"
STATUS_ERROR = "error"

RESULT_SUCCESS = "success"
RESULT_INSUFFICIENT = "insufficient_evidence"
RESULT_VALIDATION_FAILED = "validation_failed"
RESULT_ACCESS_FAILED = "access_failed"
RESULT_ERROR = "error"

TERMINAL_RESULT_STATUSES = {
    RESULT_SUCCESS,
    RESULT_INSUFFICIENT,
    RESULT_VALIDATION_FAILED,
    RESULT_ACCESS_FAILED,
    RESULT_ERROR,
}


class SqlRagState(TypedDict, total=False):
    request_id: str
    trace_id: str
    session_id: str | None
    user_question: str
    messages: list[dict[str, Any]]
    conversation_context: dict[str, Any] | None
    access_status: str
    trusted_user_context: dict[str, Any]
    user_permission_schema: dict[str, Any]
    tool_selection: dict[str, Any]
    runtime_plan: dict[str, Any] | None
    runtime_plan_status: str
    current_step: dict[str, Any] | None
    current_child_result: dict[str, Any] | None
    completed_steps: list[str]
    covered_obligation_ids: list[str]
    step_results: list[dict[str, Any]]
    dependency_context: dict[str, Any]
    final_result_bundle: dict[str, Any] | None
    tool_result: dict[str, Any] | None
    tool_results: list[dict[str, Any]]
    final_answer_context: dict[str, Any] | None
    limitations: list[dict[str, Any]]
    errors: list[dict[str, str]]
    audit_metadata: dict[str, Any]
    debug: dict[str, Any]
    failed_node: str | None
    failure_code: str | None
    trace: list[dict[str, Any]]


def safe_error(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def fail_state(
    node: str,
    code: str,
    message: str,
    *,
    status: str = STATUS_ERROR,
    result_status: str | None = None,
) -> SqlRagState:
    result_status = {
        STATUS_INVALID_PLAN: RESULT_VALIDATION_FAILED,
        STATUS_PLANNING_FAILED: RESULT_ERROR,
        STATUS_BLOCKED: RESULT_ERROR,
    }.get(status, RESULT_ERROR) if result_status is None else result_status
    return {
        "runtime_plan_status": status,
        "failed_node": node,
        "failure_code": code,
        "errors": [safe_error(code, message)],
        "final_result_bundle": _empty_bundle(result_status, [safe_error(code, message)]),
    }


def _empty_bundle(status: str, errors: list[dict[str, str]] | None = None) -> dict[str, Any]:
    return {
        "tool": "sql_rag",
        "status": status,
        "validated_outputs": [],
        "validated_evidence": [],
        "validated_citations": [],
        "validated_sql_rows": [],
        "limitations": [],
        "errors": list(errors or []),
        "audit_metadata": {},
    }
