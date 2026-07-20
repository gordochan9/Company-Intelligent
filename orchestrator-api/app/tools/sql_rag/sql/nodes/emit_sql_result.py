from __future__ import annotations

from app.schemas.audit_trace import AuditEventCategory, AuditEventStatus
from app.services.audit_trace import append_trace_entry, emit_audit_event
from app.tools.sql_rag.sql.contracts import public_sql_result
from app.tools.sql_rag.sql.state import STATUS_SUCCESS, SqlState


def emit_sql_result(state: SqlState) -> SqlState:
    validated_output = dict(state.get("validated_sql_result") or {})
    selected = state.get("selected_resources") or {}
    rows = validated_output.get("rows") or []
    columns = validated_output.get("columns") or []
    result = emit_audit_event(
        request_id=state.get("request_id"),
        trace_id=state.get("trace_id"),
        event_category=AuditEventCategory.SQL,
        event_type="sql_result_emitted",
        status=AuditEventStatus.SUCCEEDED,
        workflow_name="sql_subgraph",
        node_name="emit_sql_result",
        metadata={
            **state.get("audit_metadata", {}),
            "row_count": validated_output.get("row_count", 0),
            "column_count": len(columns),
            "result_status": "success",
            "result_shape": "rows" if rows else "empty",
            "has_rows": bool(rows),
            "sql_hash": validated_output.get("sql_hash") or (state.get("audit_metadata") or {}).get("sql_hash"),
            "selected_table_count": len(selected.get("tables") or []),
            "selected_column_count": len(selected.get("columns") or []),
            "selected_filter_column_count": (state.get("audit_metadata") or {}).get("selected_filter_column_count", 0),
        },
        restricted_metadata={
            "result_columns": columns,
            "selected_columns": [column.get("column_name") for column in selected.get("columns", [])],
            "selected_filter_columns": [],
            "row_preview": rows[:5],
            "validated_sql": (state.get("validated_sql") or {}).get("sql"),
        },
    )
    patch: SqlState = {
        "sql_status": STATUS_SUCCESS,
        "sql_result": public_sql_result(
            step_id=state["step_id"],
            status=STATUS_SUCCESS,
            validated_output=validated_output,
            limitations=state.get("limitations", []),
            errors=[],
            audit_metadata=state.get("audit_metadata", {}),
        ),
    }
    return append_trace_entry(patch, result.trace_entry)
