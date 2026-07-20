from __future__ import annotations

from app.schemas.audit_trace import AuditEventCategory, AuditEventStatus
from app.services.audit_trace import emit_audit_event
from app.tools.sql_rag.sql.services.repository import list_structured_resources
from app.tools.sql_rag.sql.services.schema import build_filtered_schema
from app.tools.sql_rag.sql.state import STATUS_INSUFFICIENT, SqlState, fail_state


def build_permission_filtered_sql_schema(state: SqlState) -> SqlState:
    try:
        resources = list_structured_resources()
    except RuntimeError:
        return fail_state(
            "build_permission_filtered_sql_schema",
            "sql_runtime_store_unavailable",
            "SQL runtime store is unavailable.",
        )
    schema = build_filtered_schema(
        request_id=state["request_id"],
        step_id=state["step_id"],
        user_permission_schema=state["user_permission_schema"],
        resources=resources,
    )
    if not schema["structured_resources"]:
        return fail_state(
            "build_permission_filtered_sql_schema",
            "no_allowed_structured_resources",
            "No permitted structured resources are available for this SQL step.",
            status=STATUS_INSUFFICIENT,
        )
    allowed_resources = (state.get("user_permission_schema") or {}).get("allowed_resources", {})
    allowed_scope_count = len(allowed_resources.get("allowed_scopes") or [])
    allowed_column_count = sum(len(resource.get("columns", [])) for resource in schema["structured_resources"])
    emit_audit_event(
        request_id=state.get("request_id"),
        trace_id=state.get("trace_id"),
        event_category=AuditEventCategory.SQL,
        event_type="filtered_sql_schema_built",
        status=AuditEventStatus.SUCCEEDED,
        workflow_name="sql_subgraph",
        node_name="build_permission_filtered_sql_schema",
        metadata={
            "structured_resource_count": len(schema["structured_resources"]),
            "allowed_resource_count": len(allowed_resources.get("allowed_structured_resources") or []),
            "allowed_table_count": len(schema["structured_resources"]),
            "allowed_column_count": allowed_column_count,
            "permission_scope_count": allowed_scope_count,
        },
        restricted_metadata={
            "selected_resource_labels": [resource.get("display_name") for resource in schema["structured_resources"]],
        },
        include_trace_entry=False,
    )
    return {"filtered_sql_schema": schema, "audit_metadata": {"structured_resource_count": len(schema["structured_resources"])}}
