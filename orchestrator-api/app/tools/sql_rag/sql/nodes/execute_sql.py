from __future__ import annotations

from time import perf_counter

from app.schemas.audit_trace import AuditEventCategory, AuditEventStatus, AuditFailure
from app.services.audit_trace import emit_audit_event
from app.tools.sql_rag.sql.services.executor import SqlExecutionFailed, SqlExecutorUnavailable, execute_validated_sql
from app.tools.sql_rag.sql.state import STATUS_ACCESS_FAILED, STATUS_VALIDATION_FAILED, SqlState, fail_state


def execute_sql(state: SqlState) -> SqlState:
    validated = state.get("validated_sql")
    if not isinstance(validated, dict):
        return fail_state("execute_sql", "missing_validated_sql", "Validated SQL is unavailable.")
    allowed_resources = (state.get("user_permission_schema") or {}).get("allowed_resources", {})
    execution_payload = {
        **validated,
        "permission_scope_keys": [item for item in allowed_resources.get("allowed_scopes", []) if isinstance(item, str)],
        "permission_resource_keys": [
            item for item in allowed_resources.get("allowed_structured_resources", []) if isinstance(item, str)
        ],
    }
    started = perf_counter()
    try:
        result = execute_validated_sql(execution_payload)
    except PermissionError:
        _emit_execution_failed(state, "restricted_sql_access_failed", "Restricted SQL execution was not allowed.")
        return fail_state("execute_sql", "restricted_sql_access_failed", "Restricted SQL execution was not allowed.", status=STATUS_ACCESS_FAILED)
    except SqlExecutorUnavailable:
        _emit_execution_failed(state, "sql_executor_unavailable", "Restricted SQL executor is unavailable.")
        return fail_state("execute_sql", "sql_executor_unavailable", "Restricted SQL executor is unavailable.")
    except SqlExecutionFailed:
        _emit_execution_failed(state, "sql_execution_failed", "SQL execution failed.")
        return fail_state("execute_sql", "sql_execution_failed", "SQL execution failed.", status=STATUS_VALIDATION_FAILED)
    duration_ms = int((perf_counter() - started) * 1000)
    rows = result.get("rows") if isinstance(result, dict) else []
    columns = result.get("columns") if isinstance(result, dict) else []
    emit_audit_event(
        request_id=state.get("request_id"),
        trace_id=state.get("trace_id"),
        event_category=AuditEventCategory.SQL,
        event_type="sql_execution_completed",
        status=AuditEventStatus.SUCCEEDED,
        workflow_name="sql_subgraph",
        node_name="execute_sql",
        duration_ms=duration_ms,
        metadata={
            "sql_hash": validated.get("sql_hash"),
            "row_count": len(rows) if isinstance(rows, list) else 0,
            "column_count": len(columns) if isinstance(columns, list) else 0,
            "execution_status": "completed",
            "execution_duration_ms": duration_ms,
        },
        restricted_metadata={
            "result_columns": columns if isinstance(columns, list) else [],
            "row_preview": rows[:5] if isinstance(rows, list) else [],
        },
        include_trace_entry=False,
    )
    return {"execution_result": result}


def _emit_execution_failed(state: SqlState, failure_code: str, failure_reason: str) -> None:
    validated = state.get("validated_sql") if isinstance(state.get("validated_sql"), dict) else {}
    emit_audit_event(
        request_id=state.get("request_id"),
        trace_id=state.get("trace_id"),
        event_category=AuditEventCategory.SQL,
        event_type="sql_execution_failed",
        status=AuditEventStatus.FAILED,
        workflow_name="sql_subgraph",
        node_name="execute_sql",
        failure=AuditFailure(
            failed_workflow="sql_subgraph",
            failed_node="execute_sql",
            failure_code=failure_code,
            failure_reason=failure_reason,
        ),
        metadata={
            "sql_hash": validated.get("sql_hash"),
            "row_count": 0,
            "column_count": 0,
            "execution_status": "failed",
            "failure_code": failure_code,
        },
        restricted_metadata={"validated_sql": validated.get("sql")},
        include_trace_entry=False,
    )
