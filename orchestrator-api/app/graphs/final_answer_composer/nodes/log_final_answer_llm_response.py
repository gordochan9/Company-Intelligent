from __future__ import annotations

from app.graphs.final_answer_composer.state import FinalAnswerComposerState
from app.schemas.audit_trace import AuditEventCategory, AuditEventStatus
from app.services.audit_trace import append_trace_entry, emit_audit_event


def log_final_answer_llm_response(state: FinalAnswerComposerState) -> FinalAnswerComposerState:
    status = AuditEventStatus.SUCCEEDED if state.get("raw_final_answer_llm_response") is not None else AuditEventStatus.FAILED
    result = emit_audit_event(
        request_id=state.get("request_id"),
        trace_id=state.get("trace_id"),
        event_category=AuditEventCategory.FINAL_ANSWER,
        event_type="final_answer_llm_response",
        status=status,
        workflow_name="final_answer_composer",
        node_name="log_final_answer_llm_response",
        metadata={"provider_status": (state.get("final_answer_llm_metadata") or {}).get("provider_status")},
        restricted_metadata={"llm_response": state.get("raw_final_answer_llm_response")},
    )
    return append_trace_entry({}, result.trace_entry)
