from app.schemas.audit_trace import AuditEventCategory, AuditEventStatus
from app.services.audit_trace import REDACTED, emit_audit_event


def test_raw_sql_is_allowed_only_in_restricted_metadata() -> None:
    result = emit_audit_event(
        request_id="req-1",
        trace_id="trace-1",
        event_category=AuditEventCategory.SQL,
        event_type="sql_validated",
        status=AuditEventStatus.SUCCEEDED,
        workflow_name="sql_subgraph",
        node_name="validate_sql_before_execution",
        metadata={"raw_sql": "select * from finance"},
        restricted_metadata={"raw_sql": "select count(*) from finance"},
    )

    assert result.event.metadata["raw_sql"] == REDACTED
    assert result.event.restricted_metadata["raw_sql"] == "select count(*) from finance"
    assert result.trace_entry.metadata["raw_sql"] == REDACTED


def test_failed_emit_returns_result_instead_of_raising() -> None:
    result = emit_audit_event(
        request_id="req-1",
        trace_id="trace-1",
        event_category=AuditEventCategory.SYSTEM,
        event_type="bad_status",
        status="not-a-status",
    )

    assert result.status == AuditEventStatus.FAILED
    assert result.errors
