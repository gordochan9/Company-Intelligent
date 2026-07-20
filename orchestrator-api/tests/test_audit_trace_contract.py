from app.schemas.audit_trace import AuditEventCategory, AuditEventStatus
from app.services.audit_trace import emit_audit_event


def test_emit_audit_event_creates_request_and_trace_ids() -> None:
    result = emit_audit_event(
        request_id=None,
        trace_id=None,
        event_category=AuditEventCategory.REQUEST,
        event_type="request_received",
        status=AuditEventStatus.STARTED,
        workflow_name="main",
        node_name="request_intake",
    )

    assert result.status == AuditEventStatus.SUCCEEDED
    assert result.event is not None
    assert result.event.request_id
    assert result.event.trace_id
    assert result.trace_entry is not None


def test_trace_entry_uses_same_status_vocabulary_as_audit_event() -> None:
    result = emit_audit_event(
        request_id="req-1",
        trace_id="trace-1",
        event_category=AuditEventCategory.PLANNER,
        event_type="planner_completed",
        status=AuditEventStatus.SUCCEEDED,
        workflow_name="tool_selection_planner",
        node_name="select_tool",
    )

    assert result.event.status == result.trace_entry.status


def test_emit_audit_event_persists_when_database_url_is_configured(monkeypatch) -> None:
    calls: list[tuple[str, tuple]] = []

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, sql: str, params: tuple) -> None:
            calls.append((sql, params))

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def cursor(self):
            return Cursor()

    monkeypatch.setenv("DATABASE_URL", "postgresql://project3:secret@postgres:5432/project3")
    monkeypatch.setattr("psycopg.connect", lambda _url: Connection())

    result = emit_audit_event(
        request_id="req-1",
        trace_id="trace-1",
        event_category=AuditEventCategory.REQUEST,
        event_type="request_received",
        status=AuditEventStatus.STARTED,
        workflow_name="main",
        node_name="request_intake",
        metadata={"api_key": "sk-test-value"},
    )

    assert result.status == AuditEventStatus.SUCCEEDED
    assert len(calls) == 1
    assert calls[0][1][4].obj["metadata"]["api_key"] == "[REDACTED]"
