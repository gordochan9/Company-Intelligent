from __future__ import annotations

from app.schemas.audit_trace import AuditEventCategory, AuditEventStatus
from app.services.audit_trace import emit_audit_event
from app.tools.sql_rag.sql.services.executor import validate_execution_result
from app.tools.sql_rag.sql.state import SqlState, fail_state


def validate_sql_result(state: SqlState) -> SqlState:
    result = state.get("execution_result")
    validated = state.get("validated_sql") or {}
    if not isinstance(result, dict):
        return fail_state("validate_sql_result", "missing_sql_execution_result", "SQL execution result is unavailable.")
    try:
        validated_result = validate_execution_result(result, validated.get("sql_hash", ""))
    except ValueError as exc:
        return fail_state("validate_sql_result", str(exc), "SQL result validation failed.")
    rows = validated_result.get("rows") or []
    columns = validated_result.get("columns") or []
    emit_audit_event(
        request_id=state.get("request_id"),
        trace_id=state.get("trace_id"),
        event_category=AuditEventCategory.SQL,
        event_type="sql_result_validated",
        status=AuditEventStatus.SUCCEEDED,
        workflow_name="sql_subgraph",
        node_name="validate_sql_result",
        metadata={
            "result_status": "validated",
            "row_count": validated_result.get("row_count", 0),
            "column_count": len(columns),
            "has_rows": bool(rows),
            "result_shape": "rows" if rows else "empty",
            "limitations_count": len(state.get("limitations", [])),
        },
        restricted_metadata={
            "result_columns": columns,
            "row_preview": rows[:5],
        },
        include_trace_entry=False,
    )
    return {"validated_sql_result": validated_result}
