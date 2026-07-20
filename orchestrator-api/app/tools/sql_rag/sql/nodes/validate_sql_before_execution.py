from __future__ import annotations

from app.schemas.audit_trace import AuditEventCategory, AuditEventStatus, AuditFailure
from app.services.audit_trace import emit_audit_event
from app.tools.sql_rag.sql.services.validation import count_unbound_sql_parameters, validate_read_only_sql
from app.tools.sql_rag.sql.state import STATUS_VALIDATION_FAILED, SqlState, fail_state


def validate_sql_before_execution(state: SqlState) -> SqlState:
    candidate = state.get("candidate_sql")
    if not isinstance(candidate, str) or not candidate.strip():
        _emit_validation_failed(state, "missing_candidate_sql", "Candidate SQL is unavailable.", {})
        return fail_state("validate_sql_before_execution", "missing_candidate_sql", "Candidate SQL is unavailable.", status=STATUS_VALIDATION_FAILED)
    parameter_count = count_unbound_sql_parameters(candidate)
    if parameter_count:
        regeneration_count = state.get("unbound_parameter_regeneration_count", 0)
        regeneration_scheduled = regeneration_count == 0
        next_regeneration_count = regeneration_count + 1 if regeneration_scheduled else regeneration_count
        _emit_validation_failed(
            state,
            "unbound_sql_parameter",
            "Candidate SQL contains an unbound parameter.",
            {},
            extra_metadata={
                "parameter_count": parameter_count,
                "unbound_parameter_regeneration_count": next_regeneration_count,
                "regeneration_scheduled": regeneration_scheduled,
            },
        )
        if regeneration_scheduled:
            return {
                "candidate_sql": None,
                "validated_sql": None,
                "unbound_parameter_regeneration_count": next_regeneration_count,
            }
        return fail_state(
            "validate_sql_before_execution",
            "unbound_sql_parameter",
            "Candidate SQL contains an unbound parameter.",
            status=STATUS_VALIDATION_FAILED,
        )
    try:
        validation = validate_read_only_sql(candidate, state.get("selected_resources") or {})
    except ValueError as exc:
        _emit_validation_failed(
            state,
            str(exc),
            "Candidate SQL failed deterministic validation.",
            getattr(exc, "metadata", {}),
        )
        return fail_state("validate_sql_before_execution", str(exc), "Candidate SQL failed deterministic validation.", status=STATUS_VALIDATION_FAILED)
    emit_audit_event(
        request_id=state.get("request_id"),
        trace_id=state.get("trace_id"),
        event_category=AuditEventCategory.SQL,
        event_type="sql_validation_completed",
        status=AuditEventStatus.SUCCEEDED,
        workflow_name="sql_subgraph",
        node_name="validate_sql_before_execution",
        metadata={
            "validation_status": "approved",
            "allowed_operation": "read_only",
            "statement_count": validation["statement_count"],
            "operation_types": validation["operation_types"],
            "syntax_valid": validation["syntax_valid"],
            "read_only": validation["read_only"],
            "sql_hash": validation["sql_hash"],
        },
        restricted_metadata={"validated_sql": validation["sql"], "validation_messages": []},
        include_trace_entry=False,
    )
    return {
        "validated_sql": validation,
        "audit_metadata": {**state.get("audit_metadata", {}), "sql_hash": validation["sql_hash"]},
    }


def _emit_validation_failed(
    state: SqlState,
    failure_code: str,
    failure_reason: str,
    validation: dict,
    *,
    extra_metadata: dict | None = None,
) -> None:
    emit_audit_event(
        request_id=state.get("request_id"),
        trace_id=state.get("trace_id"),
        event_category=AuditEventCategory.SQL,
        event_type="sql_validation_failed",
        status=AuditEventStatus.VALIDATION_FAILED,
        workflow_name="sql_subgraph",
        node_name="validate_sql_before_execution",
        failure=AuditFailure(
            failed_workflow="sql_subgraph",
            failed_node="validate_sql_before_execution",
            failure_code=failure_code,
            failure_reason=failure_reason,
        ),
        metadata={
            "validation_status": "failed",
            "failure_code": failure_code,
            "allowed_operation": "read_only",
            "statement_count": validation.get("statement_count", 0),
            "operation_types": validation.get("operation_types", []),
            "syntax_valid": validation.get("syntax_valid", False),
            "read_only": validation.get("read_only", False),
            "blocked_reason": failure_reason,
            **(extra_metadata or {}),
        },
        restricted_metadata={
            "candidate_sql": state.get("candidate_sql"),
            "validation_messages": [failure_code],
        },
        include_trace_entry=False,
    )
