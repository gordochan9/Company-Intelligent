from __future__ import annotations

from app.schemas.audit_trace import AuditEventCategory, AuditEventStatus
from app.services.audit_trace import append_trace_entry, emit_audit_event
from app.tools.sql_rag.rag.contracts import public_rag_result
from app.tools.sql_rag.rag.state import STATUS_ERROR, STATUS_INSUFFICIENT, RagState, empty_validated_output, safe_error


def emit_rag_failure(state: RagState) -> RagState:
    status = state.get("rag_status") if state.get("rag_status") in {STATUS_INSUFFICIENT, STATUS_ERROR} else STATUS_ERROR
    errors = state.get("errors") or [safe_error(state.get("failure_code") or "rag_failed", "RAG workflow failed.")]
    result = emit_audit_event(
        request_id=state.get("request_id"),
        trace_id=state.get("trace_id"),
        event_category=AuditEventCategory.RAG,
        event_type="rag_failure_emitted",
        status=AuditEventStatus.FAILED,
        workflow_name="rag_subgraph",
        node_name="emit_rag_failure",
        metadata={
            "rag_status": status,
            "failure_code": state.get("failure_code"),
            "failed_node": state.get("failed_node"),
        },
    )
    patch: RagState = {
        "rag_status": status,
        "rag_result": public_rag_result(
            step_id=state.get("step_id", ""),
            status=status,
            validated_output=empty_validated_output(),
            limitations=state.get("limitations", []),
            errors=errors,
            audit_metadata={
                "rag_status": status,
                "failure_code": state.get("failure_code"),
                "failed_node": state.get("failed_node"),
            },
        ),
    }
    return append_trace_entry(patch, result.trace_entry)
