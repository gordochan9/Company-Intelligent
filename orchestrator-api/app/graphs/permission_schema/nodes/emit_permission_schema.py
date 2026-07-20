from __future__ import annotations

from app.graphs.permission_schema.state import ACCESS_OK, PermissionSchemaState
from app.schemas.audit_trace import AuditEventCategory, AuditEventStatus
from app.services.audit_trace import append_trace_entry, emit_audit_event


def emit_permission_schema(state: PermissionSchemaState) -> PermissionSchemaState:
    status = state.get("access_status", "access_failed")
    event_status = AuditEventStatus.SUCCEEDED if status == ACCESS_OK else AuditEventStatus.FAILED
    result = emit_audit_event(
        request_id=state.get("request_id"),
        trace_id=state.get("trace_id"),
        event_category=AuditEventCategory.PERMISSION,
        event_type="permission_schema_emitted",
        status=event_status,
        workflow_name="permission_schema",
        node_name="emit_permission_schema",
        metadata={"access_status": status},
    )
    patch: PermissionSchemaState = {
        "access_status": status,
        "trusted_user_context": state.get("trusted_user_context"),
        "user_permission_schema": state.get("user_permission_schema") if status == ACCESS_OK else None,
        "tool_capability_cards": state.get("tool_capability_cards", []) if status == ACCESS_OK else [],
        "permission_limitations": state.get("permission_limitations", []),
        "permission_errors": state.get("permission_errors", []),
    }
    return append_trace_entry(patch, result.trace_entry)
