from __future__ import annotations

from app.schemas.audit_trace import AuditEventCategory, AuditEventStatus, AuditFailure
from app.services.audit_trace import append_trace_entry, emit_audit_event
from app.tools.sql_rag.sql.contracts import public_sql_result
from app.tools.sql_rag.sql.state import ALLOWED_SQL_STATUSES, STATUS_ERROR, SqlState, empty_validated_output, safe_error


def emit_sql_failure(state: SqlState) -> SqlState:
    status = state.get("sql_status") if state.get("sql_status") in ALLOWED_SQL_STATUSES - {"success"} else STATUS_ERROR
    errors = state.get("errors") or [safe_error(state.get("failure_code") or "sql_failed", "SQL workflow failed.")]
    failure_code = state.get("failure_code") or "sql_failed"
    failed_node = state.get("failed_node") or "unknown"
    selected = state.get("selected_resources") or {}
    validated = state.get("validated_sql") or {}
    internal_audit = state.get("audit_metadata") or {}
    intent_diagnostics = {
        key: internal_audit[key]
        for key in (
            "intent_diagnostic_code",
            "fields_present",
            "filter_count",
            "metric_count",
            "grouping_count",
            "has_ranking",
        )
        if key in internal_audit
    }
    result = emit_audit_event(
        request_id=state.get("request_id"),
        trace_id=state.get("trace_id"),
        event_category=AuditEventCategory.SQL,
        event_type="sql_failure_emitted",
        status=AuditEventStatus.FAILED,
        workflow_name="sql_subgraph",
        node_name="emit_sql_failure",
        failure=AuditFailure(
            failed_workflow="sql_subgraph",
            failed_node=failed_node,
            failure_code=failure_code,
            failure_reason=errors[0].get("message", "SQL workflow failed."),
        ),
        metadata={
            "sql_status": status,
            "failed_node": failed_node,
            "failure_code": failure_code,
            "failure_reason": errors[0].get("message", "SQL workflow failed."),
            "selected_table_count": len(selected.get("tables") or []),
            "selected_column_count": len(selected.get("columns") or []),
            "sql_hash": validated.get("sql_hash") or (state.get("audit_metadata") or {}).get("sql_hash"),
        },
        restricted_metadata={
            "candidate_sql": state.get("candidate_sql"),
            "validation_messages": [failure_code],
            "referenced_columns": [column.get("column_name") for column in selected.get("columns", [])],
            "unselected_columns": [],
            **intent_diagnostics,
        },
    )
    audit_metadata = {
        "sql_status": status,
        "failure_code": failure_code,
        "failed_node": failed_node,
    }
    patch: SqlState = {
        "sql_status": status,
        "sql_result": public_sql_result(
            step_id=state.get("step_id", ""),
            status=status,
            validated_output=empty_validated_output(),
            limitations=state.get("limitations", []),
            errors=errors,
            audit_metadata=audit_metadata,
        ),
    }
    return append_trace_entry(patch, result.trace_entry)
