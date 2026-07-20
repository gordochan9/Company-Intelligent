from __future__ import annotations

from app.graphs.tool_selection_planner.state import STATUS_SELECTED, ToolSelectionPlannerState
from app.schemas.audit_trace import AuditEventCategory, AuditEventStatus
from app.services.audit_trace import append_trace_entry, emit_audit_event


def emit_tool_selection(state: ToolSelectionPlannerState) -> ToolSelectionPlannerState:
    selection = state.get("tool_selection") or {
        "status": "error",
        "selected_tools": [],
        "reason": "Tool selection failed.",
        "limitations": [],
        "errors": [{"code": "tool_selection_missing", "message": "Tool selection failed."}],
        "debug": {},
    }
    event_status = AuditEventStatus.SUCCEEDED if selection.get("status") == STATUS_SELECTED else AuditEventStatus.FAILED
    result = emit_audit_event(
        request_id=state.get("request_id"),
        trace_id=state.get("trace_id"),
        event_category=AuditEventCategory.PLANNER,
        event_type="tool_selection_emitted",
        status=event_status,
        workflow_name="tool_selection_planner",
        node_name="emit_tool_selection",
        metadata={"tool_selection_status": selection.get("status")},
    )
    patch: ToolSelectionPlannerState = {"tool_selection": selection}
    return append_trace_entry(patch, result.trace_entry)
