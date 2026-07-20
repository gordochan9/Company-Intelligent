from __future__ import annotations

import hashlib

from app.schemas.audit_trace import AuditEventCategory, AuditEventStatus
from app.services.audit_trace import emit_audit_event
from app.tools.sql_rag.sql.contracts import require_sql_input
from app.tools.sql_rag.sql.state import STATUS_ACCESS_FAILED, STATUS_RUNNING, SqlState, fail_state


def sql_intake(state: SqlState) -> SqlState:
    request_id = state.get("request_id")
    trace_id = state.get("trace_id")
    base_metadata = {
        "sql_question_hash": _hash_text(str(state.get("sql_question") or state.get("step_goal") or "")),
        "has_permission_schema": isinstance(state.get("user_permission_schema"), dict),
        "access_status": state.get("access_status"),
        "request_id": request_id,
        "trace_id": trace_id,
        "workflow_name": "sql_subgraph",
        "node_name": "sql_intake",
    }
    emit_audit_event(
        request_id=request_id,
        trace_id=trace_id,
        event_category=AuditEventCategory.SQL,
        event_type="sql_intake_started",
        status=AuditEventStatus.STARTED,
        workflow_name="sql_subgraph",
        node_name="sql_intake",
        metadata=base_metadata,
        include_trace_entry=False,
    )
    try:
        require_sql_input(state)
    except PermissionError as exc:
        emit_audit_event(
            request_id=request_id,
            trace_id=trace_id,
            event_category=AuditEventCategory.SQL,
            event_type="sql_intake_failed",
            status=AuditEventStatus.ACCESS_FAILED,
            workflow_name="sql_subgraph",
            node_name="sql_intake",
            metadata={**base_metadata, "failure_code": str(exc)},
            include_trace_entry=False,
        )
        return fail_state("sql_intake", str(exc), "SQL permission context is missing or malformed.", status=STATUS_ACCESS_FAILED)
    except ValueError as exc:
        emit_audit_event(
            request_id=request_id,
            trace_id=trace_id,
            event_category=AuditEventCategory.SQL,
            event_type="sql_intake_failed",
            status=AuditEventStatus.FAILED,
            workflow_name="sql_subgraph",
            node_name="sql_intake",
            metadata={**base_metadata, "failure_code": str(exc)},
            include_trace_entry=False,
        )
        return fail_state("sql_intake", str(exc), "SQL input is missing or malformed.")
    emit_audit_event(
        request_id=request_id,
        trace_id=trace_id,
        event_category=AuditEventCategory.SQL,
        event_type="sql_intake_completed",
        status=AuditEventStatus.SUCCEEDED,
        workflow_name="sql_subgraph",
        node_name="sql_intake",
        metadata=base_metadata,
        include_trace_entry=False,
    )
    return {
        "request_id": state["request_id"],
        "trace_id": state.get("trace_id", ""),
        "step_id": state["step_id"],
        "sql_question": str(state.get("sql_question") or state.get("step_goal") or ""),
        "step_goal": str(state.get("step_goal") or ""),
        "obligations": list(state.get("obligations") or []),
        "trusted_user_context": dict(state["trusted_user_context"]),
        "user_permission_schema": dict(state["user_permission_schema"]),
        "dependency_context": dict(state.get("dependency_context") or {}),
        "conversation_context": state.get("conversation_context"),
        "filtered_sql_schema": None,
        "llm_readable_sql_schema": None,
        "approved_join_runtime_map": {},
        "sql_query_intent": None,
        "selected_resources": None,
        "candidate_sql": None,
        "unbound_parameter_regeneration_count": 0,
        "validated_sql": None,
        "execution_result": None,
        "validated_sql_result": None,
        "sql_status": STATUS_RUNNING,
        "limitations": [],
        "errors": [],
        "audit_metadata": {},
        "debug": {},
        "failed_node": None,
        "failure_code": None,
        "trace": list(state.get("trace", [])),
    }


def _hash_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()
