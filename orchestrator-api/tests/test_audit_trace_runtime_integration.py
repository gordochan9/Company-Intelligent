from app.schemas.audit_trace import AuditEventCategory, AuditEventStatus
from app.services.audit_trace import append_trace_entry, emit_audit_event


def test_append_trace_entry_adds_safe_trace_to_state_patch() -> None:
    result = emit_audit_event(
        request_id="req-1",
        trace_id="trace-1",
        event_category=AuditEventCategory.DISPATCH,
        event_type="tool_dispatch_started",
        status=AuditEventStatus.STARTED,
        workflow_name="main",
        node_name="tool_dispatch",
        metadata={"raw_sql": "select * from restricted_table"},
    )

    patch = append_trace_entry({}, result.trace_entry)

    assert patch["trace"][0]["metadata"]["raw_sql"] == "[REDACTED]"
