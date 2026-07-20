from app.schemas.audit_trace import AuditEventCategory, AuditEventStatus
from app.services.audit_trace import build_request_timeline, emit_audit_event


def test_request_timeline_orders_events_by_time_and_sequence() -> None:
    first = emit_audit_event(
        request_id="req-1",
        trace_id="trace-1",
        event_sequence=1,
        event_category=AuditEventCategory.REQUEST,
        event_type="request_received",
        status=AuditEventStatus.STARTED,
        workflow_name="main",
        node_name="request_intake",
    ).event
    second = emit_audit_event(
        request_id="req-1",
        trace_id="trace-1",
        event_sequence=2,
        event_category=AuditEventCategory.PERMISSION,
        event_type="permission_completed",
        status=AuditEventStatus.SUCCEEDED,
        workflow_name="permission_schema",
        node_name="emit_permission_schema",
    ).event

    timeline = build_request_timeline([second, first])

    assert [row.event_sequence for row in timeline] == [1, 2]
    assert timeline[0].event_type == "request_received"
