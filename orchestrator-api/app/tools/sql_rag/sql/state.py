from __future__ import annotations

from typing import Any, TypedDict


STATUS_RUNNING = "running"
STATUS_SUCCESS = "success"
STATUS_INSUFFICIENT = "insufficient_evidence"
STATUS_VALIDATION_FAILED = "validation_failed"
STATUS_ACCESS_FAILED = "access_failed"
STATUS_ERROR = "error"
ALLOWED_SQL_STATUSES = {STATUS_SUCCESS, STATUS_INSUFFICIENT, STATUS_VALIDATION_FAILED, STATUS_ACCESS_FAILED, STATUS_ERROR}


class SqlState(TypedDict, total=False):
    request_id: str
    trace_id: str
    step_id: str
    sql_question: str
    step_goal: str
    obligations: list[dict[str, str]]
    trusted_user_context: dict[str, Any]
    user_permission_schema: dict[str, Any]
    dependency_context: dict[str, Any]
    conversation_context: dict[str, Any] | None
    filtered_sql_schema: dict[str, Any] | None
    llm_readable_sql_schema: dict[str, Any] | None
    approved_join_runtime_map: dict[str, Any]
    sql_query_intent: dict[str, Any] | None
    selected_resources: dict[str, Any] | None
    candidate_sql: str | None
    unbound_parameter_regeneration_count: int
    validated_sql: dict[str, Any] | None
    execution_result: dict[str, Any] | None
    validated_sql_result: dict[str, Any] | None
    sql_status: str
    limitations: list[dict[str, Any]]
    errors: list[dict[str, str]]
    audit_metadata: dict[str, Any]
    debug: dict[str, Any]
    failed_node: str | None
    failure_code: str | None
    trace: list[dict[str, Any]]
    sql_result: dict[str, Any]


def safe_error(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def fail_state(node: str, code: str, message: str, *, status: str = STATUS_ERROR) -> SqlState:
    return {
        "sql_status": status,
        "failed_node": node,
        "failure_code": code,
        "errors": [safe_error(code, message)],
    }


def empty_validated_output() -> dict[str, Any]:
    return {
        "rows": [],
        "columns": [],
        "row_count": 0,
        "sql_hash": None,
        "calculation_metadata": {},
        "execution_metadata": {},
    }
